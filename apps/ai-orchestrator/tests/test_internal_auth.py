from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_internal_ping_requires_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    response = client.get("/v1/internal/ping")
    assert response.status_code == 401


def test_internal_ping_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    response = client.get(
        "/v1/internal/ping", headers={"X-Internal-Token": "wrong-token"}
    )
    assert response.status_code == 401


def test_internal_ping_rejects_a_user_jwt_in_the_internal_token_header(monkeypatch):
    # AC #3: a user JWT presented against an internal-only endpoint must be
    # rejected — it simply won't match the configured internal token.
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    fake_user_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.fakesignature"
    response = client.get(
        "/v1/internal/ping", headers={"X-Internal-Token": fake_user_jwt}
    )
    assert response.status_code == 401


def test_internal_ping_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    response = client.get(
        "/v1/internal/ping", headers={"X-Internal-Token": "correct-token"}
    )
    assert response.status_code == 200
    assert response.json()["scope"] == "internal"


def test_internal_ping_rejects_when_token_not_configured(monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    response = client.get(
        "/v1/internal/ping", headers={"X-Internal-Token": "anything"}
    )
    assert response.status_code == 500
