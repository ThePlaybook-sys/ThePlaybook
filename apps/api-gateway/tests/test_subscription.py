"""Tests for GET /v1/user/subscription (Phase 6 Milestone 2). Own-tier
read only -- never fabricates a 'free' tier for a user with no
subscription row (HQ Final Decision 9 / app.entitlement's own rule)."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "22222222-2222-2222-2222-222222222222"


def _mock_authenticated_user() -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": "NJ"}])
    )


@respx.mock
def test_subscription_requires_authentication():
    response = client.get("/v1/user/subscription")
    assert response.status_code == 401


@respx.mock
def test_subscription_returns_null_when_no_row_exists():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))

    response = client.get("/v1/user/subscription", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"tier": None, "status": None, "billingPeriod": None, "currentPeriodEnd": None}


@respx.mock
def test_subscription_returns_own_active_tier():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "tier": "pro",
                    "status": "active",
                    "billing_period": "monthly",
                    "current_period_end": "2026-09-28T00:00:00Z",
                }
            ],
        )
    )

    response = client.get("/v1/user/subscription", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "pro"
    assert body["status"] == "active"
    assert body["billingPeriod"] == "monthly"
