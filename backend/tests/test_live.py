"""GPT-Live voice: the browser's offer is answered here, with the conversation so far."""

from fastapi.testclient import TestClient

from app.ai.live import LiveService, LiveSession, _history_items
from app.ai.service import ChatMessage
from app.api.deps import get_live_service
from app.main import app


def test_live_without_api_key_returns_503(client: TestClient) -> None:
    app.dependency_overrides[get_live_service] = lambda: LiveService(api_key=None, model="gpt-live-1", voice="cedar")

    response = client.post("/api/v1/voice/live", json={"sdp": "v=0"})

    assert response.status_code == 503


def test_live_session_gets_the_conversation_and_returns_the_answer(client: TestClient) -> None:
    captured: dict[str, object] = {}

    class RecordingLive(LiveService):
        async def connect(self, offer_sdp, app_name, owner, memory, history):  # type: ignore[override]
            captured.update(offer=offer_sdp, history=[m.content for m in history])
            return LiveSession(session_id="sess_1", sdp="answer-sdp")

    app.dependency_overrides[get_live_service] = lambda: RecordingLive(api_key="k", model="m", voice="cedar")
    client.post("/api/v1/voice/turn", json={"role": "user", "text": "Serverim 10.0.0.5-dir"})

    body = client.post("/api/v1/voice/live", json={"sdp": "offer-sdp"}).json()

    assert body == {"session_id": "sess_1", "sdp": "answer-sdp"}
    assert captured == {"offer": "offer-sdp", "history": ["Serverim 10.0.0.5-dir"]}


def test_history_becomes_live_text_items_without_tool_noise() -> None:
    items = _history_items(
        [
            ChatMessage(role="system", content="prompt"),
            ChatMessage(role="user", content="Docker işləyir?"),
            ChatMessage(role="tool", tool_call_id="c1", content='{"ok": true}'),
            ChatMessage(role="assistant", content="Bəli."),
        ]
    )

    assert items == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Docker işləyir?"}]},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Bəli."}]},
    ]


def test_api_info_tells_the_client_which_voice_engine_to_use(client: TestClient) -> None:
    assert client.get("/").json()["voice"] in ("live", "realtime")
