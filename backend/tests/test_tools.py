from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_device_actions
from app.main import app
from app.tools.base import Tool, ToolParameters
from app.tools.registry import ConfirmationRequiredError, ToolNotFoundError, ToolRegistry, create_default_registry


class DangerousTool(Tool[ToolParameters]):
    name = "dangerous"
    description = "A tool that must be confirmed before it runs."
    parameters = ToolParameters
    requires_confirmation = True

    async def execute(self, params: ToolParameters) -> str:
        return "done"


@pytest.mark.anyio
async def test_registry_executes_tool() -> None:
    assert await create_default_registry().execute("echo", {"text": "hi"}) == {"text": "hi"}


@pytest.mark.anyio
async def test_get_current_time_returns_iso_timestamp() -> None:
    result = await create_default_registry().execute("get_current_time", {})

    assert datetime.fromisoformat(result["iso"]).tzinfo is not None


def test_registry_lists_and_gets_tools() -> None:
    registry = create_default_registry()

    assert {tool.name for tool in registry.list_tools()} == {"get_current_time", "echo"}
    assert registry.get("echo").name == "echo"
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(DangerousTool())

    with pytest.raises(ValueError):
        registry.register(DangerousTool())


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", [{}, {"text": "hi", "unexpected": 1}])
async def test_registry_validates_arguments(arguments: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        await create_default_registry().execute("echo", arguments)


@pytest.mark.anyio
async def test_dangerous_tool_requires_confirmation() -> None:
    registry = ToolRegistry()
    registry.register(DangerousTool())

    with pytest.raises(ConfirmationRequiredError):
        await registry.execute("dangerous", {})
    assert await registry.execute("dangerous", {}, confirmed=True) == "done"


def test_list_tools_endpoint(client: TestClient) -> None:
    tools = {tool["name"]: tool for tool in client.get("/api/v1/tools").json()}

    assert set(tools) == {"get_current_time", "echo"}
    assert tools["echo"]["target"] == "backend"
    assert "text" in tools["echo"]["parameters"]["properties"]


def test_execute_tool_endpoint(client: TestClient) -> None:
    response = client.post("/api/v1/tools/echo/execute", json={"arguments": {"text": "hi"}})

    assert response.status_code == 200
    assert response.json() == {"tool": "echo", "result": {"ok": True, "data": {"text": "hi"}}}


def test_execute_tool_endpoint_errors(client: TestClient) -> None:
    assert client.post("/api/v1/tools/missing/execute", json={}).status_code == 404
    assert client.post("/api/v1/tools/echo/execute", json={"arguments": {}}).status_code == 422


def test_execute_device_tool_endpoint(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices

    response = client.post("/api/v1/tools/mac_open_app/execute", json={"arguments": {"name": "TextEdit"}})

    assert response.status_code == 200
    assert response.json()["result"] == {"ok": True, "data": {"running": True}, "verified": True}
    assert socket.invocations[0]["capability"] == "open_app"
