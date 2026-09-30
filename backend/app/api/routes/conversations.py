from fastapi import APIRouter

from app.api.deps import ConversationsDep
from app.schemas.chat import ActionLogRead, ConversationRead, MessageRead

router = APIRouter(tags=["conversations"])


@router.get("/conversations/current")
async def current_conversation(conversations: ConversationsDep) -> ConversationRead:
    """The thread every device shares. Starts a new one after an hour of silence."""
    conversation = await conversations.current()
    rows = await conversations.rows(conversation.id)
    return ConversationRead(
        id=conversation.id,
        # Tool messages carry raw JSON for the model; the readable thread is user/assistant.
        messages=[MessageRead.model_validate(row) for row in rows if row.role in ("user", "assistant") and row.content],
    )


@router.get("/activity")
async def recent_activity(conversations: ConversationsDep) -> list[ActionLogRead]:
    """Audit log: what was actually executed, and whether it worked."""
    return [ActionLogRead.model_validate(row) for row in await conversations.recent_actions()]
