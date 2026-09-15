"""Tests for POST /v1/internal/canonical-finalization/run (2026-09-15,
HQ-authorized "CANONICAL SCHEDULE + FINALIZATION HARDENING").

The worker itself is covered directly in `tests/test_canonical_finalization.py`;
these cover only what is specific to the HTTP boundary: auth, response shape,
and -- the reason this endpoint exists separately from the MSF postgame
dispatcher at all -- that it runs and finalizes even while MSF ingestion is
paused for cost, since it never touches a provider.

No real network is used anywhere in this file, and no provider call is possible
from this path at all.
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


def _mock_one_completed_game():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "state-1",
                    "game_id": GAME_ID,
                    "provider_name": "mysportsfeeds",
                    "state": "confirmed_complete",
                    "raw_capture_id": "capture-1",
                    "captured_at": "2026-09-15T04:00:00+00:00",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "capture-1",
                    "raw_payload": {
                        "body": {
                            "game": {"playedStatus": "COMPLETED"},
                            "scoring": {"homeScoreTotal": 13, "awayScoreTotal": 10},
                        }
                    },
                }
            ],
        )
    )
    return respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": GAME_ID}])
    )


def test_run_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    assert client.post("/v1/internal/canonical-finalization/run").status_code == 401


@respx.mock
def test_run_finalizes_and_reports_per_game_outcomes(monkeypatch):
    _set_env(monkeypatch)
    _mock_one_completed_game()

    response = client.post(
        "/v1/internal/canonical-finalization/run", headers={"X-Internal-Token": "correct-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["considered"] == 1
    assert body["finalized"] == 1
    assert body["already_finalized"] == 0
    assert body["skipped"] == 0
    assert body["duplicate_captures_collapsed"] == 0
    assert body["failures"] == []
    assert body["outcomes"] == [
        {
            "game_id": GAME_ID,
            "status": "finalized",
            "final_score": {"home": 13, "away": 10},
            "reason": None,
        }
    ]


@respx.mock
def test_endpoint_makes_no_provider_calls_even_when_msf_is_not_paused(monkeypatch):
    """respx is strict here, so any non-Supabase host would raise."""
    _set_env(monkeypatch)
    monkeypatch.delenv("MSF_POSTGAME_ENABLED", raising=False)
    _mock_one_completed_game()

    client.post(
        "/v1/internal/canonical-finalization/run", headers={"X-Internal-Token": "correct-token"}
    )

    assert {call.request.url.host for call in respx.calls} == {"test-project.supabase.co"}


@respx.mock
def test_finalization_still_drains_the_backlog_while_msf_is_paused(monkeypatch):
    """This is why finalization is its own endpoint rather than a step inside
    `/v1/internal/msf-postgame/dispatch`: that dispatcher is a full zero-call
    no-op when `MSF_POSTGAME_ENABLED=false`, which would have silently stopped
    finalization too -- even though finalization costs nothing to run."""
    _set_env(monkeypatch)
    monkeypatch.setenv("MSF_POSTGAME_ENABLED", "false")
    patch_route = _mock_one_completed_game()

    response = client.post(
        "/v1/internal/canonical-finalization/run", headers={"X-Internal-Token": "correct-token"}
    )

    assert response.json()["finalized"] == 1
    assert patch_route.called
