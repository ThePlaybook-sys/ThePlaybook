"""Tests for app.orchestration.sequential (Milestone 4.6)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.agents.bankroll_coach import BankrollCoachAgent
from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.expected_value_agent import ExpectedValueAgent
from app.agents.probability_modeling import ProbabilityModelingAgent
from app.agents.risk_manager import RiskManagerAgent
from app.features.candidate import MarketCandidate
from app.models.errors import ModelTimeoutError
from app.models.fake_adapter import FakeModelAdapter, ScriptedFailure, ScriptedSuccess
from app.models.router import AdapterRegistry
from app.orchestration.sequential import run_sequential_chain

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


def _context() -> SequentialDecisionContext:
    return SequentialDecisionContext(
        game_id="g1",
        correlation_id="corr-1",
        candidate=_candidate(),
        upstream_outputs=(),
        participation=_participation(),
        bankroll_profile={"optional_bankroll": 1000.0, "risk_tolerance": "moderate"},
    )


def _routing_rules() -> dict[str, dict]:
    return {
        agent_cls.task_type: {"task_type": agent_cls.task_type, "primary_model": "claude-sonnet-5", "fallback_model": None}
        for agent_cls in (ProbabilityModelingAgent, ExpectedValueAgent, RiskManagerAgent, BankrollCoachAgent)
    }


def _agent_output_json(agent_name: str) -> str:
    return _VALID_AGENT_OUTPUT.replace('"placeholder"', f'"{agent_name}"')


@pytest.mark.asyncio
async def test_chain_full_when_all_four_succeed():
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_VALID_PROBABILITY_OUTPUT),
            ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent")),
        ],
    )
    result = await run_sequential_chain(
        _context(), routing_rules=_routing_rules(), adapter_registry=AdapterRegistry(adapters={"anthropic": adapter})
    )
    assert result.status == "full"
    assert len(result.successes) == 4
    assert result.probability.modeled_probability == 0.57
    # decimal_odds for -125 is 1.8; ev_per_dollar = 0.57*1.8-1 = 0.026
    assert result.ev.ev_per_dollar == pytest.approx(0.57 * 1.8 - 1)
    assert result.risk.bernoulli_outcome_variance == pytest.approx(0.57 * 0.43)
    assert result.kelly.stake is not None


@pytest.mark.asyncio
async def test_chain_failed_when_probability_modeling_fails_blocks_everything():
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedFailure(error=ModelTimeoutError("t1")), ScriptedFailure(error=ModelTimeoutError("t2"))],
    )
    result = await run_sequential_chain(
        _context(), routing_rules=_routing_rules(), adapter_registry=AdapterRegistry(adapters={"anthropic": adapter})
    )
    assert result.status == "failed"
    assert len(result.results) == 1  # EV/Risk/Bankroll never attempted
    assert result.probability is None
    assert result.ev is None
    assert result.risk is None
    assert result.kelly is None


@pytest.mark.asyncio
async def test_chain_partial_when_probability_succeeds_but_one_downstream_agent_fails():
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
    result = await run_sequential_chain(_context(), routing_rules=_routing_rules(), adapter_registry=registry)

    assert result.status == "partial"
    assert len(result.successes) == 3
    assert len(result.failures) == 1
    assert result.failures[0].agent_name == "expected_value_agent"
    # Deterministic math still computed for Risk/Bankroll even though EV's own LLM call failed:
    assert result.ev is not None
    assert result.ev.ev_per_dollar == pytest.approx(0.57 * 1.8 - 1)
    assert result.risk is not None
    assert result.kelly is not None


@pytest.mark.asyncio
async def test_missing_bankroll_profile_yields_null_stake_but_chain_still_full():
    context = SequentialDecisionContext(
        game_id="g1",
        correlation_id="corr-1",
        candidate=_candidate(),
        upstream_outputs=(),
        participation=_participation(),
        bankroll_profile=None,
    )
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[
            ScriptedSuccess(raw_text=_VALID_PROBABILITY_OUTPUT),
            ScriptedSuccess(raw_text=_agent_output_json("expected_value_agent")),
            ScriptedSuccess(raw_text=_agent_output_json("risk_manager_agent")),
            ScriptedSuccess(raw_text=_agent_output_json("bankroll_coach_agent")),
        ],
    )
    result = await run_sequential_chain(
        context, routing_rules=_routing_rules(), adapter_registry=AdapterRegistry(adapters={"anthropic": adapter})
    )
    assert result.status == "full"
    assert result.kelly.stake is None
    assert result.kelly.full_kelly_fraction is not None  # Kelly fractions still computed
