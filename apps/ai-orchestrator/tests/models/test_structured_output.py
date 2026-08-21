"""Tests for app.models.structured_output (Milestone 4.3, requirement 6)."""
from __future__ import annotations

import pytest

from app.agents.contract import AgentOutput
from app.models.errors import ModelMalformedOutputError
from app.models.structured_output import parse_structured_output

_VALID_AGENT_OUTPUT_JSON = """{
  "agent_name": "injury_intelligence_agent",
  "finding": "BAL's starting QB is questionable with an ankle injury.",
  "supporting_evidence": ["injury_reports: BAL QB questionable, ankle"],
  "evidence_classification": "data_backed",
  "directional_lean": "away",
  "confidence": 0.62,
  "would_change_mind_if": "QB is upgraded to probable or active by kickoff"
}"""


def test_valid_json_matching_contract_parses():
    result = parse_structured_output(_VALID_AGENT_OUTPUT_JSON, AgentOutput)
    assert isinstance(result, AgentOutput)
    assert result.agent_name == "injury_intelligence_agent"


def test_not_json_at_all_raises_malformed_not_guessed():
    with pytest.raises(ModelMalformedOutputError, match="not valid JSON"):
        parse_structured_output("this is plain prose, not JSON", AgentOutput)


def test_valid_json_missing_required_field_raises_malformed():
    payload = '{"agent_name": "weather_agent"}'
    with pytest.raises(ModelMalformedOutputError, match="AgentOutput validation"):
        parse_structured_output(payload, AgentOutput)


def test_valid_json_wrong_enum_value_raises_malformed():
    payload = _VALID_AGENT_OUTPUT_JSON.replace('"data_backed"', '"pretty_sure"')
    with pytest.raises(ModelMalformedOutputError):
        parse_structured_output(payload, AgentOutput)


def test_extra_unrecognized_field_raises_malformed():
    payload = _VALID_AGENT_OUTPUT_JSON.rstrip("}") + ', "extra_field": "surprise"}'
    with pytest.raises(ModelMalformedOutputError):
        parse_structured_output(payload, AgentOutput)
