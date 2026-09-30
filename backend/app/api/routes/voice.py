from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from app.ai.assistant import VoiceToolResult
from app.ai.service import AIServiceError, AIServiceNotConfiguredError
from app.ai.voice import VoiceSession
from app.api.deps import AssistantDep, VoiceServiceDep

router = APIRouter(tags=["voice"])


class VoiceToolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class VoiceTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]


@router.post("/voice/session")
async def create_voice_session(assistant: AssistantDep, voice: VoiceServiceDep) -> VoiceSession:
    """Mint a short-lived credential for a browser voice session.

    The real API key never leaves the backend. The session is configured with the
    current device list and the same tools the text path offers.
    """
    instructions, tools, vocabulary = await assistant.voice_context()
    try:
        return await voice.create_session(instructions, tools, vocabulary)
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
