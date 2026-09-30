"""The agent loop: model → tool calls → results → model → ... → answer."""

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from app.ai.service import AIService, ChatMessage, ToolCall, ToolSpec
from app.devices.actions import DeviceActions
from app.devices.capabilities import Risk
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_STEPS = 8


class ActionRecord(BaseModel):
    """One executed tool call, for the UI and the audit log."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    error: str | None = None
    duration_ms: int = 0


class RequestedAction(BaseModel):
    """A high-risk call the model wanted; it waits for the user's confirmation."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Risk


class AgentTurn(BaseModel):
    text: str
    actions: list[ActionRecord] = Field(default_factory=list)
    # Assistant and tool messages produced in this turn, to be persisted.
    messages: list[ChatMessage] = Field(default_factory=list)
    # High-risk calls held back for confirmation.
    requested: list[RequestedAction] = Field(default_factory=list)


class AIRouter:
    """Entry point for every user message.

    Plain questions come back as text after one model call. Anything that needs
    the user's devices goes through tool calls, whose real results decide what
    the assistant is allowed to claim.
    """

    def __init__(self, ai: AIService, tools: ToolRegistry, devices: DeviceActions, max_steps: int = MAX_STEPS) -> None:
        self._ai = ai
        self._tools = tools
        self._devices = devices
        self._max_steps = max_steps

    async def handle(self, messages: list[ChatMessage]) -> AgentTurn:
        working = list(messages)
        produced: list[ChatMessage] = []
        actions: list[ActionRecord] = []
        requested: list[RequestedAction] = []

        for _ in range(self._max_steps):
            completion = await self._ai.complete(working, self.tool_specs())
            assistant = ChatMessage(role="assistant", content=completion.text, tool_calls=completion.tool_calls)
            working.append(assistant)
            produced.append(assistant)

            if not completion.tool_calls:
                return AgentTurn(
                    text=completion.text or "", actions=actions, messages=produced, requested=requested
                )

            for call in completion.tool_calls:
                payload, record = await self._run(call, requested)
                result = ChatMessage(role="tool", tool_call_id=call.id, content=json.dumps(payload))
                working.append(result)
                produced.append(result)
                actions.append(record)

        # Step budget spent: ask for a final answer without tools so the model has to
        # summarise what actually happened instead of looping forever.
        completion = await self._ai.complete(working)
        assistant = ChatMessage(role="assistant", content=completion.text)
        produced.append(assistant)
        return AgentTurn(text=completion.text or "", actions=actions, messages=produced, requested=requested)

    async def finalize(self, messages: list[ChatMessage]) -> str:
        """One reply with no tools, used after a confirmed action has run."""
        completion = await self._ai.complete(messages)
        return completion.text or ""


    def tool_specs(self) -> list[ToolSpec]:
        """Everything the model may call right now: backend tools + online devices."""
        return [*self._local_specs(), *self._devices.specs()]

    def _local_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters.model_json_schema(),
            )
            for tool in self._tools.list_tools()
        ]

    async def _run(
        self, call: ToolCall, requested: list[RequestedAction]
    ) -> tuple[dict[str, Any], ActionRecord]:
        return await self.run_tool(call.name, call.arguments, requested)

    async def run_tool(
        self, name: str, arguments: dict[str, Any], requested: list[RequestedAction]
    ) -> tuple[dict[str, Any], ActionRecord]:
        """Run one tool under the same rules for every channel (text and voice)."""
        call = ToolCall(id="", name=name, arguments=arguments)
        started = time.monotonic()
        if self._devices.knows(call.name) and self._devices.risk(call.name) is Risk.HIGH:
            # Hold it back: the user confirms in the UI, then the brain runs it.
            requested.append(
                RequestedAction(tool=call.name, arguments=call.arguments, risk=self._devices.risk(call.name))
            )
            payload = {
                "ok": False,
                "error": "confirmation_required",
                "message": "Show the user exactly what this would do and ask them to confirm it.",
            }
            return payload, ActionRecord(
                tool=call.name, arguments=call.arguments, ok=False, error="confirmation_required"
            )

        if self._devices.knows(call.name):
            result = await self._devices.execute(call.name, call.arguments)
            payload = result.model_dump(exclude_none=True)
            ok, error = result.ok, result.error
        else:
            try:
                data = await self._tools.execute(call.name, call.arguments)
                payload, ok, error = {"ok": True, "data": data}, True, None
            except Exception as exc:  # tool errors belong to the model, not to the user
                logger.warning("Tool %s failed: %s", call.name, exc)
                payload, ok, error = {"ok": False, "error": str(exc)}, False, str(exc)

        duration_ms = int((time.monotonic() - started) * 1000)
        record = ActionRecord(
            tool=call.name, arguments=call.arguments, ok=ok, error=error, duration_ms=duration_ms
        )
        return payload, record
