import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH_URL = "https://test-project.supabase.co/auth/v1/user"
PROFILE_URL = "https://test-project.supabase.co/rest/v1/user_profiles"


def test_missing_authorization_header_returns_401():
    response = client.get("/v1/user/profile")
    assert response.status_code == 401


def test_malformed_authorization_header_returns_401():
    response = client.get("/v1/user/profile", headers={"Authorization": "NotBearer xyz"})
    assert response.status_code == 401


def test_empty_bearer_token_returns_401():
    response = client.get("/v1/user/profile", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


@respx.mock
def test_tampered_or_invalid_token_rejected_by_supabase_returns_401():
    # Simulates what Supabase Auth's own /auth/v1/user endpoint returns for a
    # signature-invalid, tampered, or expired token — it rejects with 401 itself.
    respx.get(AUTH_URL).mock(return_value=httpx.Response(401, json={"msg": "invalid JWT"}))
    response = client.get(
        "/v1/user/profile", headers={"Authorization": "Bearer tampered.token.value"}
    )
    assert response.status_code == 401


@respx.mock
def test_supabase_auth_network_error_returns_401_not_500():
    respx.get(AUTH_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    response = client.get("/v1/user/profile", headers={"Authorization": "Bearer sometoken"})
    assert response.status_code == 401


@respx.mock
def test_valid_token_for_deleted_user_returns_401():
    respx.get(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"id": "11111111-1111-1111-1111-111111111111"})
    )
    respx.get(PROFILE_URL).mock(return_value=httpx.Response(200, json=[]))
    response = client.get("/v1/user/profile", headers={"Authorization": "Bearer validtoken"})
    assert response.status_code == 401


@respx.mock
def test_valid_token_for_existing_user_returns_200_with_profile():
    user_id = "11111111-1111-1111-1111-111111111111"
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": user_id}))
    respx.get(PROFILE_URL).mock(
        return_value=httpx.Response(
            200, json=[{"id": user_id, "jurisdiction_state": None, "display_name": None}]
        )
    )
    response = client.get("/v1/user/profile", headers={"Authorization": "Bearer validtoken"})
    assert response.status_code == 200
    assert response.json()["id"] == user_id
