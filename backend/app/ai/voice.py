"""Voice sessions (OpenAI Realtime).

The browser streams audio straight to OpenAI over WebRTC, which is what keeps the
latency low. To do that without ever exposing the real API key, the backend mints
a short-lived client secret here and configures the session: instructions, the
device list, and the same tools the text path uses.

Tool calls still come back through this backend (`/api/v1/voice/tool`), so risk
gating, confirmation and the audit log apply to voice exactly as to text.
"""

import logging

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

from app.ai.service import AIServiceError, AIServiceNotConfiguredError, ToolSpec

logger = logging.getLogger(__name__)

VOICE_GUIDANCE = """
You are speaking out loud, so keep answers to one or two short sentences. Never read
JSON, paths or code aloud; summarise instead. Say what you are about to do only when an
action takes a while. If an action needs confirmation, say so in one sentence and stop;
the user confirms on screen.
"""


class VoiceSession(BaseModel):
    client_secret: str
    expires_at: int | None = None
    model: str


class VoiceService:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        voice: str,
        transcribe_model: str,
        language: str,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model
        self._voice = voice
        self._transcribe_model = transcribe_model
        self._language = language

    async def create_session(self, instructions: str, tools: list[ToolSpec]) -> VoiceSession:
        if self._client is None:
            raise AIServiceNotConfiguredError("OPENAI_API_KEY is not set")

        try:
            secret = await self._client.realtime.client_secrets.create(
                session={
                    "type": "realtime",
                    "model": self._model,
                    "instructions": f"{instructions}\n{VOICE_GUIDANCE}",
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "transcription": {"model": self._transcribe_model, "language": self._language},
                            "turn_detection": {"type": "server_vad", "create_response": True},
                        },
                        "output": {"voice": self._voice},
                    },
                    "tools": [
                        {
                            "type": "function",
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in tools
                    ],
                }
            )
        except OpenAIError as exc:
            logger.exception("Could not create a realtime session")
            raise AIServiceError("Could not start a voice session") from exc

        logger.info("Voice session created (model=%s, tools=%d)", self._model, len(tools))
        return VoiceSession(client_secret=secret.value, expires_at=secret.expires_at, model=self._model)
