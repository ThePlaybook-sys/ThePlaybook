"""Tests for app.agents.contract (Milestone 4.2)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.contract import AgentOutput, DirectionalLean, EvidenceClassification, MetaAgentOutput


def _valid_agent_output(**overrides) -> dict:
    base = {
        "agent_name": "injury_intelligence_agent",
        "finding": "BAL's starting QB is questionable with an ankle injury.",
        "supporting_evidence": ["injury_reports: BAL QB questionable, ankle"],
        "evidence_classification": "data_backed",
        "directional_lean": "away",
        "confidence": 0.62,
        "would_change_mind_if": "QB is upgraded to probable or active by kickoff",
    }
    base.update(overrides)
    return base


def _valid_meta_agent_output(**overrides) -> dict:
    base = {
        "agent_name": "meta_agent",
        "polarization_score": 0.2,
        "uncertainty_flag": False,
        "confidence_adjustment": 0.0,
        "reasoning": "Committee agreement is high across all four functional groups.",
    }
    base.update(overrides)
    return base


# --- AgentOutput: valid cases ---


def test_valid_agent_output_parses():
    output = AgentOutput.model_validate(_valid_agent_output())
    assert output.agent_name == "injury_intelligence_agent"
    assert output.evidence_classification == EvidenceClassification.DATA_BACKED
    assert output.directional_lean == DirectionalLean.AWAY
    assert output.confidence == 0.62


@pytest.mark.parametrize("value", [0.0, 1.0, 0.5])
def test_confidence_accepts_full_inclusive_range(value):
    output = AgentOutput.model_validate(_valid_agent_output(confidence=value))
    assert output.confidence == value


@pytest.mark.parametrize("classification", ["data_backed", "inference", "assumption"])
def test_evidence_classification_accepts_all_three_values(classification):
    output = AgentOutput.model_validate(_valid_agent_output(evidence_classification=classification))
    assert output.evidence_classification.value == classification


@pytest.mark.parametrize("lean", ["home", "away", "over", "under", "none"])
def test_directional_lean_accepts_all_five_values(lean):
    output = AgentOutput.model_validate(_valid_agent_output(directional_lean=lean))
    assert output.directional_lean.value == lean


def test_supporting_evidence_accepts_empty_list():
    # Volume 4 Section 2.1 gives no minimum-length requirement -- an
    # assumption-classified finding may legitimately cite zero specific
    # data points.
    output = AgentOutput.model_validate(_valid_agent_output(supporting_evidence=[]))
    assert output.supporting_evidence == []


# --- AgentOutput: required-field / allowed-value rejection ---


@pytest.mark.parametrize(
    "missing_field",
    ["agent_name", "finding", "supporting_evidence", "evidence_classification", "directional_lean", "confidence", "would_change_mind_if"],
)
def test_missing_required_field_rejected(missing_field):
    payload = _valid_agent_output()
    del payload[missing_field]
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(payload)


def test_empty_agent_name_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(agent_name=""))


def test_empty_finding_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(finding=""))


def test_empty_would_change_mind_if_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(would_change_mind_if=""))


def test_unrecognized_evidence_classification_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(evidence_classification="mostly_sure"))


def test_unrecognized_directional_lean_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(directional_lean="sideways"))


@pytest.mark.parametrize("value", [-0.01, 1.01, -1.0, 2.0])
def test_confidence_outside_bounds_rejected(value):
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(confidence=value))


def test_supporting_evidence_wrong_type_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(supporting_evidence="not a list"))


def test_supporting_evidence_non_string_items_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(supporting_evidence=[1, 2, 3]))


def test_unknown_extra_field_rejected():
    payload = _valid_agent_output()
    payload["extra_field_the_agent_invented"] = "surprise"
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(payload)


def test_non_dict_input_rejected():
    with pytest.raises(ValidationError):
        AgentOutput.model_validate("not a dict")


def test_null_confidence_rejected_not_coerced_to_zero():
    # Null-not-neutral discipline carried to the output side: a None
    # confidence must be rejected outright, never silently treated as 0.
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(confidence=None))


def test_null_directional_lean_rejected_not_coerced_to_none_value():
    # `directional_lean="none"` (the string) is a valid, explicit choice;
    # a Python None is a different thing entirely and must be rejected.
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(_valid_agent_output(directional_lean=None))


# --- MetaAgentOutput: valid cases ---


def test_valid_meta_agent_output_parses():
    output = MetaAgentOutput.model_validate(_valid_meta_agent_output())
    assert output.agent_name == "meta_agent"
    assert output.confidence_adjustment == 0.0


@pytest.mark.parametrize("value", [0.0, -0.01, -1.0])
def test_confidence_adjustment_accepts_zero_and_negative(value):
    output = MetaAgentOutput.model_validate(_valid_meta_agent_output(confidence_adjustment=value))
    assert output.confidence_adjustment == value


# --- MetaAgentOutput: the hard confidence_adjustment <= 0 rule ---


@pytest.mark.parametrize("value", [0.01, 0.5, 1.0])
def test_positive_confidence_adjustment_rejected(value):
    """The hard rule from Volume 4 Section 2.6: the Meta Agent can never
    boost confidence. A deliberate attempt to produce a positive
    adjustment must be rejected at construction time."""
    with pytest.raises(ValidationError, match="confidence_adjustment must be <= 0"):
        MetaAgentOutput.model_validate(_valid_meta_agent_output(confidence_adjustment=value))


@pytest.mark.parametrize(
    "missing_field",
    ["agent_name", "polarization_score", "uncertainty_flag", "confidence_adjustment", "reasoning"],
)
def test_meta_agent_missing_required_field_rejected(missing_field):
    payload = _valid_meta_agent_output()
    del payload[missing_field]
    with pytest.raises(ValidationError):
        MetaAgentOutput.model_validate(payload)


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_meta_agent_polarization_score_outside_bounds_rejected(value):
    with pytest.raises(ValidationError):
        MetaAgentOutput.model_validate(_valid_meta_agent_output(polarization_score=value))


def test_meta_agent_empty_reasoning_rejected():
    with pytest.raises(ValidationError):
        MetaAgentOutput.model_validate(_valid_meta_agent_output(reasoning=""))


def test_meta_agent_unknown_extra_field_rejected():
    payload = _valid_meta_agent_output()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        MetaAgentOutput.model_validate(payload)
