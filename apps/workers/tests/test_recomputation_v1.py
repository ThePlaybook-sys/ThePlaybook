"""Recomputation V1 (HQ owner decision, 2026-09-18).

Two rules, both about *paid* inference and neither about scoring:

1. **First paid run window** -- a game may enter its first paid cycle only
   within 36 hours of kickoff. An additional gate on expensive inference,
   layered on top of (not replacing) the canonical 7-day horizon.
2. **One successful paid cycle per canonical game** -- and `run_id` is
   explicitly not the reason a game becomes eligible again.

The loop rule 2 closes is real and measured: `correlation_id` is
`f"{master_refresh_run_id}:{game_id}"`, and dev accumulated three
`master_refresh_runs` rows on three consecutive days. Each new day minted a
fresh correlation, found no prior row, and would have re-run the full
committee on identical evidence -- roughly 7x the necessary spend across a
horizon, driven by days passing rather than anything changing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from conftest import COMPLETED_PAID_CYCLES_GET, release_default_route

from app.persistence.games import FIRST_PAID_RUN_WINDOW_HOURS, read_eligible_game_ids
from app.persistence.recommendations import read_game_ids_with_completed_paid_cycle
from app.recommendation_worker import run_recommendation_worker_cycle

SUPABASE_URL = "https://test-project.supabase.co"
AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"apikey": "k", "Authorization": "Bearer k"}


def _sent_scheduled_start_bounds(route) -> list[str]:
    url = httpx.URL(str(route.calls[0].request.url))
    return [v for k, v in url.params.multi_items() if k == "scheduled_start"]


# ------------------------------------------------------------ 1, 2, 3
# The 36-hour first-paid-run window.


@pytest.mark.asyncio
@respx.mock
async def test_37h_before_kickoff_is_outside_the_paid_window():
    """VERIFY 1 -- 37h out yields zero LLM, because the query never
    returns the game."""
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await read_eligible_game_ids(client, _headers(), now=NOW)

    assert result == []
    cutoff = NOW + timedelta(hours=FIRST_PAID_RUN_WINDOW_HOURS)
    assert f"lte.{cutoff.isoformat()}" in _sent_scheduled_start_bounds(route)
    # A kickoff 37h out is strictly beyond the cutoff.
    assert NOW + timedelta(hours=37) > cutoff


@pytest.mark.asyncio
@respx.mock
async def test_exactly_36h_is_deterministic_and_inclusive():
    """VERIFY 2 -- the boundary case HQ asked to be deterministic.

    `lte` makes exactly-36h ELIGIBLE. Asserted against the operator
    actually sent, not against a Python-side comparison, because the
    database is what decides.
    """
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)

    cutoff = NOW + timedelta(hours=FIRST_PAID_RUN_WINDOW_HOURS)
    bounds = _sent_scheduled_start_bounds(route)
    assert f"lte.{cutoff.isoformat()}" in bounds, "must be <=, so exactly 36h is inside"
    assert f"lt.{cutoff.isoformat()}" not in bounds, "must not be <, which would exclude the boundary"
    exactly_36h = NOW + timedelta(hours=36)
    assert exactly_36h <= cutoff


@pytest.mark.asyncio
@respx.mock
async def test_the_7_day_horizon_is_preserved_not_replaced():
    """The 36h gate is additional. Both bounds go to the database."""
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)

    bounds = _sent_scheduled_start_bounds(route)
    assert f"gte.{NOW.isoformat()}" in bounds
    assert f"lt.{(NOW + timedelta(days=7)).isoformat()}" in bounds, "horizon preserved"
    assert f"lte.{(NOW + timedelta(hours=36)).isoformat()}" in bounds, "paid gate added"


@pytest.mark.asyncio
@respx.mock
async def test_inside_36h_and_eligible_allows_the_first_paid_run():
    """VERIFY 3 -- the positive case. A gate that lets nothing through is
    not a gate, it is an outage."""
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(200, json=[]))
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "status": "computed", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 1
    assert result.status == "completed"
    assert result.games_completed_previously == 0


# ---------------------------------------------------------------- 4, 5, 6
# One successful paid cycle per canonical game.


@pytest.mark.asyncio
@respx.mock
async def test_completed_recommendation_cannot_run_again_next_day():
    """VERIFY 4 + 6 -- a game with a completed cycle is excluded, and a
    NEW master_refresh_run does not reopen it.

    `run-2` is deliberately a different run than the one that completed the
    cycle: that is exactly the next-morning situation, and the point is
    that it changes nothing.
    """
    # The conftest default answers this endpoint inertly for every other
    # test; release it so this test's own behaviour is reachable.
    release_default_route(COMPLETED_PAID_CYCLES_GET)
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-2-a-brand-new-day", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1", "cycle_completed_at": "2026-09-18T06:20:00+00:00"}])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 0, "a new run_id must NOT reopen a completed game"
    assert result.games_completed_previously == 1
    assert result.games_selected == 0
    assert result.games == []


@pytest.mark.asyncio
@respx.mock
async def test_completed_no_bet_also_cannot_run_again():
    """VERIFY 5 -- a legitimate No Bet IS a completed paid cycle.

    The evidence is `cycle_completed_at`, which is set unconditionally once
    every candidate has been attempted, whatever the product outcome. So
    this test asserts the rule is outcome-blind, which is what HQ decided.
    """
    # The conftest default answers this endpoint inertly for every other
    # test; release it so this test's own behaviour is reachable.
    release_default_route(COMPLETED_PAID_CYCLES_GET)
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-3", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g_nobet"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g_nobet", "cycle_completed_at": "2026-09-18T06:20:00+00:00"}])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 0
    assert result.games_completed_previously == 1


@pytest.mark.asyncio
@respx.mock
async def test_completed_cycle_identity_is_game_scoped_not_run_scoped():
    """The query is keyed on `game_id` and on `cycle_completed_at` being
    non-null -- never on `correlation_id` or any run identity."""
    release_default_route(COMPLETED_PAID_CYCLES_GET)
    route = respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_game_ids_with_completed_paid_cycle(client, _headers(), game_ids=["a", "b"])

    params = dict(httpx.URL(str(route.calls[0].request.url)).params.multi_items())
    assert params["game_id"] == "in.(a,b)"
    assert params["cycle_completed_at"] == "not.is.null"
    assert "correlation_id" not in params, "run identity must not appear in this rule"


@pytest.mark.asyncio
async def test_empty_slate_does_not_query_supabase():
    """An empty `in.()` is wasteful and a PostgREST syntax risk."""
    with respx.mock:
        route = respx.get(f"{SUPABASE_URL}/rest/v1/recommendations")
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            assert await read_game_ids_with_completed_paid_cycle(client, _headers(), game_ids=[]) == set()
        assert route.call_count == 0


# ------------------------------------------------------------------- 7, 8
# Zero-cost outcomes must stay retryable.


@pytest.mark.asyncio
@respx.mock
async def test_incomplete_cycle_does_not_consume_the_one_paid_run():
    """VERIFY 7 + 8 + 9 -- a row whose cycle never completed is NOT a
    completed paid cycle.

    This is the shape of every zero-cost or failed outcome: stale odds and
    missing odds create no row at all, and a failed paid attempt leaves
    `cycle_completed_at` NULL. All three must remain retryable, and none
    may be marked as having consumed the game's one run.
    """
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-4", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    # PostgREST would filter this out server-side; returning it anyway
    # proves the caller does not treat a mere row as completion.
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(200, json=[]))
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "status": "computed", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 1, "a game with no completed cycle must still be allowed to try"
    assert result.games_completed_previously == 0


@pytest.mark.asyncio
@respx.mock
async def test_failed_paid_attempt_keeps_bounded_retry_not_unlimited():
    """VERIFY 9 -- the existing circuit breaker is preserved, unchanged.

    A deterministic failure halts after 3 identical failures rather than
    burning the slate, and the game is NOT marked completed merely to stop
    spend.
    """
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-5", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(10)])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(200, json=[]))
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(500, text="model provider exploded")
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 3, "bounded, not unlimited"
    assert result.status == "failed", "and never dressed up as a completed run"


# ------------------------------------------------------------------ 10, 11


@pytest.mark.asyncio
@respx.mock
async def test_final_game_never_runs():
    """VERIFY 10 -- only `scheduled` is ever requested."""
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)
    params = dict(httpx.URL(str(route.calls[0].request.url)).params.multi_items())
    assert params["status"] == "eq.scheduled"


def test_no_change_to_probability_ev_or_recommendation_semantics():
    """VERIFY 11 -- structural.

    Recomputation V1 is entirely about WHICH games may be paid for and HOW
    OFTEN. It must not reach into how a recommendation is computed, so the
    worker service still contains no probability, EV, scoring or threshold
    logic of any kind -- exactly as before this change.
    """
    import app.recommendation_worker as worker
    import app.persistence.recommendations as recs
    import app.persistence.games as games

    for module in (worker, recs, games):
        source = open(module.__file__).read()
        for forbidden in ("modeled_probability", "expected_value", "confidence_score", "kelly", "threshold"):
            assert forbidden not in source, f"{forbidden} must not appear in {module.__name__}"
