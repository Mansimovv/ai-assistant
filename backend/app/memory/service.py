from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory
from app.memory.models import MemoryKind, MemoryRecord


class MemoryService:
    """Long-term memory: preferences, projects, devices, past tasks, context.

    `search` is plain text matching for now. With pgvector it becomes semantic
    similarity search over an embedding column, without changing callers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(self, kind: MemoryKind, content: str) -> MemoryRecord:
        memory = Memory(kind=kind, content=content)
        self._session.add(memory)
        await self._session.commit()
        await self._session.refresh(memory)
        return MemoryRecord.model_validate(memory)

    async def recent(self, kind: MemoryKind | None = None, limit: int = 20) -> list[MemoryRecord]:
        statement = select(Memory).order_by(Memory.created_at.desc()).limit(limit)
        if kind is not None:
            statement = statement.where(Memory.kind == kind)
        return [MemoryRecord.model_validate(memory) for memory in await self._session.scalars(statement)]

    async def search(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        statement = (
            select(Memory)
            .where(Memory.content.icontains(query, autoescape=True))
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return [MemoryRecord.model_validate(memory) for memory in await self._session.scalars(statement)]
