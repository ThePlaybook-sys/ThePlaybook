"""Tests for app.agents.probability_output (Milestone 4.6, Decision B)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.contract import AgentOutput
from app.agents.probability_output import ProbabilityModelOutput


def _valid_probability_output(**overrides) -> dict:
    base = {
        "agent_name": "probability_modeling_agent",
        "candidate_key": "g1:DraftKings:moneyline:Kansas City Chiefs:none",
        "selection": "Kansas City Chiefs",
        "modeled_probability": 0.57,
        "confidence_in_probability": 0.72,
        "reasoning": "Committee findings lean toward KC covering the injury/rest edge.",
        "supporting_evidence": ["injury_intelligence_agent: BAL QB questionable"],
        "would_change_mind_if": "BAL's QB is upgraded to probable",
    }
    base.update(overrides)
    return base


def test_valid_probability_output_parses():
    output = ProbabilityModelOutput.model_validate(_valid_probability_output())
    assert output.modeled_probability == 0.57
    assert output.confidence_in_probability == 0.72


def test_modeled_probability_and_confidence_in_probability_are_independent_fields():
    output = ProbabilityModelOutput.model_validate(
        _valid_probability_output(modeled_probability=0.57, confidence_in_probability=0.90)
    )
    assert output.modeled_probability != output.confidence_in_probability


@pytest.mark.parametrize("field", ["modeled_probability", "confidence_in_probability"])
@pytest.mark.parametrize("value", [0.0, 1.0, 0.5])
def test_both_probability_fields_accept_full_inclusive_range(field, value):
    output = ProbabilityModelOutput.model_validate(_valid_probability_output(**{field: value}))
    assert getattr(output, field) == value


@pytest.mark.parametrize("field", ["modeled_probability", "confidence_in_probability"])
@pytest.mark.parametrize("value", [-0.01, 1.01, 2.0, -1.0])
def test_both_probability_fields_reject_out_of_bounds(field, value):
    with pytest.raises(ValidationError):
        ProbabilityModelOutput.model_validate(_valid_probability_output(**{field: value}))


@pytest.mark.parametrize(
    "missing_field",
    ["agent_name", "candidate_key", "selection", "modeled_probability", "confidence_in_probability", "reasoning", "would_change_mind_if"],
)
def test_missing_required_field_rejected(missing_field):
    payload = _valid_probability_output()
    del payload[missing_field]
    with pytest.raises(ValidationError):
        ProbabilityModelOutput.model_validate(payload)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        ProbabilityModelOutput.model_validate(_valid_probability_output(unexpected_field="x"))


def test_empty_candidate_key_rejected():
    with pytest.raises(ValidationError):
        ProbabilityModelOutput.model_validate(_valid_probability_output(candidate_key=""))


def test_does_not_have_a_confidence_field_like_agent_output():
    """Decision B: ProbabilityModelOutput must never expose a bare
    `confidence` field that could be confused with AgentOutput's -- its
    probability-shaped fields are explicitly named."""
    assert "confidence" not in ProbabilityModelOutput.model_fields


def test_not_interchangeable_with_agent_output():
    payload = _valid_probability_output()
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(payload)
