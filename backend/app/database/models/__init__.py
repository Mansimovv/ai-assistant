# Import every model here so Base.metadata (used by Alembic) knows all tables.
from app.database.models.base import Base
from app.database.models.conversation import Conversation, Message
from app.database.models.device import Device
from app.database.models.memory import Memory

__all__ = ["Base", "Conversation", "Device", "Memory", "Message"]
