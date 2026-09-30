from fastapi import APIRouter, HTTPException, status

from app.ai.assistant import ActionNotFoundError
from app.ai.service import AIServiceError
from app.api.deps import AssistantDep
from app.schemas.chat import ChatResponse

router = APIRouter(tags=["actions"])

NOT_FOUND = "This action is unknown, already run, or expired. Ask the assistant again."


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, assistant: AssistantDep) -> ChatResponse:
    """Run a high-risk action the assistant held back, then return its real result."""
    try:
        result = await assistant.confirm(action_id)
    except ActionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from exc
    except AIServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI provider request failed. See backend logs.") from exc
    return ChatResponse(**result.model_dump())


@router.post("/actions/{action_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_action(action_id: str, assistant: AssistantDep) -> None:
    try:
        assistant.cancel(action_id)
    except ActionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from exc
