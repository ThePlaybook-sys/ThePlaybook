"""Tests for app.orchestration.cycle.run_candidate_evaluation (Milestone
4.6, Decision G): the sequential Decision & Advisory chain for one
`MarketCandidate` against an already-existing `recommendation_id` --
never creates a second `recommendations` row, tags every persisted row
with `candidate_key`."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents.committee_context import ParticipationMetadata
from app.features.candidate import MarketCandidate
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.cycle import run_candidate_evaluation
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _candidate() -> MarketCandidate:
    return MarketCandidate(
        game_id="g1",
        sportsbook="DraftKings",
        market_type="moneyline",
        selection="Kansas City Chiefs",
        american_odds=-125,
        point=None,
        observed_at=datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc),
    )


def _participation() -> ParticipationMetadata:
    return ParticipationMetadata(
        configured_agents=frozenset({"injury_intelligence_agent"}),
        built_agents=frozenset({"injury_intelligence_agent"}),
        deferred_agents=frozenset(),
        attempted_agents=frozenset({"injury_intelligence_agent"}),
        successful_agents=frozenset({"injury_intelligence_agent"}),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=1.0,
    )


def _routing_rules() -> dict[str, dict]:
    task_types = [
        "probability_modeling_analysis",
        "expected_value_analysis",
        "risk_manager_analysis",
        "bankroll_coach_analysis",
    ]
    return {t: {"task_type": t, "primary_model": "claude-sonnet-5", "fallback_model": None} for t in task_types}


def _valid_probability_json() -> str:
    return json.dumps(
        {
            "agent_name": "probability_modeling_agent",
            "candidate_key": "g1:DraftKings:moneyline:Kansas City Chiefs:none",
            "selection": "Kansas City Chiefs",
            "modeled_probability": 0.57,
            "confidence_in_probability": 0.72,
            "reasoning": "reasoning",
            "supporting_evidence": [],
            "would_change_mind_if": "x",
        }
    )


def _valid_agent_output_json(agent_name: str) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "finding": "finding",
            "supporting_evidence": [],
            "evidence_classification": "data_backed",
            "directional_lean": "home",
            "confidence": 0.6,
            "would_change_mind_if": "x",
        }
    )


def _mock_agents():
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}]))
    mock_prompt_registry_route(SUPABASE_URL)


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_persists_one_row_per_successful_step_tagged_with_candidate_key():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_valid_probability_json()),
            ScriptedSuccess(raw_text=_valid_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent")),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert chain_result.status == "full"
    assert output_route.call_count == 4
    expected_key = "g1:DraftKings:moneyline:Kansas City Chiefs:none"
    for call in output_route.calls:
        sent = json.loads(call.request.content)
        assert sent["recommendation_id"] == "r1"
        assert sent["candidate_key"] == expected_key


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_never_creates_a_recommendations_row():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    recommendations_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "should-not-be-called"}]))
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_valid_probability_json()),
            ScriptedSuccess(raw_text=_valid_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent")),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert recommendations_route.call_count == 0  # the SAME existing recommendation_id is reused, never a second row


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_without_user_id_never_reads_user_profiles():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    profile_route = respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(return_value=httpx.Response(200, json=[]))
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_valid_probability_json()),
            ScriptedSuccess(raw_text=_valid_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent")),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert profile_route.call_count == 0
    assert chain_result.kelly.stake is None  # no bankroll profile at all -- never fabricated


@pytest.mark.asyncio
@respx.mock
async def test_run_candidate_evaluation_with_user_id_reads_real_profile_and_uses_it():
    _mock_agents()
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": "u1", "risk_tolerance": "moderate", "preferred_unit_size": 25.0, "optional_bankroll": 1000.0}])
    )
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_valid_probability_json()),
            ScriptedSuccess(raw_text=_valid_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_valid_agent_output_json("bankroll_coach_agent")),
        ],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
            user_id="u1",
        )

    assert chain_result.kelly.stake is not None  # a real (synthetic-for-this-test) complete profile -> a valid stake


@pytest.mark.asyncio
@respx.mock
async def test_probability_modeling_failure_persists_nothing():
    _mock_agents()
    output_route = respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))],
    )
    registry = AdapterRegistry(adapters={"anthropic": adapter})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        chain_result = await run_candidate_evaluation(
            client,
            _headers(),
            recommendation_id="r1",
            game_id="g1",
            correlation_id="corr-1",
            candidate=_candidate(),
            upstream_outputs=(),
            participation=_participation(),
            routing_rules=_routing_rules(),
            adapter_registry=registry,
        )

    assert chain_result.status == "failed"
    assert output_route.call_count == 0
