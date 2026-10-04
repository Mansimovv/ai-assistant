from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.router import ActionRecord
from app.ai.service import ChatMessage, ToolCall
from app.memory.conversations import HISTORY_LIMIT, IDLE_MINUTES, ConversationService


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


def test_history_lists_past_conversations_and_opens_one(client) -> None:
    client.post("/api/v1/voice/turn", json={"role": "user", "text": "Docker işləyir?"})
    client.post("/api/v1/voice/turn", json={"role": "assistant", "text": "Bəli."})

    [summary] = client.get("/api/v1/conversations").json()
    thread = client.get(f"/api/v1/conversations/{summary['id']}").json()

    assert summary["preview"] == "Docker işləyir?"
    assert [m["content"] for m in thread["messages"]] == ["Docker işləyir?", "Bəli."]
    assert client.get("/api/v1/conversations/00000000-0000-0000-0000-000000000000").status_code == 404


@pytest.mark.anyio
async def test_truncated_history_never_starts_with_orphaned_tool_results(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The provider rejects a tool result whose tool call was cut off."""
    async with session_factory() as session:
        service = ConversationService(session)
        conversation = await service.current()
        turn = [
            ChatMessage(role="user", content="Docker işləyir?"),
            ChatMessage(role="assistant", content=None, tool_calls=[ToolCall(id="c1", name="mac_docker_status", arguments={})]),
            ChatMessage(role="tool", tool_call_id="c1", content='{"ok": true}'),
            ChatMessage(role="assistant", content="Bəli."),
        ]
        # Enough turns that the limit cuts right after a tool call.
        await service.append(conversation, turn * (HISTORY_LIMIT // 4 + 1))
        await service.append(conversation, turn[:2])

        history = await service.history(conversation.id)

    assert history[0].role == "user"
    assert len(history) <= HISTORY_LIMIT
