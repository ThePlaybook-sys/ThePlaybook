"""Tests for app.agents.harness (Milestone 4.2) -- the single entry point
a future agent's raw output must pass before being wired into the real
pipeline. Covers only that wrapping/rejection behavior; contract-shape
coverage itself lives in test_contract.py."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.contract import AgentOutput, MetaAgentOutput
from app.agents.harness import AgentContractError, validate_agent_output, validate_meta_agent_output


def _valid_agent_output(**overrides) -> dict:
    base = {
        "agent_name": "weather_agent",
        "finding": "Clear conditions, minimal wind -- no meaningful impact expected.",
        "supporting_evidence": ["weather: clear, 68F, 6mph wind"],
        "evidence_classification": "data_backed",
        "directional_lean": "none",
        "confidence": 0.55,
        "would_change_mind_if": "forecast shifts to heavy rain/wind before kickoff",
    }
    base.update(overrides)
    return base


def _valid_meta_agent_output(**overrides) -> dict:
    base = {
        "agent_name": "meta_agent",
        "polarization_score": 0.1,
        "uncertainty_flag": False,
        "confidence_adjustment": -0.02,
        "reasoning": "Minor disagreement among Market agents, otherwise cohesive.",
    }
    base.update(overrides)
    return base


def test_validate_agent_output_returns_typed_model_on_success():
    result = validate_agent_output(_valid_agent_output())
    assert isinstance(result, AgentOutput)
    assert result.agent_name == "weather_agent"


def test_validate_agent_output_raises_agent_contract_error_on_missing_field():
    payload = _valid_agent_output()
    del payload["confidence"]
    with pytest.raises(AgentContractError):
        validate_agent_output(payload)


def test_validate_agent_output_error_message_is_clear_and_field_specific():
    payload = _valid_agent_output()
    del payload["directional_lean"]
    with pytest.raises(AgentContractError, match="directional_lean"):
        validate_agent_output(payload)


def test_validate_agent_output_preserves_original_pydantic_error_as_cause():
    payload = _valid_agent_output()
    del payload["finding"]
    with pytest.raises(AgentContractError) as excinfo:
        validate_agent_output(payload)
    assert isinstance(excinfo.value.__cause__, ValidationError)


def test_validate_agent_output_rejects_invalid_enum_value_clearly():
    payload = _valid_agent_output(evidence_classification="pretty_sure")
    with pytest.raises(AgentContractError, match="evidence_classification"):
        validate_agent_output(payload)


def test_validate_agent_output_rejects_out_of_bounds_confidence():
    payload = _valid_agent_output(confidence=1.5)
    with pytest.raises(AgentContractError):
        validate_agent_output(payload)


def test_validate_agent_output_never_raises_bare_pydantic_validation_error():
    """Callers should only ever need to catch AgentContractError from
    this module -- a bare pydantic.ValidationError escaping would defeat
    the harness's whole purpose as a single, clear rejection boundary."""
    payload = _valid_agent_output()
    del payload["agent_name"]
    try:
        validate_agent_output(payload)
    except AgentContractError:
        pass
    except ValidationError:
        pytest.fail("validate_agent_output leaked a bare pydantic.ValidationError")


def test_validate_meta_agent_output_returns_typed_model_on_success():
    result = validate_meta_agent_output(_valid_meta_agent_output())
    assert isinstance(result, MetaAgentOutput)
    assert result.confidence_adjustment == -0.02


def test_validate_meta_agent_output_rejects_positive_confidence_adjustment():
    """The one rule Mac explicitly called out as needing a deliberate
    positive-value test, not just a code-review claim."""
    payload = _valid_meta_agent_output(confidence_adjustment=0.1)
    with pytest.raises(AgentContractError, match="confidence_adjustment must be <= 0"):
        validate_meta_agent_output(payload)


def test_validate_meta_agent_output_rejects_missing_field():
    payload = _valid_meta_agent_output()
    del payload["uncertainty_flag"]
    with pytest.raises(AgentContractError):
        validate_meta_agent_output(payload)


def test_agent_output_and_meta_agent_output_are_not_interchangeable():
    """A fan-out agent's shape must not silently validate as a Meta Agent
    output or vice versa -- they are deliberately distinct contracts
    (Volume 4 Sections 2.1 vs. 2.6), not a shared base with optional
    fields."""
    with pytest.raises(AgentContractError):
        validate_meta_agent_output(_valid_agent_output())
    with pytest.raises(AgentContractError):
        validate_agent_output(_valid_meta_agent_output())
