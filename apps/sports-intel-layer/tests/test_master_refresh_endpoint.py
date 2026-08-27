"""Tests for POST /v1/internal/master-refresh/run (Pre-Phase-6
Operational Readiness Gate, Decision 6) -- the HTTP boundary this project
never had before this gate (Finding 1 of the preceding STOP report).
`app.master_refresh.run.run_master_refresh` is already thoroughly tested
directly (`tests/test_master_refresh.py`); these tests cover only what's
specific to this HTTP boundary: auth and the real construction of
`SportsDataIOScheduleAdapter`/`SportsDataIORosterAdapter` from env vars
(no injected fixture adapter, unlike Demo Mode's own caller in
`app.demo.runner`). Every HTTP boundary -- Supabase and SportsDataIO
both -- is respx-mocked; no real network is used anywhere in this file,
and this test suite never spends the project's real SportsDataIO call
budget."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("SPORTSDATAIO_API_KEY", "test-sportsdataio-key")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")


def _mock_season_wide_range():
    """A season row spanning a wide, fixed range -- avoids coupling this
    HTTP-boundary test to the real wall-clock date this suite happens to
    run on (unlike `test_master_refresh.py`'s own tests, which inject an
    explicit `today` this endpoint deliberately never accepts -- see
    `app.main.internal_run_master_refresh`'s own docstring)."""
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-nfl"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2020-01-01", "end_date": "2030-01-01"}])
    )


def _mock_master_refresh_runs():
    respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(201, json=[{"id": "mrr-1"}])
    )
    respx.patch(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(204))


def test_run_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/master-refresh/run")
    assert response.status_code == 401


@respx.mock
def test_run_empty_slate_round_trip_uses_real_sportsdataio_key(monkeypatch):
    """A real, respx-intercepted call to the real SportsDataIO base URL
    (`https://api.sportsdata.io`), authenticated with the real
    `SPORTSDATAIO_API_KEY` env var this endpoint reads -- proving the
    endpoint wires a genuine `SportsDataIOScheduleAdapter` (no injected
    fixture adapter), never that a real call was actually spent against
    the live provider (respx intercepts before any request leaves this
    process)."""
    _set_env(monkeypatch)
    _mock_season_wide_range()
    _mock_master_refresh_runs()
    schedule_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[])
    )

    response = client.post("/v1/internal/master-refresh/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["run_id"] == "mrr-1"
    assert body["games_in_slate"] == 0
    assert body["error"] is None
    assert schedule_route.calls.last.request.headers["Ocp-Apim-Subscription-Key"] == "test-sportsdataio-key"
