from fastapi import APIRouter, HTTPException, status

from app.ai.service import AIServiceError, AIServiceNotConfiguredError
from app.api.deps import AssistantDep
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest, assistant: AssistantDep) -> ChatResponse:
    try:
        result = await assistant.send(
            request.message, conversation_id=request.conversation_id, source_device=request.source_device
        )
    except AIServiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"AI service is not configured: {exc}") from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI provider request failed. See backend logs.") from exc
    return ChatResponse(**result.model_dump())
