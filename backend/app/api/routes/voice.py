from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app.ai.assistant import VoiceToolResult
from app.ai.service import AIServiceError, AIServiceNotConfiguredError
from app.ai.live import LiveSession
from app.ai.voice import VoiceSession
from app.api.deps import AssistantDep, LiveServiceDep, SpeechServiceDep, VoiceServiceDep

router = APIRouter(tags=["voice"])


class VoiceToolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class LiveOffer(BaseModel):
    sdp: str = Field(min_length=1, max_length=100_000)


class SpeakRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]


class VoiceTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]


@router.post("/voice/session")
async def create_voice_session(
    assistant: AssistantDep, voice: VoiceServiceDep, speech: SpeechServiceDep
) -> VoiceSession:
    """Mint a short-lived credential for a browser voice session.

    The real API key never leaves the backend. The session is configured with the
    current device list and the same tools the text path offers.
    """
    instructions, tools, vocabulary = await assistant.voice_context()
    try:
        return await voice.create_session(instructions, tools, vocabulary, native_speech=speech.enabled)
    except AIServiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Voice is not configured: {exc}") from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not start a voice session.") from exc


@router.post("/voice/live")
async def connect_live(offer: LiveOffer, assistant: AssistantDep, live: LiveServiceDep) -> LiveSession:
    """Answer the browser's WebRTC offer with a GPT-Live session.

    The voice delegates real work back to this backend through `/chat`, so voice and
    text share one brain, one memory and one conversation.
    """
    app_name, owner, memory, history = await assistant.live_context()
    try:
        return await live.connect(offer.sdp, app_name, owner, memory, history)
    except AIServiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Voice is not configured: {exc}") from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not start a voice session.") from exc


@router.post("/voice/tool")
async def run_voice_tool(request: VoiceToolRequest, assistant: AssistantDep) -> VoiceToolResult:
    """Execute a tool the voice model asked for, with the usual risk gating."""
    return await assistant.run_voice_tool(request.name, request.arguments)


@router.post("/voice/turn", status_code=status.HTTP_204_NO_CONTENT)
async def record_voice_turn(turn: VoiceTurn, assistant: AssistantDep) -> None:
    """Store a spoken turn so voice and text share one conversation."""
    await assistant.record_voice_turn(turn.role, turn.text)


@router.post("/voice/speak", response_class=Response)
async def speak(request: SpeakRequest, speech: SpeechServiceDep) -> Response:
    """One sentence of the assistant's answer, spoken by the native Azerbaijani voice."""
    try:
        audio = await speech.synthesize(request.text)
    except AIServiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Speech is not configured: {exc}") from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Speech synthesis failed.") from exc
    return Response(content=audio, media_type="audio/mpeg")
