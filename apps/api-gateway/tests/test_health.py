from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api-gateway"}


def test_deliberately_failing_tr1():
    # TR1 verification: this test is intentionally wrong and will be
    # reverted immediately after confirming it blocks deploy-dev.
    assert False
