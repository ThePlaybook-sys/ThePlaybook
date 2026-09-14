"""Tests for POST /v1/internal/msf-postgame/run (Permanent Box Score
Worker Build, 2026-09-11 + SF@LAR Live Proof, 2026-09-13) -- the HTTP
boundary `app.workers.msf_postgame_worker.run_msf_postgame_capture`
never had before this pass. That worker is already thoroughly tested
directly (`tests/test_msf_postgame_worker.py`); these tests cover only
what's specific to this HTTP boundary: auth, request/response shape, and
that a real call constructs the real worker (not a stub). Every HTTP
boundary is respx-mocked, including MySportsFeeds itself (via the
worker's own real `_default_fetch_boxscore` path) -- no real network is
used anywhere in this file, and this test suite never spends a real
MySportsFeeds call.
"""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")
    monkeypatch.delenv("MYSPORTSFEEDS_API_KEY", raising=False)


def test_run_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/msf-postgame/run", json={"game_id": GAME_ID})
    assert response.status_code == 401


@respx.mock
def test_run_missing_msf_credential_reports_permanent_failure_not_a_crash(monkeypatch):
    """No `MYSPORTSFEEDS_API_KEY` configured -- the real worker's own
    `_default_fetch_boxscore` reports this as a clean permanent_error
    result, never a raw exception through this HTTP boundary."""
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"state": "eligible_for_postgame_check", "attempt_count": 0}])
    )
    respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"provider_game_id": "163542"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "league-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2020-01-01", "end_date": "2030-01-01"}])
    )

    response = client.post(
        "/v1/internal/msf-postgame/run",
        json={"game_id": GAME_ID},
        headers={"X-Internal-Token": "correct-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == GAME_ID
    assert body["outcome"] == "capture_failed_permanent"
    assert body["error"] == "MYSPORTSFEEDS_API_KEY is not configured"


def test_run_rejects_missing_game_id(monkeypatch):
    _set_env(monkeypatch)
    response = client.post(
        "/v1/internal/msf-postgame/run", json={}, headers={"X-Internal-Token": "correct-token"}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# POST /v1/internal/msf-postgame/dispatch (Postgame Dispatcher + Sunday
# Recovery, 2026-09-14) -- `dispatch_due_msf_postgame_games` itself is
# already fully tested directly (test_msf_postgame_dispatcher.py); these
# tests cover only the HTTP boundary: auth and response shape.
# --------------------------------------------------------------------------


def test_dispatch_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post("/v1/internal/msf-postgame/dispatch")
    assert response.status_code == 401


def test_dispatch_shapes_response_from_real_dispatch_result(monkeypatch):
    _set_env(monkeypatch)

    from app.workers.msf_postgame_dispatcher import DispatchResult
    from app.workers.msf_postgame_worker import MSFPostgameCaptureResult

    async def _fake_dispatch(supabase_client, **kwargs):
        return DispatchResult(
            considered=2,
            selected_game_ids=["g1", "g2"],
            invoked_game_ids=["g1"],
            results=[
                MSFPostgameCaptureResult(
                    game_id="g1", outcome="confirmed_complete", state="confirmed_complete",
                    attempt_count=1, resolved_players=95, quarantined_players=0,
                    persisted_rows=95, unchanged_rows=0,
                )
            ],
        )

    import app.main
    monkeypatch.setattr(app.main, "dispatch_due_msf_postgame_games", _fake_dispatch)

    response = client.post("/v1/internal/msf-postgame/dispatch", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["considered"] == 2
    assert body["selected_game_ids"] == ["g1", "g2"]
    assert body["invoked_game_ids"] == ["g1"]
    assert len(body["results"]) == 1
    assert body["results"][0]["outcome"] == "confirmed_complete"
    assert body["results"][0]["resolved_players"] == 95


def test_dispatch_with_nothing_due_returns_empty_results(monkeypatch):
    _set_env(monkeypatch)

    from app.workers.msf_postgame_dispatcher import DispatchResult

    async def _fake_dispatch(supabase_client, **kwargs):
        return DispatchResult(considered=0, selected_game_ids=[], invoked_game_ids=[], results=[])

    import app.main
    monkeypatch.setattr(app.main, "dispatch_due_msf_postgame_games", _fake_dispatch)

    response = client.post("/v1/internal/msf-postgame/dispatch", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"considered": 0, "selected_game_ids": [], "invoked_game_ids": [], "results": []}
