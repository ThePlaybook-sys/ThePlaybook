"""Tests for the four Milestone 4.6 sequential Decision & Advisory
agents + their shared base. Proves: correct response_model per agent
(ProbabilityModelOutput vs AgentOutput), evidence reflects
already-computed deterministic values unchanged, missing upstream
results degrade every dependent field to None, and each agent produces
contract-valid output end-to-end via FakeModelAdapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.agents.bankroll_coach import BankrollCoachAgent
from app.agents.committee_context import ParticipationMetadata, SequentialDecisionContext
from app.agents.contract import AgentOutput
from app.agents.expected_value_agent import ExpectedValueAgent
from app.agents.probability_modeling import ProbabilityModelingAgent
from app.agents.probability_output import ProbabilityModelOutput
from app.agents.risk_manager import RiskManagerAgent
from app.agents.sequential_base import (
    _LEGACY_AGENT_OUTPUT_INSTRUCTIONS,
    _LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS,
    _LEGACY_SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE,
)
from app.features.candidate import MarketCandidate
from app.features.expected_value import EVResult
from app.features.kelly import KellyResult
from app.features.risk import RiskAssessment
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.retry_policy import RetryEngine
from app.models.types import ModelRequest


def _sequential_prompt(agent) -> str:
    instructions = (
        _LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS if agent.response_model is ProbabilityModelOutput else _LEGACY_AGENT_OUTPUT_INSTRUCTIONS
    )
    return _LEGACY_SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE.format(agent_name=agent.agent_name, output_instructions=instructions)

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
        configured_agents=frozenset({"injury_intelligence_agent", "referee_tendencies_agent"}),
        built_agents=frozenset({"injury_intelligence_agent"}),
        deferred_agents=frozenset({"referee_tendencies_agent"}),
        attempted_agents=frozenset({"injury_intelligence_agent"}),
        successful_agents=frozenset({"injury_intelligence_agent"}),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=0.5,
    )


def _upstream_output() -> AgentOutput:
    return AgentOutput(
        agent_name="injury_intelligence_agent",
        finding="BAL QB questionable",
        supporting_evidence=["injury: questionable"],
        evidence_classification="data_backed",
        directional_lean="home",
        confidence=0.6,
        would_change_mind_if="QB upgraded",
    )


def _bare_context(**overrides) -> SequentialDecisionContext:
    base = dict(
        game_id="g1",
        correlation_id="corr-1",
        candidate=_candidate(),
        upstream_outputs=(_upstream_output(),),
        participation=_participation(),
    )
    base.update(overrides)
    return SequentialDecisionContext(**base)


# --- ProbabilityModelingAgent ---


def test_probability_modeling_response_model_is_dedicated_contract():
    assert ProbabilityModelingAgent().response_model is ProbabilityModelOutput


def test_probability_modeling_evidence_includes_candidate_and_upstream_findings():
    agent = ProbabilityModelingAgent()
    context = _bare_context()
    evidence = agent.build_evidence(context)
    assert evidence["candidate"]["selection"] == "Kansas City Chiefs"
    assert evidence["candidate"]["american_odds"] == -125
    assert len(evidence["upstream_findings"]) == 1
    assert evidence["upstream_findings"][0]["agent_name"] == "injury_intelligence_agent"


def test_probability_modeling_evidence_includes_honest_participation_metadata():
    agent = ProbabilityModelingAgent()
    evidence = agent.build_evidence(_bare_context())
    participation = evidence["participation"]
    assert participation["deferred_agents"] == ["referee_tendencies_agent"]
    assert participation["fan_out_status"] == "full"
    assert participation["committee_completeness"] == 0.5


@pytest.mark.asyncio
async def test_probability_modeling_produces_contract_valid_output_via_fake_adapter():
    agent = ProbabilityModelingAgent()
    context = _bare_context()
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_VALID_PROBABILITY_OUTPUT)])
    request = ModelRequest(
        model="claude-opus-5",
        messages=agent.build_messages(context, system_prompt=_sequential_prompt(agent)),
        task_type=agent.task_type,
        agent_name=agent.agent_name,
        correlation_id=context.correlation_id,
        response_model=agent.response_model,
    )
    response = await RetryEngine().execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, ProbabilityModelOutput)
    assert response.parsed.modeled_probability == 0.57
    assert response.parsed.confidence_in_probability == 0.72


# --- ExpectedValueAgent / RiskManagerAgent: response_model stays AgentOutput ---


@pytest.mark.parametrize("agent_cls", [ExpectedValueAgent, RiskManagerAgent, BankrollCoachAgent])
def test_ev_risk_bankroll_use_ordinary_agent_output_contract(agent_cls):
    assert agent_cls().response_model is AgentOutput


def test_expected_value_evidence_reflects_deterministic_values_unchanged():
    ev = EVResult(decimal_odds=1.8, raw_implied_probability=0.5556, raw_probability_edge=0.0444, ev_per_dollar=0.08)
    probability = ProbabilityModelOutput.model_validate(json.loads(_VALID_PROBABILITY_OUTPUT))
    context = _bare_context(probability=probability, ev=ev)
    evidence = ExpectedValueAgent().build_evidence(context)
    assert evidence["ev_per_dollar"] == 0.08
    assert evidence["decimal_odds"] == 1.8
    assert evidence["modeled_probability"] == 0.57


def test_expected_value_evidence_stays_none_when_upstream_missing():
    evidence = ExpectedValueAgent().build_evidence(_bare_context())  # no probability/ev set
    assert evidence["modeled_probability"] is None
    assert evidence["ev_per_dollar"] is None


def test_risk_manager_evidence_names_missing_historical_variance():
    risk = RiskAssessment(bernoulli_outcome_variance=0.24, historical_bet_type_variance=None)
    context = _bare_context(risk=risk)
    evidence = RiskManagerAgent().build_evidence(context)
    assert evidence["bernoulli_outcome_variance"] == 0.24
    assert evidence["historical_bet_type_variance"] is None


def test_bankroll_coach_evidence_null_stake_when_bankroll_missing():
    kelly = KellyResult(full_kelly_fraction=0.1, quarter_kelly_fraction=0.025, risk_tolerance_multiplier=None, stake=None)
    context = _bare_context(kelly=kelly, bankroll_profile={"optional_bankroll": None, "risk_tolerance": None})
    evidence = BankrollCoachAgent().build_evidence(context)
    assert evidence["bankroll"] is None
    assert evidence["recommended_stake"] is None
    assert evidence["full_kelly_fraction"] == 0.1  # Kelly fractions still shown even without a dollar stake


def test_bankroll_coach_evidence_valid_stake_for_synthetic_complete_profile():
    kelly = KellyResult(full_kelly_fraction=0.1, quarter_kelly_fraction=0.025, risk_tolerance_multiplier=0.75, stake=18.75)
    context = _bare_context(kelly=kelly, bankroll_profile={"optional_bankroll": 1000.0, "risk_tolerance": "moderate"})
    evidence = BankrollCoachAgent().build_evidence(context)
    assert evidence["bankroll"] == 1000.0
    assert evidence["recommended_stake"] == 18.75


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_cls", [ExpectedValueAgent, RiskManagerAgent, BankrollCoachAgent])
async def test_agent_output_agents_produce_contract_valid_output_via_fake_adapter(agent_cls):
    agent = agent_cls()
    context = _bare_context()
    valid_output = _VALID_AGENT_OUTPUT.replace('"placeholder"', f'"{agent.agent_name}"')
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=valid_output)])
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=agent.build_messages(context, system_prompt=_sequential_prompt(agent)),
        task_type=agent.task_type,
        agent_name=agent.agent_name,
        correlation_id=context.correlation_id,
        response_model=agent.response_model,
    )
    response = await RetryEngine().execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, AgentOutput)
    assert response.parsed.agent_name == agent.agent_name
