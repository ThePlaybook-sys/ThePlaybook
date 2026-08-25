"""Tests for POST /v1/internal/recommendation-worker/finalize-strategy
(Milestone 5.1/5.2) -- the Strategy Engine's slate-level HTTP entry point,
now also driving Explainability generation immediately afterward.
`app.features.strategy`/`app.persistence.recommendation_products`/
`app.features.explainability`/`app.orchestration.explainability` are
thoroughly tested directly; these tests cover only what's specific to
this HTTP boundary: auth, request/response shape, and that the pure
decision + persistence + explanation pieces are actually wired together
correctly end to end."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _candidate(**overrides) -> dict:
    payload = {
        "game_id": "g1",
        "recommendation_id": "rec-1",
        "consensus_snapshot_id": "snap-1",
        "candidate_key": "g1:draftkings:moneyline:Home Team:none",
        "market_type": "moneyline",
        "selection": "Home Team",
        "sportsbook": "draftkings",
        "american_odds": -110,
        "point": None,
        "decimal_odds": 1.909,
        "ev_per_dollar": 0.05,
        "final_aggregate_confidence": 0.71,
    }
    payload.update(overrides)
    return payload


def _mock_explanation_reads():
    """Everything `app.orchestration.explainability` reads back, mocked
    to their honest "nothing extra available" shape -- these tests exist
    to prove the wiring succeeds and produces the right counts, not to
    exercise every content-generation branch (covered directly in
    `tests/features/test_explainability.py`)."""
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "home_team": "Home Team", "away_team": "Away Team"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": _candidate()["candidate_key"]}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-expl-1"}])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-expl-1"}])
    )


def test_finalize_strategy_requires_internal_token(monkeypatch):
    _set_env(monkeypatch)
    response = client.post(
        "/v1/internal/recommendation-worker/finalize-strategy",
        json={"master_refresh_run_id": "run-1", "games": []},
    )
    assert response.status_code == 401


@respx.mock
def test_finalize_strategy_zero_games_is_bankroll_preservation(monkeypatch):
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    _mock_explanation_reads()

    response = client.post(
        "/v1/internal/recommendation-worker/finalize-strategy",
        headers={"X-Internal-Token": "correct-token"},
        json={"master_refresh_run_id": "run-1", "games": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "bankroll_preservation"
    assert body["recommendation_product_ids"] == ["prod-1"]
    assert body["leg_count"] == 0
    assert body["no_bet_game_count"] == 0
    assert body["explanations_generated"] == 1  # the one bankroll_preservation product
    assert body["explanations_failed"] == 0


@respx.mock
def test_finalize_strategy_one_qualifying_candidate_is_single(monkeypatch):
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(201, json=[{"id": "leg-1"}]))
    _mock_explanation_reads()

    response = client.post(
        "/v1/internal/recommendation-worker/finalize-strategy",
        headers={"X-Internal-Token": "correct-token"},
        json={
            "master_refresh_run_id": "run-1",
            "games": [{"game_id": "g1", "recommendation_id": "rec-1", "candidates": [_candidate()]}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "single"
    assert body["leg_count"] == 1
    assert body["no_bet_game_count"] == 0
    assert body["explanations_generated"] == 2  # 1 product + 1 leg
    assert body["explanations_failed"] == 0


@respx.mock
def test_finalize_strategy_non_qualifying_candidate_is_no_bet(monkeypatch):
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    _mock_explanation_reads()

    response = client.post(
        "/v1/internal/recommendation-worker/finalize-strategy",
        headers={"X-Internal-Token": "correct-token"},
        json={
            "master_refresh_run_id": "run-1",
            "games": [
                {
                    "game_id": "g1",
                    "recommendation_id": "rec-1",
                    "candidates": [_candidate(final_aggregate_confidence=0.40)],  # below the 0.55 floor
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "bankroll_preservation"
    assert body["no_bet_game_count"] == 1
    assert body["explanations_generated"] == 2  # the no_bet product + the bankroll_preservation product
    assert body["explanations_failed"] == 0


@respx.mock
def test_finalize_strategy_isolates_explanation_failure_from_the_response(monkeypatch):
    """If an explanation read fails, the Strategy decision itself must
    still be reported successfully -- explanation generation is
    downstream and its failure must never un-persist or hide the
    already-committed decision."""
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(return_value=httpx.Response(500, text="db error"))

    response = client.post(
        "/v1/internal/recommendation-worker/finalize-strategy",
        headers={"X-Internal-Token": "correct-token"},
        json={"master_refresh_run_id": "run-1", "games": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "bankroll_preservation"
    assert body["recommendation_product_ids"] == ["prod-1"]
    assert body["explanations_generated"] == 0
    assert body["explanations_failed"] == 1
