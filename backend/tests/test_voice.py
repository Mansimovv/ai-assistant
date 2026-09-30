"""Voice must obey the same rules as text: same tools, same gating, same conversation."""

from fastapi.testclient import TestClient

from app.api.deps import get_device_actions, get_voice_service
from app.ai.voice import VoiceService
from app.main import app


def test_voice_session_without_api_key_returns_503(client: TestClient) -> None:
    app.dependency_overrides[get_voice_service] = lambda: VoiceService(
        api_key=None, model="m", voice="marin", transcribe_model="t", language="az"
    )

    response = client.post("/api/v1/voice/session")

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_voice_tool_runs_low_risk_action_and_audits_it(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices

    response = client.post("/api/v1/voice/tool", json={"name": "mac_open_app", "arguments": {"name": "TextEdit"}})

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == {"ok": True, "data": {"running": True}, "verified": True}
    assert body["pending"] == []
    assert socket.invocations[0]["capability"] == "open_app"
    assert [(e["tool"], e["ok"]) for e in client.get("/api/v1/activity").json()] == [("mac_open_app", True)]


def test_voice_cannot_bypass_confirmation(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices

    body = client.post("/api/v1/voice/tool", json={"name": "mac_run_command", "arguments": {"command": "ls"}}).json()

    assert socket.invocations == []  # nothing ran
    assert body["result"]["error"] == "confirmation_required"
    [pending] = body["pending"]
    assert pending["tool"] == "mac_run_command"
    assert pending["risk"] == "high"


def test_spoken_turns_join_the_same_conversation(client: TestClient) -> None:
    assert client.post("/api/v1/voice/turn", json={"role": "user", "text": "Docker işləyir?"}).status_code == 204
    assert client.post("/api/v1/voice/turn", json={"role": "assistant", "text": "Bəli."}).status_code == 204

    thread = client.get("/api/v1/conversations/current").json()

    assert [(m["role"], m["content"]) for m in thread["messages"]] == [
        ("user", "Docker işləyir?"),
        ("assistant", "Bəli."),
    ]
