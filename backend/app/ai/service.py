"""Model provider abstraction.

The rest of the app talks to `AIService`, never to a provider SDK, so the
provider or model can change without touching callers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Literal

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class AIServiceError(Exception):
    """The model provider failed to produce a response."""


class AIServiceNotConfiguredError(AIServiceError):
    """Required provider settings, such as the API key, are missing."""


class AIService(ABC):
    @abstractmethod
    async def complete(self, messages: list[ChatMessage]) -> str:
        """Return the model's reply to a conversation."""


class OpenAIService(AIService):
    def __init__(self, api_key: str | None, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def complete(self, messages: list[ChatMessage]) -> str:
        if self._client is None:
            raise AIServiceNotConfiguredError("OPENAI_API_KEY is not set")
        try:
            response = await self._client.responses.create(
                model=self._model,
                input=[message.model_dump() for message in messages],
            )
        except OpenAIError as exc:
            logger.exception("OpenAI request failed")
            raise AIServiceError("OpenAI request failed") from exc
        return response.output_text
