import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

REGISTER = {"type": "register", "device": {"id": "macbook", "name": "MacBook", "type": "mac"}}


def test_no_devices_registered(client: TestClient) -> None:
    response = client.get("/api/v1/devices")

    assert response.status_code == 200
    assert response.json() == []


def test_device_is_online_while_agent_is_connected(client: TestClient) -> None:
    with client.websocket_connect("/ws/devices") as ws:
        ws.send_json(REGISTER)
        assert ws.receive_json() == {"type": "registered"}

        [device] = client.get("/api/v1/devices").json()
        assert device["id"] == "macbook"
        assert device["name"] == "MacBook"
        assert device["type"] == "mac"
        assert device["status"] == "online"
        assert device["last_seen"] is not None

    [device] = client.get("/api/v1/devices").json()
    assert device["status"] == "offline"


def test_invalid_registration_closes_socket(client: TestClient) -> None:
    with client.websocket_connect("/ws/devices") as ws:
        ws.send_json({"type": "hello"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert exc_info.value.code == 1008
    assert client.get("/api/v1/devices").json() == []
