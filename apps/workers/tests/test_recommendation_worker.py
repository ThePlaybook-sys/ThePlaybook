"""Tests for app.recommendation_worker (Milestone 4.9) -- the Worker's
own orchestration entry point: eligibility, idempotent correlation_id
derivation, per-game dispatch and isolation."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.recommendation_worker import build_correlation_id, run_recommendation_worker_cycle

SUPABASE_URL = "https://test-project.supabase.co"
AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def test_build_correlation_id_is_stable_and_deterministic():
    first = build_correlation_id(run_id="run-1", game_id="g1")
    second = build_correlation_id(run_id="run-1", game_id="g1")
    assert first == second == "run-1:g1"
    assert build_correlation_id(run_id="run-1", game_id="g2") != first


@pytest.mark.asyncio
@respx.mock
async def test_no_eligible_run_yields_no_dispatch():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    games_route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.status == "no_eligible_run"
    assert result.run_id is None
    assert result.games == []
    assert games_route.call_count == 0  # never even looks for games without an eligible run


@pytest.mark.asyncio
@respx.mock
async def test_dispatches_one_call_per_eligible_game_with_stable_correlation_ids():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}]))
    orch_route = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "candidates": []})
    )
    strategy_route = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(
            200, json={"outcome": "bankroll_preservation", "recommendation_product_ids": ["p1"], "leg_count": 0, "no_bet_game_count": 0}
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.status == "completed"
    assert result.run_id == "run-1"
    assert orch_route.call_count == 2
    assert {g.game_id for g in result.games} == {"g1", "g2"}
    assert {g.correlation_id for g in result.games} == {"run-1:g1", "run-1:g2"}
    assert all(g.status == "dispatched" for g in result.games)
    assert strategy_route.call_count == 1
    assert result.strategy["outcome"] == "bankroll_preservation"
    assert result.strategy_error is None


@pytest.mark.asyncio
@respx.mock
async def test_one_games_failure_is_isolated_from_the_next():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}]))

    def _respond(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        if body["game_id"] == "g1":
            return httpx.Response(500, text="internal error")
        return httpx.Response(200, json={"recommendation_id": "r2", "candidates": []})

    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(side_effect=_respond)
    strategy_route = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(
            200, json={"outcome": "bankroll_preservation", "recommendation_product_ids": ["p1"], "leg_count": 0, "no_bet_game_count": 0}
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.status == "completed"
    by_game = {g.game_id: g for g in result.games}
    assert by_game["g1"].status == "failed"
    assert by_game["g1"].error is not None
    assert by_game["g2"].status == "dispatched"
    # Milestone 5.1: g1's dispatch failure means it's omitted from the
    # slate strategy call entirely -- only g2's already-successful result
    # gets relayed.
    assert strategy_route.call_count == 1
    sent_games = json.loads(strategy_route.calls.last.request.content)["games"]
    assert [g["game_id"] for g in sent_games] == ["g2"]


@pytest.mark.asyncio
@respx.mock
async def test_all_games_failing_dispatch_never_calls_finalize_strategy():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    # No finalize-strategy mock registered at all -- if the code called it
    # with zero games, respx would raise AllMockedAssertionError and fail
    # this test, proving the call is genuinely skipped, not just empty.

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.games[0].status == "failed"
    assert result.strategy is None
    assert result.strategy_error is None


@pytest.mark.asyncio
@respx.mock
async def test_finalize_strategy_failure_is_isolated_and_never_raises():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(500, text="db error")
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.status == "completed"
    assert result.games[0].status == "dispatched"
    assert result.strategy is None
    assert result.strategy_error is not None


# --- Pre-Phase-6 Operational Readiness Gate, Decision 5: a game
# ai-orchestrator reports as "skipped_already_computed" must not be
# treated as a fresh candidate source for Strategy, and a cycle where
# EVERY game was already-computed must not re-finalize Strategy at all
# (finalize_slate_strategy has no idempotency of its own for a repeated
# master_refresh_run_id -- see the completion report). ---


@pytest.mark.asyncio
@respx.mock
async def test_skipped_already_computed_game_excluded_from_strategy_input():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}]))

    def _respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["game_id"] == "g1":
            # Already fully computed on an earlier cycle -- no new candidates this time.
            return httpx.Response(200, json={"recommendation_id": "r1", "candidates": [], "status": "skipped_already_computed"})
        return httpx.Response(200, json={"recommendation_id": "r2", "candidates": [], "status": "computed"})

    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(side_effect=_respond)
    strategy_route = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(
            200, json={"outcome": "bankroll_preservation", "recommendation_product_ids": ["p1"], "leg_count": 0, "no_bet_game_count": 0}
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    # Both games still count as successfully "dispatched" (the call itself
    # succeeded) -- but only g2, which actually computed something new
    # this cycle, is fed into Strategy.
    assert all(g.status == "dispatched" for g in result.games)
    assert strategy_route.call_count == 1
    sent_games = json.loads(strategy_route.calls.last.request.content)["games"]
    assert [g["game_id"] for g in sent_games] == ["g2"]


@pytest.mark.asyncio
@respx.mock
async def test_every_game_already_computed_never_calls_finalize_strategy_again():
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[{"id": "run-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "candidates": [], "status": "skipped_already_computed"})
    )
    # No finalize-strategy mock registered at all -- a repeated call here
    # would create a SECOND, duplicate slate-level decision for a run
    # that was already finalized; if the code called it anyway, respx
    # would raise AllMockedAssertionError and fail this test.

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret",
        )

    assert result.games[0].status == "dispatched"
    assert result.strategy is None
    assert result.strategy_error is None
