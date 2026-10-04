import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ConversationsDep
from app.database.models import Conversation
from app.memory.conversations import ConversationService
from app.schemas.chat import ActionLogRead, ConversationRead, ConversationSummary, MessageRead

router = APIRouter(tags=["conversations"])

PREVIEW_LENGTH = 80


async def _read(conversations: ConversationService, conversation: Conversation) -> ConversationRead:
    rows = await conversations.rows(conversation.id)
    return ConversationRead(
        id=conversation.id,
        # Tool messages carry raw JSON for the model; the readable thread is user/assistant.
        messages=[MessageRead.model_validate(row) for row in rows if row.role in ("user", "assistant") and row.content],
    )


@router.get("/conversations")
async def list_conversations(conversations: ConversationsDep) -> list[ConversationSummary]:
    """Past conversations for the history sidebar, newest first."""
    return [
        ConversationSummary(id=conversation.id, preview=preview[:PREVIEW_LENGTH], updated_at=conversation.updated_at)
        for conversation, preview in await conversations.recent()
    ]


@router.get("/conversations/current")
async def current_conversation(conversations: ConversationsDep) -> ConversationRead:
    """The thread every device shares. Starts a new one after an hour of silence."""
    return await _read(conversations, await conversations.current())


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, conversations: ConversationsDep) -> ConversationRead:
    conversation = await conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return await _read(conversations, conversation)


@router.get("/activity")
async def recent_activity(conversations: ConversationsDep) -> list[ActionLogRead]:
    """Audit log: what was actually executed, and whether it worked."""
    return [ActionLogRead.model_validate(row) for row in await conversations.recent_actions()]
