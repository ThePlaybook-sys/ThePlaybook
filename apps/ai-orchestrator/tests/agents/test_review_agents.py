"""Tests for the two Milestone 4.7 review agents (Meta Agent, Elite
Reconciliation Agent) + their shared base."""
from __future__ import annotations

import json

import pytest

from app.agents.committee_context import ParticipationMetadata
from app.agents.consensus_review_base import (
    _LEGACY_ELITE_HARD_RULE,
    _LEGACY_ELITE_SCHEMA,
    _LEGACY_META_HARD_RULE,
    _LEGACY_META_SCHEMA,
    _LEGACY_SYSTEM_PROMPT_TEMPLATE,
)
from app.agents.consensus_review_context import ConsensusReviewContext
from app.agents.contract import MetaAgentOutput
from app.agents.elite_reconciliation_agent import EliteReconciliationAgent
from app.agents.elite_reconciliation_output import EliteReconciliationOutput
from app.agents.meta_agent import MetaAgent
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.retry_policy import RetryEngine
from app.models.types import ModelRequest


def _meta_prompt(agent) -> str:
    return _LEGACY_SYSTEM_PROMPT_TEMPLATE.format(agent_name=agent.agent_name, hard_rule=_LEGACY_META_HARD_RULE, schema=_LEGACY_META_SCHEMA)


def _elite_prompt(agent) -> str:
    return _LEGACY_SYSTEM_PROMPT_TEMPLATE.format(agent_name=agent.agent_name, hard_rule=_LEGACY_ELITE_HARD_RULE, schema=_LEGACY_ELITE_SCHEMA)


def _participation() -> ParticipationMetadata:
    return ParticipationMetadata(
        configured_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        built_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        deferred_agents=frozenset(),
        attempted_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        successful_agents=frozenset({"injury_intelligence_agent", "weather_agent"}),
        failed_agents=frozenset(),
        fan_out_status="full",
        committee_completeness=1.0,
    )


def _findings() -> tuple[dict, ...]:
    return (
        {"agent_name": "injury_intelligence_agent", "category": "context", "finding": "f1", "confidence": 0.6, "directional_lean": "home", "evidence_classification": "data_backed"},
        {"agent_name": "weather_agent", "category": "context", "finding": "f2", "confidence": 0.5, "directional_lean": "none", "evidence_classification": "data_backed"},
    )


def _context(**overrides) -> ConsensusReviewContext:
    base = dict(
        game_id="g1",
        correlation_id="corr-1",
        candidate_key="g1:DraftKings:moneyline:KC:none",
        agent_findings=_findings(),
        aggregate_confidence=0.6,
        agreement_variance=0.1,
        participation=_participation(),
    )
    base.update(overrides)
    return ConsensusReviewContext(**base)


# --- MetaAgent ---


def test_meta_agent_response_model_is_meta_agent_output():
    assert MetaAgent().response_model is MetaAgentOutput


def test_meta_agent_evidence_groups_findings_by_category():
    evidence = MetaAgent().build_evidence(_context())
    assert "context" in evidence["findings_by_category"]
    assert len(evidence["findings_by_category"]["context"]) == 2
    assert evidence["aggregate_confidence"] == 0.6
    assert evidence["agreement_variance"] == 0.1


def test_meta_agent_prompt_states_hard_rule():
    agent = MetaAgent()
    messages = agent.build_messages(_context(), system_prompt=_meta_prompt(agent))
    assert "zero or negative" in messages[0].content


@pytest.mark.asyncio
async def test_meta_agent_produces_contract_valid_output_via_fake_adapter():
    agent = MetaAgent()
    context = _context()
    raw = json.dumps({"agent_name": "meta_agent", "polarization_score": 0.2, "uncertainty_flag": False, "confidence_adjustment": -0.05, "reasoning": "r"})
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=raw)])
    request = ModelRequest(
        model="claude-sonnet-5", messages=agent.build_messages(context, system_prompt=_meta_prompt(agent)), task_type=agent.task_type,
        agent_name=agent.agent_name, correlation_id=context.correlation_id, response_model=agent.response_model,
    )
    response = await RetryEngine().execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, MetaAgentOutput)
    assert response.parsed.confidence_adjustment == -0.05


# --- EliteReconciliationAgent ---


def test_elite_agent_response_model_is_dedicated_contract():
    assert EliteReconciliationAgent().response_model is EliteReconciliationOutput


def test_elite_agent_evidence_includes_meta_reasoning_and_raw_findings():
    context = _context(meta_reasoning="Committee is split on injury impact.")
    evidence = EliteReconciliationAgent().build_evidence(context)
    assert evidence["meta_reasoning"] == "Committee is split on injury impact."
    assert len(evidence["agent_findings"]) == 2
    assert evidence["agent_findings"][0]["agent_name"] == "injury_intelligence_agent"


def test_elite_agent_evidence_meta_reasoning_none_when_not_set():
    evidence = EliteReconciliationAgent().build_evidence(_context())
    assert evidence["meta_reasoning"] is None


@pytest.mark.asyncio
async def test_elite_agent_produces_contract_valid_output_via_fake_adapter():
    agent = EliteReconciliationAgent()
    context = _context(meta_reasoning="reasoning")
    raw = json.dumps(
        {
            "agent_name": "consensus_reconciliation_agent",
            "candidate_key": "g1:DraftKings:moneyline:KC:none",
            "reasoning": "reconciled",
            "confidence_adjustment": -0.08,
            "supporting_evidence": ["x"],
            "would_change_mind_if": "y",
        }
    )
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=raw)])
    request = ModelRequest(
        model="claude-opus-5", messages=agent.build_messages(context, system_prompt=_elite_prompt(agent)), task_type=agent.task_type,
        agent_name=agent.agent_name, correlation_id=context.correlation_id, response_model=agent.response_model,
    )
    response = await RetryEngine().execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, EliteReconciliationOutput)
    assert response.parsed.confidence_adjustment == -0.08
