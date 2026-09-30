from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.router import ActionRecord
from app.ai.service import ChatMessage
from app.memory.conversations import IDLE_MINUTES, ConversationService


@pytest.mark.anyio
async def test_messages_survive_and_keep_their_order(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        service = ConversationService(session)
        conversation = await service.current()
        await service.append(
            conversation,
            [
                ChatMessage(role="user", content="Docker işləyir?"),
                ChatMessage(role="assistant", content="Yoxlayıram"),
                ChatMessage(role="tool", tool_call_id="c1", content='{"ok": true}'),
                ChatMessage(role="assistant", content="Bəli, işləyir."),
            ],
            [ActionRecord(tool="mac_docker_status", ok=True, duration_ms=12)],
            source_device="web",
        )

        history = await service.history(conversation.id)
        actions = await service.recent_actions()

    assert [message.role for message in history] == ["user", "assistant", "tool", "assistant"]
    assert [(action.tool, action.ok) for action in actions] == [("mac_docker_status", True)]


@pytest.mark.anyio
async def test_an_idle_conversation_is_not_continued(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        service = ConversationService(session)
        old = await service.current()
        old.updated_at = datetime.now(UTC) - timedelta(minutes=IDLE_MINUTES + 5)
        await session.commit()

        fresh = await service.current()
        # ...unless the client explicitly asks for it.
        resumed = await service.current(old.id)

    assert fresh.id != old.id
    assert resumed.id == old.id
