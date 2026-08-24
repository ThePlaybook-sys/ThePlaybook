"""Tests for app.orchestration.cycle (Milestone 4.5) -- the recommendation-
cycle lifecycle: one cycle created per run, the same recommendation_id
reused for every successful agent-output write, failed agents produce no
output row at all."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.agents.base_agent import ContextDataAgent
from app.agents.context import AgentContext
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.cycle import run_recommendation_cycle
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


class _StubAgent(ContextDataAgent):
    def __init__(self, name: str, task_type: str):
        self.agent_name = name
        self.task_type = task_type

    def build_evidence(self, context: AgentContext) -> dict:
        return {"stub": True}


def _valid_output_json(agent_name: str) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "finding": "finding",
            "supporting_evidence": [],
            "evidence_classification": "data_backed",
            "directional_lean": "none",
            "confidence": 0.5,
            "would_change_mind_if": "x",
        }
    )


def _routing_rule(task_type: str) -> dict:
    return {"task_type": task_type, "primary_model": "claude-sonnet-5", "fallback_model": None}


def _mock_context_reads(*, odds_rows: list | None = None):
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games", params={"status": "eq.final"}).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "g1", "home_team": "BUF", "away_team": "KC", "scheduled_start": "2026-09-21T17:00:00+00:00",
                    "venue_lat": None, "venue_long": None, "stadium": None, "venue_type": None,
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=odds_rows or []))
    mock_prompt_registry_route(SUPABASE_URL)


@pytest.mark.asyncio
@respx.mock
async def test_one_cycle_created_and_reused_across_all_successful_outputs():
    _mock_context_reads()
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(201, json=[{"id": "r1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(201, json=[{}])
    )

    agents = [_StubAgent("agent_a", "task_a"), _StubAgent("agent_b", "task_b")]
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text=_valid_output_json("agent_a")), ScriptedSuccess(raw_text=_valid_output_json("agent_b"))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        recommendation_id, fan_out_result = await run_recommendation_cycle(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            agents=agents, routing_rules={"task_a": _routing_rule("task_a"), "task_b": _routing_rule("task_b")},
            adapter_registry=registry, model_providers={"claude-sonnet-5": "anthropic"},
        )

    assert recommendation_id == "r1"
    assert fan_out_result.status == "full"
    assert create_route.call_count == 1  # exactly one cycle created for this run
    assert output_route.call_count == 2
    for call in output_route.calls:
        sent = json.loads(call.request.content)
        assert sent["recommendation_id"] == "r1"  # same id reused for every output


@pytest.mark.asyncio
@respx.mock
async def test_failed_agent_produces_no_output_row():
    _mock_context_reads()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(201, json=[{}])
    )

    agents = [_StubAgent("agent_ok", "task_ok"), _StubAgent("agent_fails", "task_fail")]
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text=_valid_output_json("agent_ok")), ScriptedFailure(error=ModelTimeoutError("t"))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        recommendation_id, fan_out_result = await run_recommendation_cycle(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            agents=agents, routing_rules={"task_ok": _routing_rule("task_ok"), "task_fail": _routing_rule("task_fail")},
            adapter_registry=registry, model_providers={"claude-sonnet-5": "anthropic"},
        )

    assert fan_out_result.status == "partial"
    assert output_route.call_count == 1  # only the successful agent persisted
    sent = json.loads(output_route.calls.last.request.content)
    assert sent["agent_id"] == "a1"


@pytest.mark.asyncio
@respx.mock
async def test_cycle_created_before_agent_outputs_are_persisted():
    _mock_context_reads()
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(201, json=[{"id": "r1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(
        return_value=httpx.Response(201, json=[{}])
    )

    agents = [_StubAgent("agent_a", "task_a")]
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_valid_output_json("agent_a"))])
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await run_recommendation_cycle(
            client, _headers(), game_id="g1", correlation_id="corr-1", prompt_version="v1", agent_version="v1",
            agents=agents, routing_rules={"task_a": _routing_rule("task_a")},
            adapter_registry=registry, model_providers={"claude-sonnet-5": "anthropic"},
        )

    assert create_route.call_count == 1
    assert output_route.call_count == 1
    # The cycle-creation POST happens strictly before the agent-output
    # POST in respx's global, chronologically-ordered call log.
    all_calls = list(respx.calls)
    create_index = next(i for i, c in enumerate(all_calls) if c.request.url.path == "/rest/v1/recommendations" and c.request.method == "POST")
    output_index = next(
        i for i, c in enumerate(all_calls) if c.request.url.path == "/rest/v1/recommendation_agent_outputs" and c.request.method == "POST"
    )
    assert create_index < output_index
