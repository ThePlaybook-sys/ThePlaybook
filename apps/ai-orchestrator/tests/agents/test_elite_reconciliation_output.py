"""Tests for app.agents.elite_reconciliation_output (Milestone 4.7,
Decision K)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.contract import MetaAgentOutput
from app.agents.elite_reconciliation_output import EliteReconciliationOutput


def _valid_output(**overrides) -> dict:
    base = {
        "agent_name": "consensus_reconciliation_agent",
        "candidate_key": "g1:DraftKings:moneyline:KC:none",
        "reasoning": "Reconciled disagreement between injury and market signals.",
        "confidence_adjustment": -0.05,
        "supporting_evidence": ["injury_intelligence_agent vs vegas_line_agent disagreement"],
        "would_change_mind_if": "Injury report is downgraded",
    }
    base.update(overrides)
    return base


def test_valid_output_parses():
    output = EliteReconciliationOutput.model_validate(_valid_output())
    assert output.confidence_adjustment == -0.05


def test_zero_adjustment_allowed():
    output = EliteReconciliationOutput.model_validate(_valid_output(confidence_adjustment=0.0))
    assert output.confidence_adjustment == 0.0


def test_positive_adjustment_rejected():
    with pytest.raises(ValidationError):
        EliteReconciliationOutput.model_validate(_valid_output(confidence_adjustment=0.1))


@pytest.mark.parametrize("missing", ["agent_name", "candidate_key", "reasoning", "confidence_adjustment", "supporting_evidence", "would_change_mind_if"])
def test_missing_required_field_rejected(missing):
    payload = _valid_output()
    del payload[missing]
    with pytest.raises(ValidationError):
        EliteReconciliationOutput.model_validate(payload)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        EliteReconciliationOutput.model_validate(_valid_output(unexpected="x"))


def test_not_interchangeable_with_meta_agent_output():
    with pytest.raises(ValidationError):
        MetaAgentOutput.model_validate(_valid_output())


def test_meta_agent_output_not_interchangeable_with_this_contract():
    meta_payload = {
        "agent_name": "meta_agent",
        "polarization_score": 0.2,
        "uncertainty_flag": False,
        "confidence_adjustment": 0.0,
        "reasoning": "reasoning",
    }
    with pytest.raises(ValidationError):
        EliteReconciliationOutput.model_validate(meta_payload)
