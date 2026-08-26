"""Tests for app.features.postgame_review (Milestone 5.4) -- the
deterministic half of the narrative layer: realized_direction and
agent-correctness classification. Pure functions, no I/O."""
from __future__ import annotations

from app.features.postgame_review import POSTGAME_REVIEW_VERSION, classify_agent_correctness, realized_direction


def test_realized_direction_is_candidate_direction_on_win():
    assert realized_direction(candidate_direction="home", outcome="WIN") == "home"
    assert realized_direction(candidate_direction="over", outcome="WIN") == "over"


def test_realized_direction_is_opposite_on_loss():
    assert realized_direction(candidate_direction="home", outcome="LOSS") == "away"
    assert realized_direction(candidate_direction="under", outcome="LOSS") == "over"


def test_realized_direction_none_for_non_terminal_outcomes():
    for outcome in ("PUSH", "VOID_NO_ACTION", "PENDING_MISSING_DATA"):
        assert realized_direction(candidate_direction="home", outcome=outcome) is None


def test_realized_direction_none_when_no_candidate_direction():
    assert realized_direction(candidate_direction=None, outcome="WIN") is None


def test_classify_agent_correctness_none_when_no_realized_direction():
    rows = [{"agent_name": "weather_agent", "directional_lean": "home"}]
    correct, underperforming = classify_agent_correctness(rows, realized_direction_value=None)
    assert correct is None
    assert underperforming is None


def test_classify_agent_correctness_splits_matching_and_opposing_agents():
    rows = [
        {"agent_name": "weather_agent", "directional_lean": "home"},
        {"agent_name": "injury_agent", "directional_lean": "away"},
        {"agent_name": "news_agent", "directional_lean": "none"},
    ]
    correct, underperforming = classify_agent_correctness(rows, realized_direction_value="home")
    assert correct == ["weather_agent"]
    assert underperforming == ["injury_agent"]


def test_classify_agent_correctness_does_not_classify_off_axis_or_no_lean():
    rows = [{"agent_name": "totals_agent", "directional_lean": "over"}]
    correct, underperforming = classify_agent_correctness(rows, realized_direction_value="home")
    assert correct == []
    assert underperforming == []


def test_postgame_review_version_is_frozen_string():
    assert POSTGAME_REVIEW_VERSION == "v1"
