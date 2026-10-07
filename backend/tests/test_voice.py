"""Voice must obey the same rules as text: same tools, same gating, same conversation."""

from fastapi.testclient import TestClient

from app.ai.speech import SpeechService
from app.api.deps import get_device_actions, get_speech_service, get_voice_service
from app.ai.voice import VoiceService, VoiceSession
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


def test_voice_session_is_given_app_names_for_transcription(client: TestClient) -> None:
    """Speech recognition mishears app names ("Termius") unless the session expects them."""
    captured: dict[str, object] = {}

    class RecordingVoiceService(VoiceService):
        async def create_session(self, instructions, tools, vocabulary=None, native_speech=False):  # type: ignore[override]
            captured["vocabulary"] = vocabulary
            captured["tools"] = [tool.name for tool in tools]
            captured["instructions"] = instructions
            return VoiceSession(client_secret="ek_test", model="test-model")

    app.dependency_overrides[get_voice_service] = lambda: RecordingVoiceService(
        api_key="k", model="m", voice="marin", transcribe_model="t", language="az"
    )

    with client.websocket_connect("/ws/devices") as ws:
        ws.send_json(
            {
                "type": "register",
                "device": {"id": "macbook", "name": "MacBook", "type": "mac"},
                "capabilities": ["open_app", "run_in_terminal", "look_at_screen", "mouse_click"],
                "apps": ["Termius", "Safari"],
            }
        )
        ws.receive_json()

        assert client.post("/api/v1/voice/session").status_code == 200

    assert captured["vocabulary"] == ["Safari", "Termius"]
    assert "mac_open_app" in captured["tools"]
    # Voice gets no screenshots, so screen-control tools would only cost tokens there.
    assert "mac_look_at_screen" not in captured["tools"]
    assert "mac_mouse_click" not in captured["tools"]
    assert "MacBook" in str(captured["instructions"])


def test_spoken_turns_join_the_same_conversation(client: TestClient) -> None:
    assert client.post("/api/v1/voice/turn", json={"role": "user", "text": "Docker işləyir?"}).status_code == 204
    assert client.post("/api/v1/voice/turn", json={"role": "assistant", "text": "Bəli."}).status_code == 204

    thread = client.get("/api/v1/conversations/current").json()

    assert [(m["role"], m["content"]) for m in thread["messages"]] == [
        ("user", "Docker işləyir?"),
        ("assistant", "Bəli."),
    ]


def test_new_voice_session_is_told_the_conversation_so_far(client: TestClient) -> None:
    """A realtime session starts empty; without this, voice forgets what was just said."""
    captured: dict[str, str] = {}

    class RecordingVoiceService(VoiceService):
        async def create_session(self, instructions, tools, vocabulary=None, native_speech=False):  # type: ignore[override]
            captured["instructions"] = instructions
            return VoiceSession(client_secret="ek_test", model="test-model")

    app.dependency_overrides[get_voice_service] = lambda: RecordingVoiceService(
        api_key="k", model="m", voice="marin", transcribe_model="t", language="az"
    )
    client.post("/api/v1/voice/turn", json={"role": "user", "text": "Serverim 10.0.0.5-dir"})

    client.post("/api/v1/voice/session")

    assert "User: Serverim 10.0.0.5-dir" in captured["instructions"]


def test_speak_without_azure_key_returns_503(client: TestClient) -> None:
    app.dependency_overrides[get_speech_service] = lambda: SpeechService(None, "westeurope", "az-AZ-BabekNeural")

    response = client.post("/api/v1/voice/speak", json={"text": "Salam"})

    assert response.status_code == 503
    assert "AZURE_SPEECH_KEY" in response.json()["detail"]


def test_native_voice_makes_the_session_answer_in_text(client: TestClient) -> None:
    """With a native Azerbaijani voice, the model writes and the browser speaks."""
    captured: dict[str, bool] = {}

    class RecordingVoiceService(VoiceService):
        async def create_session(self, instructions, tools, vocabulary=None, native_speech=False):  # type: ignore[override]
            captured["native_speech"] = native_speech
            return VoiceSession(client_secret="ek_test", model="m", speech="native" if native_speech else "realtime")

    app.dependency_overrides[get_voice_service] = lambda: RecordingVoiceService(
        api_key="k", model="m", voice="marin", transcribe_model="t", language="az"
    )
    app.dependency_overrides[get_speech_service] = lambda: SpeechService("key", "westeurope", "az-AZ-BabekNeural")

    body = client.post("/api/v1/voice/session").json()

    assert captured["native_speech"] is True
    assert body["speech"] == "native"


def test_voice_tool_results_never_carry_a_screenshot(client: TestClient) -> None:
    """A base64 screenshot sent to the voice model as text would cost a fortune."""
    from app.agents.base import AgentConnection
    from app.agents.bus import CommandBus, CommandResult
    from app.agents.manager import AgentManager
    from app.devices.actions import DeviceActions
    from tests.conftest import FakeSocket

    agents = AgentManager()
    bus = CommandBus(agents)
    socket = FakeSocket(bus, CommandResult(ok=True, data={"texts": [], "screenshot": "data:image/jpeg;base64,AAAA"}))
    agents.connect(AgentConnection("mac", "MacBook", "mac", ["look_at_screen"], socket, []))  # type: ignore[arg-type]
    app.dependency_overrides[get_device_actions] = lambda: DeviceActions(agents, bus)

    body = client.post("/api/v1/voice/tool", json={"name": "mac_look_at_screen", "arguments": {}}).json()

    assert "base64" not in str(body)
