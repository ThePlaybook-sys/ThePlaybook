"""Proves AgentOutput/MetaAgentOutput (Milestone 4.2) remain the
authoritative structured-output contracts through the model layer
(Milestone 4.3, requirement 5) -- an end-to-end path from a
`ModelRequest` through `FakeModelAdapter` and `RetryEngine` to a
validated `AgentOutput`/`MetaAgentOutput` instance, and a malformed
attempt correctly triggering the retry engine's repair path before
eventually failing cleanly."""
from __future__ import annotations

import pytest

from app.agents.contract import AgentOutput, MetaAgentOutput
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.retry_policy import RetryEngine
from app.models.types import ModelMessage, ModelRequest

_VALID_AGENT_OUTPUT = """{
  "agent_name": "injury_intelligence_agent",
  "finding": "BAL's starting QB is questionable with an ankle injury.",
  "supporting_evidence": ["injury_reports: BAL QB questionable, ankle"],
  "evidence_classification": "data_backed",
  "directional_lean": "away",
  "confidence": 0.62,
  "would_change_mind_if": "QB is upgraded to probable or active by kickoff"
}"""

_VALID_META_AGENT_OUTPUT = """{
  "agent_name": "meta_agent",
  "polarization_score": 0.15,
  "uncertainty_flag": false,
  "confidence_adjustment": -0.03,
  "reasoning": "Committee agreement is high across all four functional groups."
}"""


@pytest.mark.asyncio
async def test_end_to_end_agent_output_via_fake_adapter_and_retry_engine():
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_VALID_AGENT_OUTPUT)])
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=[ModelMessage(role="user", content="analyze injuries")],
        task_type="injury_analysis",
        agent_name="injury_intelligence_agent",
        correlation_id="corr-1",
        response_model=AgentOutput,
    )
    engine = RetryEngine()
    response = await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, AgentOutput)
    assert response.parsed.agent_name == "injury_intelligence_agent"
    assert response.parsed.confidence == 0.62


@pytest.mark.asyncio
async def test_end_to_end_meta_agent_output_via_fake_adapter_and_retry_engine():
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=_VALID_META_AGENT_OUTPUT)])
    request = ModelRequest(
        model="claude-opus-5",
        messages=[ModelMessage(role="user", content="review the committee")],
        task_type="consensus_reconciliation",
        agent_name="meta_agent",
        correlation_id="corr-2",
        response_model=MetaAgentOutput,
    )
    engine = RetryEngine()
    response = await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, MetaAgentOutput)
    assert response.parsed.confidence_adjustment == -0.03


@pytest.mark.asyncio
async def test_malformed_agent_output_is_repaired_by_retry_then_validates():
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text="not even json"), ScriptedSuccess(raw_text=_VALID_AGENT_OUTPUT)],
    )
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=[ModelMessage(role="user", content="analyze injuries")],
        task_type="injury_analysis",
        agent_name="injury_intelligence_agent",
        correlation_id="corr-3",
        response_model=AgentOutput,
    )
    engine = RetryEngine()
    response = await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, AgentOutput)
    assert response.usage.attempt_count == 2


@pytest.mark.asyncio
async def test_agent_output_missing_field_never_guessed_or_filled_in():
    """Requirement 6: malformed/incomplete output fails validation
    explicitly -- confirmed end-to-end, not just at the unit level."""
    incomplete = '{"agent_name": "weather_agent", "finding": "clear skies"}'
    adapter = FakeModelAdapter(
        provider="anthropic",
        script=[ScriptedSuccess(raw_text=incomplete), ScriptedSuccess(raw_text=incomplete)],
    )
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=[ModelMessage(role="user", content="analyze weather")],
        task_type="weather_analysis",
        agent_name="weather_agent",
        correlation_id="corr-4",
        response_model=AgentOutput,
    )
    engine = RetryEngine()
    from app.models.errors import ModelAllAttemptsFailedError

    with pytest.raises(ModelAllAttemptsFailedError):
        await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
