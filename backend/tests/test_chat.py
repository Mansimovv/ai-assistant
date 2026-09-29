import pytest
from fastapi.testclient import TestClient

from app.ai.service import AIService, AIServiceError, ChatMessage, OpenAIService
from app.api.deps import get_ai_service
from app.main import app


class FakeAIService(AIService):
    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.messages: list[ChatMessage] = []

    async def complete(self, messages: list[ChatMessage]) -> str:
        self.messages = messages
        if self.error:
            raise self.error
        return self.reply


def test_chat_returns_model_reply(client: TestClient) -> None:
    ai = FakeAIService(reply="Hello! How can I help you?")
    app.dependency_overrides[get_ai_service] = lambda: ai

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"message": "Hello! How can I help you?"}
    assert ai.messages[0].role == "system"
    assert ai.messages[-1] == ChatMessage(role="user", content="Hello")


def test_chat_without_api_key_returns_503(client: TestClient) -> None:
    app.dependency_overrides[get_ai_service] = lambda: OpenAIService(api_key=None, model="test-model")

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_chat_provider_failure_returns_502(client: TestClient) -> None:
    app.dependency_overrides[get_ai_service] = lambda: FakeAIService(error=AIServiceError("boom"))

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 502


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}])
def test_chat_rejects_empty_message(client: TestClient, payload: dict[str, str]) -> None:
    app.dependency_overrides[get_ai_service] = lambda: FakeAIService(reply="unused")

    response = client.post("/api/v1/chat", json=payload)

    assert response.status_code == 422
