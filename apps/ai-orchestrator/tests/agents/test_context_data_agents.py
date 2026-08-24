"""Tests for the four Milestone 4.4 Context & Data agents + their shared
base class. Proves: contract-valid AgentOutput end-to-end via
FakeModelAdapter, raw facts pass into the prompt unchanged, and missing
data is never neutralized in the built evidence."""
from __future__ import annotations

import json

import pytest

from app.agents.base_agent import _LEGACY_SYSTEM_PROMPT_TEMPLATE
from app.agents.context import AgentContext
from app.agents.injury_intelligence import InjuryIntelligenceAgent
from app.agents.rest_days import RestDaysAgent
from app.agents.travel_fatigue import TravelFatigueAgent
from app.agents.weather import WeatherAgent
from app.features.travel import TravelFeatures
from app.models.fake_adapter import FakeModelAdapter, ScriptedSuccess
from app.models.retry_policy import RetryEngine


def _system_prompt(agent) -> str:
    """Milestone 4.8: build_messages no longer builds its own system
    prompt -- tests supply one explicitly, exactly as the orchestration
    layer's resolve_active_prompt result would in production. Uses the
    same legacy template the prompt_registry seed rows were generated
    from, so these tests still exercise the real production wording."""
    return _LEGACY_SYSTEM_PROMPT_TEMPLATE.format(agent_name=agent.agent_name)

_VALID_OUTPUT = json.dumps(
    {
        "agent_name": "placeholder",
        "finding": "test finding",
        "supporting_evidence": ["evidence a"],
        "evidence_classification": "data_backed",
        "directional_lean": "none",
        "confidence": 0.6,
        "would_change_mind_if": "condition changes",
    }
)


def _empty_travel() -> TravelFeatures:
    return TravelFeatures(
        travel_distance_miles=None, timezone_shift_hours=None, is_international_game=None, consecutive_road_games=None
    )


def _context(**overrides) -> AgentContext:
    base = dict(
        game_id="g1",
        correlation_id="corr-1",
        injuries=None,
        weather=None,
        rest=None,
        stadium=None,
        travel=_empty_travel(),
        odds_history=None,
        line_movement=None,
    )
    base.update(overrides)
    return AgentContext(**base)


AGENT_CLASSES = [InjuryIntelligenceAgent, WeatherAgent, TravelFatigueAgent, RestDaysAgent]


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_each_agent_has_a_unique_name_and_task_type(agent_cls):
    agent = agent_cls()
    assert agent.agent_name
    assert agent.task_type


def test_agent_names_and_task_types_are_all_distinct():
    agents = [cls() for cls in AGENT_CLASSES]
    assert len({a.agent_name for a in agents}) == len(agents)
    assert len({a.task_type for a in agents}) == len(agents)


# --- raw facts pass through unchanged, missing data never neutralized ---


def test_injury_agent_evidence_preserves_raw_injuries_dict_unchanged():
    injuries = {"value": [{"status": "questionable"}], "source": "sportsdataio", "status": "fresh"}
    context = _context(injuries=injuries)
    evidence = InjuryIntelligenceAgent().build_evidence(context)
    assert evidence["injuries"] is injuries  # the exact same object, not a copy/transform


def test_injury_agent_missing_injuries_stays_none_in_evidence():
    context = _context(injuries=None)
    evidence = InjuryIntelligenceAgent().build_evidence(context)
    assert evidence["injuries"] is None


def test_weather_agent_evidence_includes_raw_weather_and_stadium():
    weather = {"value": {"conditions": "clear"}, "status": "fresh"}
    stadium = {"name": "Arrowhead Stadium", "venue_type": "outdoor"}
    context = _context(weather=weather, stadium=stadium)
    evidence = WeatherAgent().build_evidence(context)
    assert evidence["weather"] is weather
    assert evidence["stadium"] is stadium


def test_weather_agent_missing_weather_stays_none():
    context = _context(weather=None)
    evidence = WeatherAgent().build_evidence(context)
    assert evidence["weather"] is None


def test_rest_days_agent_evidence_is_exact_dgi_rest_value():
    rest = {"rest_days": 10, "season_opener": False}
    context = _context(rest=rest)
    evidence = RestDaysAgent().build_evidence(context)
    assert evidence["rest"] is rest


def test_rest_days_agent_season_opener_stays_none_rest_days_never_fabricated_as_zero():
    rest = {"rest_days": None, "season_opener": True}
    context = _context(rest=rest)
    evidence = RestDaysAgent().build_evidence(context)
    assert evidence["rest"]["rest_days"] is None


def test_travel_fatigue_agent_evidence_reflects_computed_travel_features():
    travel = TravelFeatures(
        travel_distance_miles=857.59, timezone_shift_hours=1.0, is_international_game=False, consecutive_road_games=2
    )
    context = _context(travel=travel, rest={"rest_days": 6, "season_opener": False})
    evidence = TravelFatigueAgent().build_evidence(context)
    assert evidence["travel_distance_miles"] == 857.59
    assert evidence["timezone_shift_hours"] == 1.0
    assert evidence["is_international_game"] is False
    assert evidence["consecutive_road_games"] == 2
    assert evidence["rest"] == {"rest_days": 6, "season_opener": False}


def test_travel_fatigue_agent_missing_travel_data_stays_none_never_zero():
    context = _context(travel=_empty_travel())
    evidence = TravelFatigueAgent().build_evidence(context)
    assert evidence["travel_distance_miles"] is None
    assert evidence["timezone_shift_hours"] is None
    assert evidence["is_international_game"] is None
    assert evidence["consecutive_road_games"] is None


# --- prompt construction: raw facts serialized verbatim, never reworded ---


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_build_messages_includes_agent_name_in_system_prompt(agent_cls):
    agent = agent_cls()
    context = _context()
    messages = agent.build_messages(context, system_prompt=_system_prompt(agent))
    assert messages[0].role == "system"
    assert agent.agent_name in messages[0].content


@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
def test_build_messages_user_content_is_exact_json_of_evidence(agent_cls):
    agent = agent_cls()
    context = _context(injuries={"value": [{"status": "out"}], "status": "fresh"}, weather={"value": {}, "status": "fresh"})
    messages = agent.build_messages(context, system_prompt=_system_prompt(agent))
    assert messages[1].role == "user"
    parsed_back = json.loads(messages[1].content)
    assert parsed_back == agent.build_evidence(context)


def test_system_prompt_instructs_never_treat_null_as_neutral():
    agent = InjuryIntelligenceAgent()
    messages = agent.build_messages(_context(), system_prompt=_system_prompt(agent))
    assert "null" in messages[0].content.lower()
    assert "never" in messages[0].content.lower()


def test_system_prompt_instructs_staleness_affects_confidence():
    agent = WeatherAgent()
    messages = agent.build_messages(_context(), system_prompt=_system_prompt(agent))
    assert "stale" in messages[0].content.lower()
    assert "confidence" in messages[0].content.lower()


# --- end-to-end via FakeModelAdapter + RetryEngine ---


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
async def test_agent_produces_contract_valid_agent_output_via_fake_adapter(agent_cls):
    from app.agents.contract import AgentOutput
    from app.models.types import ModelRequest

    agent = agent_cls()
    context = _context()
    valid_output = _VALID_OUTPUT.replace('"placeholder"', f'"{agent.agent_name}"')
    adapter = FakeModelAdapter(provider="anthropic", script=[ScriptedSuccess(raw_text=valid_output)])
    request = ModelRequest(
        model="claude-sonnet-5",
        messages=agent.build_messages(context, system_prompt=_system_prompt(agent)),
        task_type=agent.task_type,
        agent_name=agent.agent_name,
        correlation_id=context.correlation_id,
        response_model=AgentOutput,
    )
    engine = RetryEngine()
    response = await engine.execute(primary=adapter, primary_provider="anthropic", request=request)
    assert isinstance(response.parsed, AgentOutput)
    assert response.parsed.agent_name == agent.agent_name
