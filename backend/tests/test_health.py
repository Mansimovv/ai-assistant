from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_describes_api(client: TestClient) -> None:
    """The web client reads the assistant's name from here."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == get_settings().app_name
