import pytest
from fastapi.testclient import TestClient

from app.ai.service import AIServiceError, ChatMessage, Completion, OpenAIService, ToolCall
from app.api.deps import get_ai_service, get_device_actions
from app.main import app
from tests.conftest import ScriptedAI


class BrokenAI(ScriptedAI):
    async def complete(self, messages: list[ChatMessage], tools=None) -> Completion:
        raise AIServiceError("boom")


def use_ai(ai) -> None:
    app.dependency_overrides[get_ai_service] = lambda: ai


def test_chat_answers_and_keeps_the_conversation(client: TestClient) -> None:
    use_ai(ScriptedAI(Completion(text="Salam! Necə kömək edə bilərəm?")))

    response = client.post("/api/v1/chat", json={"message": "Salam"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Salam! Necə kömək edə bilərəm?"
    assert body["conversation_id"]
    assert body["actions"] == [] and body["pending"] == []

    # The same thread is returned to any client that asks for the current conversation.
    thread = client.get("/api/v1/conversations/current").json()
    assert thread["id"] == body["conversation_id"]
    assert [(m["role"], m["content"]) for m in thread["messages"]] == [
        ("user", "Salam"),
        ("assistant", "Salam! Necə kömək edə bilərəm?"),
    ]


def test_second_message_sees_the_history(client: TestClient) -> None:
    ai = ScriptedAI(Completion(text="Birinci"), Completion(text="İkinci"))
    use_ai(ai)

    first = client.post("/api/v1/chat", json={"message": "Bir"}).json()
    client.post("/api/v1/chat", json={"message": "İki", "conversation_id": first["conversation_id"]})

    roles_and_text = [(m.role, m.content) for m in ai.calls[1]]
    assert roles_and_text[1:] == [("user", "Bir"), ("assistant", "Birinci"), ("user", "İki")]


def test_chat_records_executed_actions_in_the_audit_log(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices
    use_ai(
        ScriptedAI(
            Completion(tool_calls=[ToolCall(id="c1", name="mac_open_app", arguments={"name": "TextEdit"})]),
            Completion(text="TextEdit açıldı."),
        )
    )

    body = client.post("/api/v1/chat", json={"message": "TextEdit aç"}).json()

    assert body["message"] == "TextEdit açıldı."
    assert [(a["tool"], a["ok"]) for a in body["actions"]] == [("mac_open_app", True)]
    assert socket.invocations[0]["capability"] == "open_app"

    activity = client.get("/api/v1/activity").json()
    assert [(entry["tool"], entry["ok"]) for entry in activity] == [("mac_open_app", True)]


def test_high_risk_action_waits_for_confirmation(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices
    use_ai(
        ScriptedAI(
            Completion(tool_calls=[ToolCall(id="c1", name="mac_run_command", arguments={"command": "ls"})]),
            Completion(text="Təsdiqləyirsən?"),
            Completion(text="Əmr işlədi."),
        )
    )

    body = client.post("/api/v1/chat", json={"message": "ls işlət"}).json()

    assert socket.invocations == []
    [pending] = body["pending"]
    assert pending["tool"] == "mac_run_command"
    assert pending["risk"] == "high"

    confirmed = client.post(f"/api/v1/actions/{pending['id']}/confirm").json()

    assert socket.invocations[0]["capability"] == "run_command"
    assert confirmed["message"] == "Əmr işlədi."
    assert [(a["tool"], a["ok"]) for a in confirmed["actions"]] == [("mac_run_command", True)]

    # An action can only be confirmed once.
    assert client.post(f"/api/v1/actions/{pending['id']}/confirm").status_code == 404


def test_cancelled_action_cannot_be_confirmed(client: TestClient, connected_mac) -> None:
    devices, socket = connected_mac
    app.dependency_overrides[get_device_actions] = lambda: devices
    use_ai(
        ScriptedAI(
            Completion(tool_calls=[ToolCall(id="c1", name="mac_run_command", arguments={"command": "ls"})]),
            Completion(text="Təsdiqləyirsən?"),
        )
    )
    [pending] = client.post("/api/v1/chat", json={"message": "ls işlət"}).json()["pending"]

    assert client.post(f"/api/v1/actions/{pending['id']}/cancel").status_code == 204
    assert client.post(f"/api/v1/actions/{pending['id']}/confirm").status_code == 404
    assert socket.invocations == []


def test_chat_without_api_key_returns_503(client: TestClient) -> None:
    use_ai(OpenAIService(api_key=None, model="test-model"))

    response = client.post("/api/v1/chat", json={"message": "Salam"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_chat_provider_failure_returns_502(client: TestClient) -> None:
    use_ai(BrokenAI())

    assert client.post("/api/v1/chat", json={"message": "Salam"}).status_code == 502


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}])
def test_chat_rejects_empty_message(client: TestClient, payload: dict[str, str]) -> None:
    use_ai(ScriptedAI())

    assert client.post("/api/v1/chat", json=payload).status_code == 422
