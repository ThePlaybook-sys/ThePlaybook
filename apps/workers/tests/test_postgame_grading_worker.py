"""Tests for app.postgame_grading_worker (Milestone 5.4) -- discovery +
single-batch dispatch, isolation of ai-orchestrator call failures."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.postgame_grading_worker import run_postgame_grading_worker_cycle

SUPABASE_URL = "https://test-project.supabase.co"
AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"
_NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_no_candidates_never_calls_ai_orchestrator():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    orch_route = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/postgame-grading/run")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_postgame_grading_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=_NOW,
        )

    assert result.status == "no_candidates"
    assert orch_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatches_one_batch_call_with_discovered_ids():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}, {"id": "g2"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/postgame-grading/run").mock(
        return_value=httpx.Response(200, json={"games": [], "bankroll_preservation_products": [], "postgame_reviews_generated": 0, "postgame_reviews_failed": 0, "postgame_reviews_skipped": 0})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_postgame_grading_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=_NOW,
        )

    assert result.status == "completed"
    assert result.game_ids == ["g1", "g2"]
    assert result.response["postgame_reviews_generated"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_ai_orchestrator_failure_is_isolated_not_raised():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[{"id": "g1"}]))
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/postgame-grading/run").mock(return_value=httpx.Response(500, text="boom"))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db_client, httpx.AsyncClient() as orch_client:
        result = await run_postgame_grading_worker_cycle(
            db_client, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=_NOW,
        )

    assert result.status == "failed"
    assert result.error is not None
