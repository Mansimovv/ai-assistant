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

from app.ai.service import AIServiceError, AIServiceNotConfiguredError, ToolSpec, without_titles

logger = logging.getLogger(__name__)

VOICE_GUIDANCE = """
Your words are spoken out loud, in Azerbaijani (Baku accent), like a real person on a
call: natural rhythm, warm and calm, short sentences, the way people in Baku actually
talk. Never sound like you are reading. Write every Azerbaijani letter correctly (ə, ı, ş,
ç, ğ, ö, ü) and write numbers, times and dates as Azerbaijani words ("saat üçə on dəqiqə
qalmış"), never digits or symbols. No markdown, no lists, no emoji.
Keep answers to one or two sentences unless asked for more. Never read JSON, paths or
code aloud; summarise instead.
If you did not clearly hear what was said, say so and ask them to repeat - never guess
an action from noise. While a tool is running, you may say a very short "bir saniyə".
If an action needs confirmation, say so in one sentence and stop; the user confirms on
screen.
You were woken by "Hey Jarvis". When the user says goodbye or sends you away ("sağ ol",
"yat", "bəsdir", "görüşərik", "hələlik"), say a very short goodbye and call go_to_sleep.
"""

# Handled by the browser, not the backend: it ends the session and goes back to
# listening for the wake word.
SLEEP_TOOL = {
    "type": "function",
    "name": "go_to_sleep",
    "description": "End the voice conversation and go back to waiting for 'Hey Jarvis'.",
    "parameters": {"type": "object", "properties": {}},
}

# Speech recognition mishears names like "Termius" unless it knows to expect them.
TRANSCRIPTION_HINT = "Azərbaycan dilində danışıq. Cihaz və proqram adları: {names}."
VOCABULARY_LIMIT = 60


class VoiceSession(BaseModel):
    client_secret: str
    expires_at: int | None = None
    model: str
    # "native": the model answers in text and the browser speaks it via /voice/speak.
    # "realtime": the model speaks itself.
    speech: str = "realtime"


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

    async def create_session(
        self,
        instructions: str,
        tools: list[ToolSpec],
        vocabulary: list[str] | None = None,
        native_speech: bool = False,
    ) -> VoiceSession:
        if self._client is None:
            raise AIServiceNotConfiguredError("OPENAI_API_KEY is not set")

        transcription: dict[str, object] = {"model": self._transcribe_model, "language": self._language}
        if vocabulary and self._transcribe_model in ("gpt-transcribe", "gpt-live-transcribe"):
            transcription["keywords"] = ["Jarvis", *vocabulary[:VOCABULARY_LIMIT]]
        elif vocabulary:
            transcription["prompt"] = TRANSCRIPTION_HINT.format(
                names=", ".join(vocabulary[:VOCABULARY_LIMIT])
            )

        try:
            secret = await self._client.realtime.client_secrets.create(
                session={
                    "type": "realtime",
                    "model": self._model,
                    "instructions": f"{instructions}\n{VOICE_GUIDANCE}",
                    "output_modalities": ["text"] if native_speech else ["audio"],
                    "audio": {
                        "input": {
                            "transcription": transcription,
                            # Laptop microphone: filtering room noise is what stops background
                            # sounds from being taken as speech.
                            "noise_reduction": {"type": "far_field"},
                            # Language-agnostic VAD, tuned to wait for a natural pause instead of
                            # cutting the user off mid-sentence.
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.6,
                                "silence_duration_ms": 700,
                                "prefix_padding_ms": 300,
                                "create_response": True,
                                "interrupt_response": True,
                            },
                        },
                        "output": {"voice": self._voice},
                    },
                    "tools": [
                        {
                            "type": "function",
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": without_titles(tool.parameters),
                        }
                        for tool in tools
                    ]
                    + [SLEEP_TOOL],
                }
            )
        except OpenAIError as exc:
            logger.exception("Could not create a realtime session")
            raise AIServiceError("Could not start a voice session") from exc

        logger.info(
            "Voice session created (model=%s, tools=%d, vocabulary=%d)",
            self._model,
            len(tools),
            len(vocabulary or []),
        )
        return VoiceSession(
            client_secret=secret.value,
            expires_at=secret.expires_at,
            model=self._model,
            speech="native" if native_speech else "realtime",
        )
