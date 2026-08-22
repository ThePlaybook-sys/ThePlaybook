"""Tests for the two Milestone 4.5 Market agents (Vegas Line, Closing
Line Movement). Proves: contract-valid AgentOutput end-to-end via
FakeModelAdapter, deterministic line-movement features pass into the
prompt as computed (never recomputed by the agent), and the
Closing-Line-Movement Agent's evidence never claims a confirmed close."""
from __future__ import annotations

import json

import pytest

from app.agents.closing_line_movement import ClosingLineMovementAgent
from app.agents.context import AgentContext
from app.agents.vegas_line import VegasLineAgent
from app.features.market import LineMovementFeatures
from app.features.travel import TravelFeatures
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.retry_policy import RetryEngine

_VALID_OUTPUT = json.dumps(
    {
        "agent_name": "placeholder",
        "finding": "test finding",
        "supporting_evidence": ["evidence a"],
        "evidence_classification": "data_backed",
        "directional_lean": "home",
        "confidence": 0.6,
        "would_change_mind_if": "condition changes",
    }
)


def _empty_travel() -> TravelFeatures:
    return TravelFeatures(travel_distance_miles=None, timezone_shift_hours=None, is_international_game=None, consecutive_road_games=None)


def _movement(**overrides) -> LineMovementFeatures:
    base = dict(
        sportsbook="DraftKings", market_type="spread", side="BUF", opening_price=-150, latest_price=-130,
        price_movement=20, opening_point=-3.5, latest_point=-2.5, point_movement=1.0, direction="up",
        sample_count=2, insufficient_history=False,
    )
    base.update(overrides)
    return LineMovementFeatures(**base)


def _context(**overrides) -> AgentContext:
    base = dict(
        game_id="g1", correlation_id="corr-1", injuries=None, weather=None, rest=None, stadium=None,
        travel=_empty_travel(), odds_history=None, line_movement=None,
    )
    base.update(overrides)
    return AgentContext(**base)


AGENT_CLASSES = [VegasLineAgent, ClosingLineMovementAgent]


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_each_agent_has_a_unique_name_and_task_type(agent_cls):
    agent = agent_cls()
    assert agent.agent_name
    assert agent.task_type


def test_agent_names_and_task_types_are_distinct_from_each_other():
    agents = [cls() for cls in AGENT_CLASSES]
    assert len({a.agent_name for a in agents}) == 2
    assert len({a.task_type for a in agents}) == 2


# --- missing data stays None, never fabricated ---


def test_vegas_line_agent_missing_odds_data_stays_none():
    evidence = VegasLineAgent().build_evidence(_context())
    assert evidence["odds_history"] is None
    assert evidence["line_movement"] is None


def test_closing_line_movement_agent_missing_data_stays_none_but_status_note_always_present():
    evidence = ClosingLineMovementAgent().build_evidence(_context())
    assert evidence["line_movement"] is None
    assert "closing" in evidence["closing_line_status"].lower()


# --- present data flows through as computed, never recomputed ---


def test_vegas_line_agent_evidence_includes_raw_history_and_computed_movement():
    odds_history = [{"sportsbook": "DraftKings", "market_type": "spread", "line_data": {"outcomes": []}, "captured_at": "t1"}]
    movement = [_movement()]
    context = _context(odds_history=odds_history, line_movement=movement)
    evidence = VegasLineAgent().build_evidence(context)
    assert evidence["odds_history"] is odds_history  # same object, not a copy/transform
    assert evidence["line_movement"] == [
        {
            "sportsbook": "DraftKings", "market_type": "spread", "side": "BUF", "opening_price": -150,
            "latest_price": -130, "price_movement": 20, "opening_point": -3.5, "latest_point": -2.5,
            "point_movement": 1.0, "direction": "up", "sample_count": 2, "insufficient_history": False,
        }
    ]


def test_closing_line_movement_agent_evidence_uses_latest_terminology_not_closing():
    context = _context(line_movement=[_movement()])
    evidence = ClosingLineMovementAgent().build_evidence(context)
    assert evidence["line_movement"][0]["latest_point"] == -2.5
    assert "latest_point" in evidence["line_movement"][0]
    assert "closing_point" not in evidence["line_movement"][0]
    assert "no confirmed closing-line marker" in evidence["closing_line_status"].lower()


def test_closing_line_movement_agent_does_not_expose_raw_odds_history():
    context = _context(odds_history=[{"sportsbook": "DraftKings"}], line_movement=[_movement()])
    evidence = ClosingLineMovementAgent().build_evidence(context)
    assert "odds_history" not in evidence


# --- prompt construction ---


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_build_messages_includes_agent_name_in_system_prompt(agent_cls):
    agent = agent_cls()
    messages = agent.build_messages(_context())
    assert messages[0].role == "system"
    assert agent.agent_name in messages[0].content


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_build_messages_user_content_is_exact_json_of_evidence(agent_cls):
    agent = agent_cls()
    context = _context(odds_history=[{"a": 1}], line_movement=[_movement()])
    messages = agent.build_messages(context)
    assert messages[1].role == "user"
    parsed_back = json.loads(messages[1].content)
    assert parsed_back == agent.build_evidence(context)


# --- end-to-end via FakeModelAdapter + RetryEngine ---


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
async def test_agent_produces_contract_valid_agent_output_via_fake_adapter(agent_cls):
    from app.agents.contract import AgentOutput
    from app.models.types import ModelRequest

    agent = agent_cls()
    context = _context(line_movement=[_movement()])
    valid_output = _VALID_OUTPUT.replace('"placeholder"', f'"{agent.agent_name}"')
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=valid_output)])
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=agent.build_messages(context),
        task_type=agent.task_type,
        agent_name=agent.agent_name,
        correlation_id=context.correlation_id,
        response_model=AgentOutput,
    )
    engine = RetryEngine()
    response = await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, AgentOutput)
    assert response.parsed.agent_name == agent.agent_name
