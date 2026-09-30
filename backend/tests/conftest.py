from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agents.base import AgentConnection
from app.agents.bus import CommandBus, CommandResult
from app.agents.manager import AgentManager
from app.ai.service import AIService, ChatMessage, Completion, ToolSpec
from app.database.models import Base
from app.database.session import get_session
from app.devices.actions import DeviceActions
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def session_factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    """A throwaway SQLite database with all tables, so tests don't need PostgreSQL."""
    path = tmp_path / "test.db"
    sync_engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def client(session_factory: async_sessionmaker[AsyncSession]) -> Iterator[TestClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class ScriptedAI(AIService):
    """Returns prepared completions in order, and records what it was asked."""

    def __init__(self, *completions: Completion) -> None:
        self._completions = list(completions)
        self.calls: list[list[ChatMessage]] = []
        self.tools_offered: list[list[str]] = []

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> Completion:
        self.calls.append(list(messages))
        self.tools_offered.append([tool.name for tool in tools or []])
        if self._completions:
            return self._completions.pop(0)
        return Completion(text="done")


class FakeSocket:
    """Stands in for an agent's WebSocket and answers every invoke at once."""

    def __init__(self, bus: CommandBus, result: CommandResult) -> None:
        self._bus = bus
        self._result = result
        self.invocations: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.invocations.append(message)
        self._bus.resolve(message["call_id"], self._result)


@pytest.fixture
def connected_mac() -> tuple[DeviceActions, FakeSocket]:
    """A Mac agent that is online and answers with a successful result."""
    agents = AgentManager()
    bus = CommandBus(agents)
    socket = FakeSocket(bus, CommandResult(ok=True, data={"running": True}, verified=True))
    agents.connect(
        AgentConnection(  # type: ignore[arg-type]
            "mac",
            "MacBook",
            "mac",
            ["open_app", "docker_status", "run_command", "run_in_terminal"],
            socket,
            ["Termius", "Safari"],
        )
    )
    return DeviceActions(agents, bus), socket
