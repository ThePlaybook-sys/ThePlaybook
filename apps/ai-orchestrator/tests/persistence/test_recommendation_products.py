"""Tests for app.persistence.recommendation_products (Milestone 5.1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.features.strategy import EvaluatedCandidate, GameDecision, SlateStrategyResult
from app.persistence.recommendation_products import (
    RecommendationProductsError,
    generate_display_id,
    persist_strategy_decision,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _leg(**overrides) -> EvaluatedCandidate:
    defaults = dict(
        game_id="g1",
        recommendation_id="rec-1",
        consensus_snapshot_id="snap-1",
        candidate_key="g1:draftkings:moneyline:Home Team:none",
        market_type="moneyline",
        selection="Home Team",
        sportsbook="draftkings",
        american_odds=-110,
        point=None,
        decimal_odds=1.909,
        ev_per_dollar=0.05,
        final_aggregate_confidence=0.71,
    )
    defaults.update(overrides)
    return EvaluatedCandidate(**defaults)


# --- generate_display_id ---


@pytest.mark.asyncio
@respx.mock
async def test_generate_display_id_calls_rpc_with_year_bucket_and_formats_result():
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=7))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        display_id = await generate_display_id(client, _headers(), now=datetime(2026, 8, 25, tzinfo=timezone.utc))
    assert display_id == "2026-00007"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"p_bucket_key": "2026"}


@pytest.mark.asyncio
@respx.mock
async def test_generate_display_id_raises_on_non_200():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(500, text="db error"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationProductsError):
            await generate_display_id(client, _headers(), now=datetime(2026, 8, 25, tzinfo=timezone.utc))


# --- persist_strategy_decision: one path per Strategy outcome ---


@pytest.mark.asyncio
@respx.mock
async def test_no_bet_games_get_a_product_with_zero_legs_and_no_fake_provenance():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    products_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-1"}])
    )
    legs_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs")

    decision = SlateStrategyResult(
        outcome="bankroll_preservation",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="no_bet", legs=()),),
        legs=(),
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        created = await persist_strategy_decision(
            client, _headers(), master_refresh_run_id="run-1", decision=decision, now=datetime(2026, 8, 25, tzinfo=timezone.utc)
        )

    assert created == ["prod-1", "prod-1"]  # one no_bet product + one bankroll_preservation product
    assert legs_route.call_count == 0
    sent_payloads = [json.loads(c.request.content) for c in products_route.calls]
    no_bet_payload = next(p for p in sent_payloads if p["recommendation_type"] == "no_bet")
    assert no_bet_payload["scope"] == "game"
    assert no_bet_payload["game_id"] == "g1"
    assert no_bet_payload["recommendation_id"] == "rec-1"
    assert no_bet_payload["master_refresh_run_id"] == "run-1"


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_product_has_no_game_or_recommendation_id():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    products_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(201, json=[{"id": "prod-1"}])
    )

    decision = SlateStrategyResult(outcome="bankroll_preservation", game_decisions=(), legs=())
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        created = await persist_strategy_decision(
            client, _headers(), master_refresh_run_id="run-1", decision=decision, now=datetime(2026, 8, 25, tzinfo=timezone.utc)
        )

    assert created == ["prod-1"]
    payload = json.loads(products_route.calls.last.request.content)
    assert payload["recommendation_type"] == "bankroll_preservation"
    assert payload["scope"] == "slate"
    assert payload["game_id"] is None
    assert payload["recommendation_id"] is None


@pytest.mark.asyncio
@respx.mock
async def test_single_outcome_creates_one_product_and_exactly_one_leg():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    legs_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-1"}])
    )

    leg = _leg()
    decision = SlateStrategyResult(
        outcome="single",
        game_decisions=(GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(leg,)),),
        legs=(leg,),
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        created = await persist_strategy_decision(
            client, _headers(), master_refresh_run_id="run-1", decision=decision, now=datetime(2026, 8, 25, tzinfo=timezone.utc)
        )

    assert created == ["prod-1"]
    assert legs_route.call_count == 1
    leg_payload = json.loads(legs_route.calls.last.request.content)
    assert leg_payload["recommendation_product_id"] == "prod-1"
    assert leg_payload["leg_order"] == 1
    assert leg_payload["candidate_key"] == leg.candidate_key
    assert leg_payload["consensus_snapshot_id"] == "snap-1"


@pytest.mark.asyncio
@respx.mock
async def test_multiple_singles_creates_one_product_and_n_legs_in_order():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(201, json=[{"id": "prod-1"}]))
    legs_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(201, json=[{"id": "leg-x"}])
    )

    strong = _leg(candidate_key="strong", ev_per_dollar=0.09)
    weak = _leg(candidate_key="weak", ev_per_dollar=0.02, game_id="g2", market_type="total", selection="Over")
    decision = SlateStrategyResult(
        outcome="multiple_singles",
        game_decisions=(
            GameDecision(game_id="g1", recommendation_id="rec-1", outcome="qualified", legs=(strong,)),
            GameDecision(game_id="g2", recommendation_id="rec-2", outcome="qualified", legs=(weak,)),
        ),
        legs=(strong, weak),  # already ranked by the Strategy Engine
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        created = await persist_strategy_decision(
            client, _headers(), master_refresh_run_id="run-1", decision=decision, now=datetime(2026, 8, 25, tzinfo=timezone.utc)
        )

    assert created == ["prod-1"]
    assert legs_route.call_count == 2
    leg_orders = [json.loads(c.request.content)["leg_order"] for c in legs_route.calls]
    assert leg_orders == [1, 2]
    candidate_keys = [json.loads(c.request.content)["candidate_key"] for c in legs_route.calls]
    assert candidate_keys == ["strong", "weak"]


@pytest.mark.asyncio
@respx.mock
async def test_product_insert_failure_raises_recommendation_products_error():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/next_display_id_counter").mock(return_value=httpx.Response(200, json=1))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(500, text="db error"))

    decision = SlateStrategyResult(outcome="bankroll_preservation", game_decisions=(), legs=())
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(RecommendationProductsError):
            await persist_strategy_decision(
                client, _headers(), master_refresh_run_id="run-1", decision=decision, now=datetime(2026, 8, 25, tzinfo=timezone.utc)
            )
