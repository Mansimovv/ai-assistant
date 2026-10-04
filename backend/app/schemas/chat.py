import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.ai.confirmations import PendingAction
from app.ai.router import ActionRecord


class ChatRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
    # Continue a specific conversation; omit to continue the current one.
    conversation_id: uuid.UUID | None = None
    source_device: Annotated[str, StringConstraints(max_length=64)] = "web"


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: str
    actions: list[ActionRecord] = Field(default_factory=list)
    # High-risk actions waiting for confirmation via /actions/{id}/confirm.
    pending: list[PendingAction] = Field(default_factory=list)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationRead(BaseModel):
    id: uuid.UUID
    messages: list[MessageRead] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: uuid.UUID
    preview: str
    updated_at: datetime


class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool: str
    arguments: dict[str, Any] | None
    ok: bool
    error: str | None
    duration_ms: int
    created_at: datetime
