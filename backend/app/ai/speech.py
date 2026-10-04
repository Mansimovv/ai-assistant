"""Native Azerbaijani text-to-speech (Azure Speech).

The realtime model understands Azerbaijani well but speaks it with a foreign accent.
When a key is configured, the realtime model answers in text and this service turns
each sentence into speech with a native az-AZ voice.
"""

import logging
from xml.sax.saxutils import escape

import httpx

from app.ai.service import AIServiceError, AIServiceNotConfiguredError

logger = logging.getLogger(__name__)

OUTPUT_FORMAT = "audio-24khz-96kbitrate-mono-mp3"
TIMEOUT_SECONDS = 15


class SpeechService:
    def __init__(self, key: str | None, region: str, voice: str) -> None:
        self._key = key
        self._url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self._voice = voice
        self._client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def synthesize(self, text: str) -> bytes:
        """MP3 audio of `text` spoken by the configured voice."""
        if not self._key:
            raise AIServiceNotConfiguredError("AZURE_SPEECH_KEY is not set")
        locale = "-".join(self._voice.split("-")[:2])
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}'>"
            f"<voice name='{self._voice}'>{escape(text)}</voice></speak>"
        )
        try:
            response = await self._client.post(
                self._url,
                content=ssml.encode("utf-8"),
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                    "User-Agent": "jarvis",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Speech synthesis failed: %s", exc)
            raise AIServiceError("Speech synthesis failed") from exc
        return response.content
