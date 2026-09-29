import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class MemoryKind(StrEnum):
    CONVERSATION = "conversation"
    PREFERENCE = "preference"
    PROJECT = "project"
    DEVICE = "device"
    TASK = "task"
    CONTEXT = "context"


class MemoryRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MemoryKind
    content: str
    created_at: datetime
