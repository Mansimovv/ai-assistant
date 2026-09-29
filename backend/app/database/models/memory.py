import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, TimestampMixin


class Memory(TimestampMixin, Base):
    """Something the assistant should remember.

    Semantic recall adds a pgvector `embedding` column here.
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # a MemoryKind value
    content: Mapped[str] = mapped_column(Text)
