"""Model provider abstraction.

The rest of the app talks to `AIService`, never to a provider SDK, so the
provider or model can change without touching callers. The Chat Completions
shape is used because most providers (OpenAI, Ollama, OpenRouter) speak it.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)  # assistant only
    tool_call_id: str | None = None  # tool results only
    # Images the model should see (data: URLs), e.g. a screenshot. Never persisted.
    images: list[str] = Field(default_factory=list, exclude=True)


class ToolSpec(BaseModel):
    """A tool as the model sees it."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class Completion(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class AIServiceError(Exception):
    """The model provider failed to produce a response."""


class AIServiceNotConfiguredError(AIServiceError):
    """Required provider settings, such as the API key, are missing."""


class AIService(ABC):
    @abstractmethod
    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> Completion:
        """Return the model's next step: a reply, tool calls, or both."""


def _to_openai_message(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content or ""}
    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in message.tool_calls
            ],
        }
    if message.images:
        return {
            "role": message.role,
            "content": [
                {"type": "text", "text": message.content or ""},
                *({"type": "image_url", "image_url": {"url": url, "detail": "high"}} for url in message.images),
            ],
        }
    return {"role": message.role, "content": message.content or ""}


class OpenAIService(AIService):
    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url) if api_key else None
        self._model = model

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> Completion:
        if self._client is None:
            raise AIServiceNotConfiguredError("OPENAI_API_KEY is not set")

        request: dict[str, Any] = {
            "model": self._model,
            "messages": [_to_openai_message(message) for message in messages],
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]

        try:
            response = await self._client.chat.completions.create(**request)
        except OpenAIError as exc:
            logger.exception("OpenAI request failed")
            raise AIServiceError("OpenAI request failed") from exc

        if response.usage:  # visible token cost per call
            logger.info(
                "model=%s tokens in=%s out=%s",
                response.model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        message = response.choices[0].message
        return Completion(text=message.content, tool_calls=[_parse_tool_call(c) for c in message.tool_calls or []])


def _parse_tool_call(call: Any) -> ToolCall:
    raw = call.function.arguments or "{}"
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        # The model produced invalid JSON. Pass empty arguments through: validation
        # then fails and the error goes back to the model, which can retry.
        logger.warning("Tool call %s had invalid JSON arguments", call.function.name)
        arguments = {}
    return ToolCall(id=call.id, name=call.function.name, arguments=arguments)
