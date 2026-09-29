from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.router import AIRouter
from app.ai.service import AIServiceError, AIServiceNotConfiguredError
from app.api.deps import get_ai_router
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest, ai_router: Annotated[AIRouter, Depends(get_ai_router)]) -> ChatResponse:
    try:
        reply = await ai_router.handle(request.message)
    except AIServiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"AI service is not configured: {exc}") from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI provider request failed. See backend logs.") from exc
    return ChatResponse(message=reply)
