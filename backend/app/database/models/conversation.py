import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, TimestampMixin

# Autoincrementing ids keep message order exact, which matters: the model is fed
# the messages in this order.
MessageId = BigInteger().with_variant(Integer, "sqlite")
JsonColumn = JSON().with_variant(JSONB, "postgresql")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(String(200))
    # A conversation stays "current" until it has been idle for a while.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(MessageId, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool
    content: Mapped[str | None] = mapped_column(Text)
    # Set on assistant messages that asked for tools, and on tool results.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonColumn)
    tool_call_id: Mapped[str | None] = mapped_column(String(64))
    # Which device the user spoke from (null for assistant and tool messages).
    source_device: Mapped[str | None] = mapped_column(String(64))
