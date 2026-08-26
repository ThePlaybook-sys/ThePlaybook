"""Tests for app.orchestration.postgame_grading (Milestone 5.4) -- the
per-game grading orchestration: reconciliation-eligibility gating,
per-leg grading, product rollup, no_bet handling, and idempotent
worker-retry recovery, all against a mocked PostgREST."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.orchestration.postgame_grading import (
    RECONCILIATION_WINDOW_HOURS,
    grade_game,
    grade_pending_bankroll_preservation_products,
)

SUPABASE_URL = "https://test-project.supabase.co"
_NOW = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

_LEG_1 = {
    "id": "leg-1", "recommendation_product_id": "prod-single", "market_type": "moneyline",
    "selection": "KC", "point": None, "game_id": "game-1", "recommendation_id": "rec-1",
}


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _final_game(finalized_hours_ago: float, home="KC", away="BAL", status="final", home_score=27, away_score=24):
    finalized_at = (_NOW - timedelta(hours=finalized_hours_ago)).isoformat()
    return {
        "id": "game-1", "status": status, "home_team": home, "away_team": away,
        "final_score": {"home": home_score, "away": away_score} if status == "final" else None,
        "finalized_at": finalized_at if status == "final" else None,
    }


def _mock_common(*, game: dict, legs: list[dict], no_bet_products: list[dict] | None = None):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=legs))

    def _products_responder(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("recommendation_type") == "eq.no_bet":
            return httpx.Response(200, json=no_bet_products or [])
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(side_effect=_products_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(201, json=[{"id": "leg-grade-x"}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(201, json=[{"id": "prod-grade-x"}]))


@pytest.mark.asyncio
@respx.mock
async def test_game_not_yet_reconciliation_eligible_skips_legs_but_grades_no_bet():
    _mock_common(
        game=_final_game(finalized_hours_ago=1), legs=[_LEG_1],
        no_bet_products=[{"id": "prod-nobet", "recommendation_type": "no_bet"}],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="game-1", now=_NOW)

    assert result.status == "graded"
    assert result.legs[0].status == "skipped_not_eligible"
    assert result.no_bet_products[0].outcome == "NOT_APPLICABLE"
    assert result.no_bet_products[0].status == "created"


@pytest.mark.asyncio
@respx.mock
async def test_reconciliation_eligible_moneyline_win_rolls_up_single_product():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[_final_game(finalized_hours_ago=RECONCILIATION_WINDOW_HOURS + 1)])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[_LEG_1]))

    def _products_responder(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("recommendation_type") == "eq.no_bet":
            return httpx.Response(200, json=[])
        if params.get("id") == "eq.prod-single":
            return httpx.Response(200, json=[{"id": "prod-single", "recommendation_type": "single"}])
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(side_effect=_products_responder)
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(return_value=httpx.Response(201, json=[{"id": "leg-grade-1"}]))

    def _leg_grade_events_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": "leg-grade-1", "outcome": "WIN", "authoritative_result": {}, "is_correction": False}])

    # First read (inside persist_leg_grade, before insert) sees nothing yet;
    # subsequent reads (rollup's own lookup) see the just-created grade.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events").mock(
        side_effect=[httpx.Response(200, json=[]), httpx.Response(200, json=[{"id": "leg-grade-1", "outcome": "WIN", "authoritative_result": {}, "is_correction": False}])]
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))

    captured = {}

    def _product_grade_post(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "prod-grade-1"}])

    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(side_effect=_product_grade_post)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="game-1", now=_NOW)

    assert result.legs[0].outcome == "WIN"
    assert result.legs[0].status == "created"
    assert len(result.products) == 1
    assert result.products[0].outcome == "WIN"
    assert captured["body"]["outcome"] == "WIN"
    assert captured["body"]["leg_outcome_counts"] is None


@pytest.mark.asyncio
@respx.mock
async def test_postponed_game_grades_legs_void_immediately_no_wait():
    _mock_common(game=_final_game(finalized_hours_ago=0, status="postponed"), legs=[_LEG_1])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="game-1", now=_NOW)

    assert result.legs[0].outcome == "VOID_NO_ACTION"
    assert result.legs[0].status == "created"


@pytest.mark.asyncio
@respx.mock
async def test_prop_market_is_skipped_never_fabricated():
    prop_leg = {**_LEG_1, "market_type": "prop", "selection": "Player X Over 249.5", "point": 249.5}
    _mock_common(game=_final_game(finalized_hours_ago=RECONCILIATION_WINDOW_HOURS + 1), legs=[prop_leg])
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_leg_grade_events")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="game-1", now=_NOW)

    assert result.legs[0].status == "skipped_unsupported_market"
    assert post_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_malformed_selection_is_isolated_as_failed_not_fatal():
    bad_leg = {**_LEG_1, "selection": "NOT_A_REAL_TEAM"}
    _mock_common(game=_final_game(finalized_hours_ago=RECONCILIATION_WINDOW_HOURS + 1), legs=[bad_leg])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="game-1", now=_NOW)
    assert result.legs[0].status == "failed"
    assert result.legs[0].error is not None


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_sweep_grades_not_applicable():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[{"id": "prod-bp"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(return_value=httpx.Response(201, json=[{"id": "pgrade-bp"}]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        results = await grade_pending_bankroll_preservation_products(client, _headers())

    assert len(results) == 1
    assert results[0].outcome == "NOT_APPLICABLE"
    assert results[0].status == "created"


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_sweep_is_idempotent():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[{"id": "prod-bp"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events").mock(
        return_value=httpx.Response(200, json=[{"id": "pgrade-bp", "outcome": "NOT_APPLICABLE", "leg_outcome_counts": None, "is_correction": False}])
    )
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_product_grade_events")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        results = await grade_pending_bankroll_preservation_products(client, _headers())

    assert results[0].status == "unchanged"
    assert post_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_game_not_found_returns_safe_status():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await grade_game(client, _headers(), game_id="ghost", now=_NOW)
    assert result.status == "game_not_found"
