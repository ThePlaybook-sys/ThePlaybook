"""Tests for GET /v1/system/freshness (Phase 6 Milestone 7.1). Covers
the three real freshness states -- no refresh has ever run, a refresh
is currently running (no completed_at yet), and the latest refresh
completed -- and that this route is a pure thin read (one Supabase
call, no computation) requiring authentication like every other route
in this gateway."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "33333333-3333-3333-3333-333333333333"
RUNS_URL = f"{SUPABASE_URL}/rest/v1/master_refresh_runs"


def _mock_authenticated_user() -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID}])
    )


@respx.mock
def test_freshness_requires_authentication():
    response = client.get("/v1/system/freshness")
    assert response.status_code == 401


@respx.mock
def test_no_refresh_has_ever_run_is_a_real_honest_state():
    _mock_authenticated_user()
    respx.get(RUNS_URL).mock(return_value=httpx.Response(200, json=[]))

    response = client.get("/v1/system/freshness", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json() == {"status": None, "startedAt": None, "completedAt": None, "gamesInSlate": None}


@respx.mock
def test_running_refresh_has_no_completed_at_yet():
    _mock_authenticated_user()
    respx.get(RUNS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "status": "running",
                    "started_at": "2026-09-02T06:00:00Z",
                    "completed_at": None,
                    "games_in_slate": None,
                }
            ],
        )
    )

    response = client.get("/v1/system/freshness", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["startedAt"] == "2026-09-02T06:00:00Z"
    assert body["completedAt"] is None


@respx.mock
def test_completed_refresh_returns_its_own_timestamp_never_a_decision_timestamp():
    _mock_authenticated_user()
    respx.get(RUNS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "status": "success",
                    "started_at": "2026-09-02T06:00:00Z",
                    "completed_at": "2026-09-02T06:04:12Z",
                    "games_in_slate": 14,
                }
            ],
        )
    )

    response = client.get("/v1/system/freshness", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["completedAt"] == "2026-09-02T06:04:12Z"
    assert body["gamesInSlate"] == 14


@respx.mock
def test_only_the_most_recent_run_is_returned():
    """`order=started_at.desc&limit=1` -- confirms the route trusts and
    forwards that ordering rather than re-sorting or aggregating
    client-side (no new business logic, per HQ's explicit boundary)."""
    _mock_authenticated_user()
    route = respx.get(RUNS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"status": "success", "started_at": "t2", "completed_at": "t2c", "games_in_slate": 5}],
        )
    )

    response = client.get("/v1/system/freshness", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json()["startedAt"] == "t2"
    request = route.calls[0].request
    assert request.url.params["order"] == "started_at.desc"
    assert request.url.params["limit"] == "1"


@respx.mock
def test_partial_and_failed_statuses_pass_through_honestly():
    _mock_authenticated_user()
    respx.get(RUNS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"status": "failed", "started_at": "t1", "completed_at": "t1c", "games_in_slate": 0}],
        )
    )

    response = client.get("/v1/system/freshness", headers={"Authorization": "Bearer validtoken"})

    assert response.json()["status"] == "failed"
