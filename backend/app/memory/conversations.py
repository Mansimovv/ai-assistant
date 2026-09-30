"""Conversation storage.

There is one rolling conversation: any device joins the same thread, so moving
from phone to laptop continues the same talk. After `IDLE_MINUTES` of silence the
next message starts a new conversation.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import ActionRecord
from app.ai.service import ChatMessage, ToolCall
from app.database.models import Conversation, Message, ToolCallLog

IDLE_MINUTES = 60
HISTORY_LIMIT = 40


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current(self, conversation_id: uuid.UUID | None = None) -> Conversation:
        if conversation_id is not None:
            conversation = await self._session.get(Conversation, conversation_id)
            if conversation is not None:
                return conversation

        cutoff = datetime.now(UTC) - timedelta(minutes=IDLE_MINUTES)
        recent = await self._session.scalars(
            select(Conversation).where(Conversation.updated_at >= cutoff).order_by(Conversation.updated_at.desc())
        )
        conversation = recent.first()
        if conversation is None:
            conversation = Conversation()
            self._session.add(conversation)
            await self._session.commit()
            await self._session.refresh(conversation)
        return conversation

    async def history(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        rows = await self._session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
        return [_to_chat_message(row) for row in list(rows)[-HISTORY_LIMIT:]]

    async def rows(self, conversation_id: uuid.UUID) -> list[Message]:
        """Stored messages, for showing the thread in a client."""
        rows = await self._session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
        return list(rows)

    async def append(
        self,
        conversation: Conversation,
        messages: list[ChatMessage],
        actions: list[ActionRecord] | None = None,
        source_device: str | None = None,
    ) -> None:
        for message in messages:
            self._session.add(
                Message(
                    conversation_id=conversation.id,
                    role=message.role,
                    content=message.content,
                    tool_calls=[call.model_dump() for call in message.tool_calls] or None,
                    tool_call_id=message.tool_call_id,
                    source_device=source_device if message.role == "user" else None,
                )
            )
        for action in actions or []:
            self._session.add(
                ToolCallLog(
                    conversation_id=conversation.id,
                    tool=action.tool,
                    arguments=action.arguments,
                    ok=action.ok,
                    error=action.error,
                    duration_ms=action.duration_ms,
                )
            )
        conversation.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def log_action(self, action: ActionRecord, conversation_id: uuid.UUID | None = None) -> None:
        """Record a tool call that happened outside a conversation (e.g. a manual test)."""
        self._session.add(
            ToolCallLog(
                conversation_id=conversation_id,
                tool=action.tool,
                arguments=action.arguments,
                ok=action.ok,
                error=action.error,
                duration_ms=action.duration_ms,
            )
        )
        await self._session.commit()

    async def recent_actions(self, limit: int = 20) -> list[ToolCallLog]:
        rows = await self._session.scalars(select(ToolCallLog).order_by(ToolCallLog.id.desc()).limit(limit))
        return list(rows)


def _to_chat_message(row: Message) -> ChatMessage:
    return ChatMessage(
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        tool_calls=[ToolCall.model_validate(call) for call in row.tool_calls or []],
        tool_call_id=row.tool_call_id,
    )
