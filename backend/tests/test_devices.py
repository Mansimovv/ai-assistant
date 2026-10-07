import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

REGISTER = {
    "type": "register",
    "device": {"id": "macbook", "name": "MacBook", "type": "mac"},
    "capabilities": ["open_app", "docker_status", "not_a_real_capability"],
}


def test_no_devices_registered(client: TestClient) -> None:
    response = client.get("/api/v1/devices")

    assert response.status_code == 200
    assert response.json() == []


def test_agent_registration_publishes_its_capabilities(client: TestClient) -> None:
    with client.websocket_connect("/ws/devices") as ws:
        ws.send_json(REGISTER)
        # Unknown capabilities are dropped instead of being offered to the model.
        assert ws.receive_json() == {"type": "registered", "capabilities": ["open_app", "docker_status"]}

        [device] = client.get("/api/v1/devices").json()
        assert device["status"] == "online"
        assert device["capabilities"] == ["open_app", "docker_status"]
        assert device["last_seen"] is not None

        tools = {tool["name"]: tool for tool in client.get("/api/v1/tools").json()}
        assert tools["mac_open_app"]["target"] == "device"
        assert tools["mac_open_app"]["risk"] == "low"
        assert "mac_run_command" not in tools  # not announced by this agent

    [device] = client.get("/api/v1/devices").json()
    assert device["status"] == "offline"
    assert device["capabilities"] == []
    assert "mac_open_app" not in {tool["name"] for tool in client.get("/api/v1/tools").json()}


def test_invalid_registration_closes_socket(client: TestClient) -> None:
    with client.websocket_connect("/ws/devices") as ws:
        ws.send_json({"type": "hello"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert exc_info.value.code == 1008
    assert client.get("/api/v1/devices").json() == []


def test_device_tool_without_an_online_device_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/tools/mac_open_app/execute", json={"arguments": {"name": "TextEdit"}})

    assert response.status_code == 409
    assert "No online device" in response.json()["detail"]


def test_web_pages_cannot_connect_as_a_device(client: TestClient) -> None:
    """A browser sends an Origin; any site could otherwise reach localhost and pose as a device."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/devices", headers={"origin": "https://evil.example"}) as ws:
            ws.send_json(REGISTER)
            ws.receive_json()

    assert exc_info.value.code == 1008
    assert client.get("/api/v1/devices").json() == []
