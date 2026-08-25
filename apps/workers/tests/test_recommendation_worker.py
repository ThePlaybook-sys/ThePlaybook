"""Tests for app.recommendation_worker (Milestone 4.9) -- the Worker's
own orchestration entry point: eligibility, idempotent correlation_id
derivation, per-game dispatch and isolation."""
from __future__ import annotations

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
