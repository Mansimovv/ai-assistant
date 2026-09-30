"""Ties a user message to the conversation, the devices and the agent loop."""

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.ai.confirmations import PendingAction, PendingActions
from app.ai.prompts import build_system_prompt
from app.ai.router import ActionRecord, AIRouter, RequestedAction
from app.ai.service import ChatMessage, ToolSpec
from app.devices.actions import DeviceActions
from app.devices.manager import DeviceManager
from app.memory.conversations import ConversationService


class ActionNotFoundError(LookupError):
    """The pending action is unknown, already used, or expired."""


class ChatResult(BaseModel):
    conversation_id: uuid.UUID
    message: str
    actions: list[ActionRecord] = Field(default_factory=list)
    pending: list[PendingAction] = Field(default_factory=list)


class VoiceToolResult(BaseModel):
    result: dict[str, Any]
    pending: list[PendingAction] = Field(default_factory=list)


class Assistant:
    def __init__(
        self,
        router: AIRouter,
        conversations: ConversationService,
        devices: DeviceManager,
        actions: DeviceActions,
        pending: PendingActions,
        app_name: str,
        owner_name: str = "the owner",
    ) -> None:
        self._router = router
        self._conversations = conversations
        self._devices = devices
        self._actions = actions
        self._pending = pending
        self._app_name = app_name
        self._owner_name = owner_name

    async def send(
        self,
        message: str,
        conversation_id: uuid.UUID | None = None,
        source_device: str = "web",
    ) -> ChatResult:
        conversation = await self._conversations.current(conversation_id)
        history = await self._conversations.history(conversation.id)
        user_message = ChatMessage(role="user", content=message)

        turn = await self._router.handle([await self._system_message(), *history, user_message])

        await self._conversations.append(
            conversation, [user_message, *turn.messages], turn.actions, source_device=source_device
        )
        pending = [
            self._pending.add(conversation.id, request.tool, request.arguments, request.risk)
            for request in turn.requested
        ]
        return ChatResult(
            conversation_id=conversation.id, message=turn.text, actions=turn.actions, pending=pending
        )

    async def confirm(self, action_id: str) -> ChatResult:
        """Run a held-back action now that the user approved it, then report back."""
        action = self._pending.take(action_id)
        if action is None:
            raise ActionNotFoundError(action_id)

        result = await self._actions.execute(action.tool, action.arguments)
        record = ActionRecord(tool=action.tool, arguments=action.arguments, ok=result.ok, error=result.error)

        conversation = await self._conversations.current(action.conversation_id)
        note = ChatMessage(
            role="system",
            content=(
                f"The user confirmed {action.tool} with arguments {json.dumps(action.arguments)}. "
                f"It has now been executed. Result: {result.model_dump_json()}. "
                "Tell the user the outcome briefly and honestly, including the output if useful."
            ),
        )
        history = await self._conversations.history(conversation.id)
        text = await self._router.finalize([await self._system_message(), *history, note])
        reply = ChatMessage(role="assistant", content=text)

        await self._conversations.append(conversation, [note, reply], [record])
        return ChatResult(conversation_id=conversation.id, message=text, actions=[record])

    def cancel(self, action_id: str) -> None:
        if self._pending.take(action_id) is None:
            raise ActionNotFoundError(action_id)

    async def _system_message(self) -> ChatMessage:
        return ChatMessage(
            role="system",
            content=build_system_prompt(self._app_name, await self._devices.summary(), self._owner_name),
        )

    # --- voice ---------------------------------------------------------------
    # Voice uses the same tools, the same risk gating and the same conversation.

    async def voice_context(self) -> tuple[str, list[ToolSpec], list[str]]:
        """Instructions, tools and app names (to help transcription) for a voice session."""
        system = build_system_prompt(self._app_name, await self._devices.summary(), self._owner_name)
        return system, self._router.tool_specs(), self._devices.app_names()

    async def run_voice_tool(self, name: str, arguments: dict[str, Any]) -> VoiceToolResult:
        requested: list[RequestedAction] = []
        payload, record = await self._router.run_tool(name, arguments, requested)
        conversation = await self._conversations.current()
        await self._conversations.log_action(record, conversation.id)
        pending = [
            self._pending.add(conversation.id, request.tool, request.arguments, request.risk)
            for request in requested
        ]
        return VoiceToolResult(result=payload, pending=pending)

    async def record_voice_turn(self, role: str, text: str) -> None:
        """Keep spoken turns in the same thread as typed ones."""
        conversation = await self._conversations.current()
        await self._conversations.append(
            conversation,
            [ChatMessage(role=role, content=text)],  # type: ignore[arg-type]
            source_device="voice",
        )
