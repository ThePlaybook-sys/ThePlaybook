"""Tests for app.ai_orchestrator_client (Milestone 4.9)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.ai_orchestrator_client import AiOrchestratorCallError, run_game_recommendation

BASE_URL = "https://ai-orchestrator.test"


@pytest.mark.asyncio
@respx.mock
async def test_success_returns_parsed_json_and_sends_internal_token():
    route = respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "candidates": []})
    )
    async with httpx.AsyncClient() as client:
        result = await run_game_recommendation(
            client, base_url=BASE_URL, internal_token="secret-token", game_id="g1",
            correlation_id="run-1:g1", prompt_version="v1", agent_version="v1",
        )
    assert result == {"recommendation_id": "r1", "candidates": []}
    sent = route.calls.last.request
    assert sent.headers["X-Internal-Token"] == "secret-token"
    import json
    assert json.loads(sent.content) == {"game_id": "g1", "correlation_id": "run-1:g1", "prompt_version": "v1", "agent_version": "v1"}


@pytest.mark.asyncio
@respx.mock
async def test_non_200_raises_ai_orchestrator_call_error():
    respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run-game").mock(return_value=httpx.Response(404, text="not found"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AiOrchestratorCallError):
            await run_game_recommendation(
                client, base_url=BASE_URL, internal_token="secret-token", game_id="ghost",
                correlation_id="run-1:ghost", prompt_version="v1", agent_version="v1",
            )


@pytest.mark.asyncio
@respx.mock
async def test_transport_failure_raises_ai_orchestrator_call_error():
    respx.post(f"{BASE_URL}/v1/internal/recommendation-worker/run-game").mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AiOrchestratorCallError):
            await run_game_recommendation(
                client, base_url=BASE_URL, internal_token="secret-token", game_id="g1",
                correlation_id="run-1:g1", prompt_version="v1", agent_version="v1",
            )
