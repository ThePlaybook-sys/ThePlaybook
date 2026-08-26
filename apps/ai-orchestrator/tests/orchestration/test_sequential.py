"""Tests for app.orchestration.sequential (Milestone 4.6; client/headers +
prompt resolution added Milestone 4.8; split into `run_shared_candidate_chain`
/ `run_bankroll_coach_step` in Milestone 4.9, Decision 2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents.bankroll_coach import BankrollCoachAgent
from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.expected_value_agent import ExpectedValueAgent
from app.agents.probability_modeling import ProbabilityModelingAgent
from app.agents.risk_manager import RiskManagerAgent
from app.features.candidate import MarketCandidate
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.sequential import run_bankroll_coach_step, run_shared_candidate_chain
from tests.conftest import mock_prompt_registry_route

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}

_VALID_AGENT_OUTPUT = json.dumps(
    {
        "agent_name": "placeholder",
        "finding": "finding",
        "supporting_evidence": [],
        "evidence_classification": "data_backed",
        "directional_lean": "home",
        "confidence": 0.6,
        "would_change_mind_if": "x",
    }
)

_VALID_PROBABILITY_OUTPUT = json.dumps(
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


def _context(*, bankroll_profile=None) -> SequentialDecisionContext:
    return SequentialDecisionContext(
        game_id="g1",
        correlation_id="corr-1",
        candidate=_candidate(),
        upstream_outputs=(),
        participation=_participation(),
        bankroll_profile=bankroll_profile,
    )


def _routing_rules() -> dict[str, dict]:
    return {
        agent_cls.task_type: {"task_type": agent_cls.task_type, "primary_model": "claude-sonnet-5", "fallback_model": None}
        for agent_cls in (ProbabilityModelingAgent, ExpectedValueAgent, RiskManagerAgent, BankrollCoachAgent)
    }


def _agent_output_json(agent_name: str) -> str:
    return _VALID_AGENT_OUTPUT.replace('"placeholder"', f'"{agent_name}"')


# --- run_shared_candidate_chain: Probability -> EV -> Risk, no user concept ---


@pytest.mark.asyncio
@respx.mock
async def test_shared_chain_full_when_all_three_succeed():
    mock_prompt_registry_route(SUPABASE_URL)
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_VALID_PROBABILITY_OUTPUT),
            ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent")),
        ],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_shared_candidate_chain(
            _context(),
            client=client,
            headers=_headers(),
            routing_rules=_routing_rules(),
            adapter_registry=AdapterRegistry(adapters={"anthropic": adapter}),
        )
    assert result.status == "full"
    assert len(result.successes) == 3
    assert result.probability.modeled_probability == 0.57
    # decimal_odds for -125 is 1.8; ev_per_dollar = 0.57*1.8-1 = 0.026
    assert result.ev.ev_per_dollar == pytest.approx(0.57 * 1.8 - 1)
    assert result.risk.bernoulli_outcome_variance == pytest.approx(0.57 * 0.43)
    # No bankroll/Kelly concept at all in the shared chain:
    assert result.context.kelly is None
    # Milestone 5.3 (Decision AV) -- the ACTUAL model/provider that
    # produced each output, from ModelResponse.usage.
    for success in result.successes:
        assert success.model_name == "claude-sonnet-5"
        assert success.provider == "anthropic"
        assert success.used_fallback is False


@pytest.mark.asyncio
@respx.mock
async def test_shared_chain_failed_when_probability_modeling_fails_blocks_everything():
    mock_prompt_registry_route(SUPABASE_URL)
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))],
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_shared_candidate_chain(
            _context(),
            client=client,
            headers=_headers(),
            routing_rules=_routing_rules(),
            adapter_registry=AdapterRegistry(adapters={"anthropic": adapter}),
        )
    assert result.status == "failed"
    assert len(result.results) == 1  # EV/Risk never attempted
    assert result.probability is None
    assert result.ev is None
    assert result.risk is None


@pytest.mark.asyncio
@respx.mock
async def test_shared_chain_partial_when_probability_succeeds_but_one_downstream_agent_fails():
    mock_prompt_registry_route(SUPABASE_URL)

    class _MixedAdapter:
        def __init__(self):
            self.calls = 0

        async def complete(self, request):
            self.calls += 1
            if request.agent_name == "expected_value_agent":
                raise ModelTimeoutError("always times out")
            from app.models.structured_output import parse_structured_output
            from app.models.types import ModelResponse, UsageMetadata

            text = _VALID_PROBABILITY_OUTPUT if request.agent_name == "probability_modeling_agent" else _agent_output_json(request.agent_name)
            return ModelResponse(
                raw_text=text,
                usage=UsageMetadata(provider="anthropic", model=request.model),
                parsed=parse_structured_output(text, request.response_model),
            )

    registry = AdapterRegistry(adapters={"anthropic": _MixedAdapter()})
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_shared_candidate_chain(_context(), client=client, headers=_headers(), routing_rules=_routing_rules(), adapter_registry=registry)

    assert result.status == "partial"
    assert len(result.successes) == 2
    assert len(result.failures) == 1
    assert result.failures[0].agent_name == "expected_value_agent"
    # Deterministic math still computed for Risk even though EV's own LLM call failed:
    assert result.ev is not None
    assert result.ev.ev_per_dollar == pytest.approx(0.57 * 1.8 - 1)
    assert result.risk is not None


# --- run_bankroll_coach_step: per-user, reuses the shared chain's own context ---


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_coach_step_success_with_a_complete_profile():
    mock_prompt_registry_route(SUPABASE_URL)
    context = _context(bankroll_profile={"optional_bankroll": 1000.0, "risk_tolerance": "moderate"})
    import dataclasses

    from app.features.expected_value import compute_ev
    from app.features.risk import build_risk_assessment

    ev = compute_ev(0.57, -125)
    risk = build_risk_assessment(0.57)
    from app.agents.probability_output import ProbabilityModelOutput

    probability = ProbabilityModelOutput(**json.loads(_VALID_PROBABILITY_OUTPUT))
    context = dataclasses.replace(context, probability=probability, ev=ev, risk=risk)

    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent"))])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_bankroll_coach_step(
            context,
            client=client,
            headers=_headers(),
            routing_rule=_routing_rules()[BankrollCoachAgent.task_type],
            adapter_registry=AdapterRegistry(adapters={"anthropic": adapter}),
        )
    assert result.status == "success"
    assert result.kelly.stake is not None


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_coach_step_missing_bankroll_profile_yields_null_stake_but_still_succeeds():
    mock_prompt_registry_route(SUPABASE_URL)
    import dataclasses

    from app.agents.probability_output import ProbabilityModelOutput
    from app.features.expected_value import compute_ev
    from app.features.risk import build_risk_assessment

    probability = ProbabilityModelOutput(**json.loads(_VALID_PROBABILITY_OUTPUT))
    ev = compute_ev(0.57, -125)
    risk = build_risk_assessment(0.57)
    context = dataclasses.replace(_context(bankroll_profile=None), probability=probability, ev=ev, risk=risk)

    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent"))])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_bankroll_coach_step(
            context,
            client=client,
            headers=_headers(),
            routing_rule=_routing_rules()[BankrollCoachAgent.task_type],
            adapter_registry=AdapterRegistry(adapters={"anthropic": adapter}),
        )
    assert result.status == "success"
    assert result.kelly.stake is None
    assert result.kelly.full_kelly_fraction is not None  # Kelly fractions still computed


@pytest.mark.asyncio
async def test_bankroll_coach_step_skipped_when_shared_chain_never_reached_a_probability():
    context = _context()  # probability/ev both None -- as if the shared chain failed
    result = await run_bankroll_coach_step(
        context,
        client=None,  # never reached -- proves this short-circuits before any I/O
        headers=_headers(),
        routing_rule=_routing_rules()[BankrollCoachAgent.task_type],
        adapter_registry=AdapterRegistry(adapters={}),
    )
    assert result.status == "skipped_no_probability"
    assert result.result is None
    assert result.kelly is None
