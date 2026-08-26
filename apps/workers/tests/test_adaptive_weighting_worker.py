"""Tests for app.adaptive_weighting_worker (Milestone 5.5) -- the
single-call wrapper and its failure isolation."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.adaptive_weighting_worker import run_adaptive_weighting_worker_cycle

AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"


@pytest.mark.asyncio
@respx.mock
async def test_successful_cycle_relays_response():
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/adaptive-weighting/run").mock(
        return_value=httpx.Response(200, json={"evaluation_window_start": "2026-05-01", "evaluation_window_end": "2026-08-01", "committee_average_roi": None, "agents": []})
    )
    async with httpx.AsyncClient() as orch_client:
        result = await run_adaptive_weighting_worker_cycle(
            ai_orchestrator_client=orch_client, ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret"
        )
    assert result.status == "completed"
    assert result.response["evaluation_window_start"] == "2026-05-01"


@pytest.mark.asyncio
@respx.mock
async def test_ai_orchestrator_failure_is_isolated_not_raised():
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/adaptive-weighting/run").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient() as orch_client:
        result = await run_adaptive_weighting_worker_cycle(
            ai_orchestrator_client=orch_client, ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret"
        )
    assert result.status == "failed"
    assert result.error is not None
