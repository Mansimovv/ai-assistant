import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.memory.models import MemoryKind
from app.memory.service import MemoryService


@pytest.mark.anyio
async def test_remember_and_recall(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        memory = MemoryService(session)
        await memory.remember(MemoryKind.PREFERENCE, "Prefers VS Code over Vim")
        await memory.remember(MemoryKind.PROJECT, "Works on personal-ai")

        preferences = await memory.recent(kind=MemoryKind.PREFERENCE)
        matches = await memory.search("vs code")

    assert [record.content for record in preferences] == ["Prefers VS Code over Vim"]
    assert [record.content for record in matches] == ["Prefers VS Code over Vim"]
