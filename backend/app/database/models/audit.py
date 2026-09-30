import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, TimestampMixin
from app.database.models.conversation import JsonColumn, MessageId


class ToolCallLog(TimestampMixin, Base):
    """Every executed tool call. Append-only: this is the answer to "what did it do?"."""

    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(MessageId, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    tool: Mapped[str] = mapped_column(String(100), index=True)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
