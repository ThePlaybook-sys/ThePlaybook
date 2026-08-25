"""Tests for POST /v1/internal/recommendation-worker/finalize-strategy
(Milestone 5.1) -- the Strategy Engine's slate-level HTTP entry point.
`app.features.strategy`/`app.persistence.recommendation_products` are
thoroughly tested directly; these tests cover only what's specific to
this HTTP boundary: auth, request/response shape, and that the pure
decision + persistence pieces are actually wired together correctly."""
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


@respx.mock
def test_finalize_strategy_one_qualifying_candidate_is_single(monkeypatch):
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(201, json=[{"id": "leg-1"}]))

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


@respx.mock
def test_finalize_strategy_non_qualifying_candidate_is_no_bet(monkeypatch):
    _set_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))

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
