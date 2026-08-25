"""Tests for POST /v1/internal/recommendation-worker/run-game (Milestone
4.9) -- the Recommendation Worker's own internal HTTP entry point.
`app.orchestration.recommendation_worker` itself is thoroughly tested
directly (`tests/orchestration/test_recommendation_worker.py`); these
tests cover only what's specific to this HTTP boundary: auth,
request/response shape, and error translation."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import mock_prompt_registry_route

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"

TASK_TYPES = (
    "injury_analysis", "weather_analysis", "vegas_line_analysis", "closing_line_movement_analysis",
    "travel_fatigue_analysis", "rest_days_analysis", "probability_modeling_analysis", "expected_value_analysis",
    "risk_manager_analysis", "bankroll_coach_analysis", "meta_agent_review", "consensus_reconciliation",
)


def _routing_rule_rows() -> list[dict]:
    return [
        {"id": f"rr-{t}", "task_type": t, "primary_model": "claude-sonnet-5", "fallback_model": None, "min_tier_for_second_pass": None, "active": True}
        for t in TASK_TYPES
    ]


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_run_game_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post(
        "/v1/internal/recommendation-worker/run-game",
        json={"game_id": "g1", "correlation_id": "corr-1", "prompt_version": "v1", "agent_version": "v1"},
    )
    assert response.status_code == 401


@respx.mock
def test_run_game_returns_404_when_game_not_found(monkeypatch):
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(return_value=httpx.Response(200, json=_routing_rule_rows()))
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    response = client.post(
        "/v1/internal/recommendation-worker/run-game",
        headers={"X-Internal-Token": "correct-token"},
        json={"game_id": "ghost", "correlation_id": "corr-1", "prompt_version": "v1", "agent_version": "v1"},
    )
    assert response.status_code == 404


@respx.mock
def test_run_game_success_round_trip_with_no_qualifying_sportsbook(monkeypatch):
    """Zero `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` configured (this test's
    default, matching CI/local dev where no live keys exist) -- the
    endpoint still builds and returns a real response; every LLM-calling
    step degrades to an isolated per-agent/per-candidate failure rather
    than the endpoint itself erroring out. Uses the "no odds data"
    shortcut (candidate generation skips the whole game) to keep this
    round-trip's mock surface small -- the full multi-candidate pipeline
    is already covered directly against `run_game_recommendation`."""
    _set_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/model_routing_rules").mock(return_value=httpx.Response(200, json=_routing_rule_rows()))
    respx.get(f"{SUPABASE_URL}/rest/v1/model_registry").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{
            "id": "g1", "status": "scheduled", "scheduled_start": "2026-09-21T20:00:00+00:00",
            "home_team": "KC", "away_team": "BAL", "season_type": "regular", "week": 3,
            "venue_lat": None, "venue_long": None, "stadium": None, "venue_type": None,
        }])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    mock_prompt_registry_route(SUPABASE_URL)

    response = client.post(
        "/v1/internal/recommendation-worker/run-game",
        headers={"X-Internal-Token": "correct-token"},
        json={"game_id": "g1", "correlation_id": "corr-1", "prompt_version": "v1", "agent_version": "v1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation_id"] == "r1"
    assert body["game_skipped_reason"] == "no_configured_sportsbook_has_fresh_data"
    assert body["candidates"] == []
