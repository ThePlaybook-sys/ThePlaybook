import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH_URL = "https://test-project.supabase.co/auth/v1/user"
PROFILE_URL = "https://test-project.supabase.co/rest/v1/user_profiles"
USER_ID = "22222222-2222-2222-2222-222222222222"


def _mock_authenticated_user():
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(PROFILE_URL).mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": None}])
    )


# AC #4: "Attempting to complete onboarding without a jurisdiction value is
# blocked with a clear message, not a silent failure."


@respx.mock
def test_onboarding_without_jurisdiction_returns_422_with_clear_message():
    _mock_authenticated_user()
    response = client.patch(
        "/v1/user/profile",
        headers={"Authorization": "Bearer validtoken"},
        json={"display_name": "Test User"},
    )
    assert response.status_code == 422
    body = response.json()
    assert any("jurisdiction_state" in str(err.get("loc", "")) for err in body["detail"])


@respx.mock
def test_onboarding_with_blank_jurisdiction_returns_422():
    _mock_authenticated_user()
    response = client.patch(
        "/v1/user/profile",
        headers={"Authorization": "Bearer validtoken"},
        json={"jurisdiction_state": ""},
    )
    assert response.status_code == 422


@respx.mock
def test_onboarding_with_jurisdiction_succeeds():
    _mock_authenticated_user()
    respx.patch(PROFILE_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": USER_ID,
                    "jurisdiction_state": "NJ",
                    "onboarding_completed_at": "2026-08-09T00:00:00Z",
                }
            ],
        )
    )
    response = client.patch(
        "/v1/user/profile",
        headers={"Authorization": "Bearer validtoken"},
        json={"jurisdiction_state": "NJ"},
    )
    assert response.status_code == 200
    assert response.json()["jurisdiction_state"] == "NJ"
    assert response.json()["onboarding_completed_at"] is not None


@respx.mock
def test_onboarding_requires_authentication():
    response = client.patch("/v1/user/profile", json={"jurisdiction_state": "NJ"})
    assert response.status_code == 401
