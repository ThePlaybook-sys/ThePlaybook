"""Tests for app.demo.scenario (DEMO-3 schema layer). Pure -- no HTTP, no
Supabase, no worker/adapter construction; that's app.demo.runner's job and
tests/test_demo_scenario_runner.py's coverage.
"""
from __future__ import annotations

import pytest

from app.demo.scenario import (
    VALID_ACTIONS,
    Scenario,
    ScenarioStep,
    ScenarioValidationError,
    load_scenario,
)

BASE = {
    "scenario_id": "demo-basic",
    "title": "Basic",
    "description": "test",
    "version": "1.0.0",
    "phase_requirements": ["phase_3"],
    "initial_virtual_now": "2026-09-14T12:00:00+00:00",
    "slate": {},
    "steps": [
        {"virtual_now": "2026-09-14T12:00:00+00:00", "action": "run_odds_worker"},
        {"virtual_now": "2026-09-14T13:00:00+00:00", "action": "checkpoint", "checkpoint_note": "hi"},
    ],
}


def test_load_scenario_happy_path():
    scenario = load_scenario(BASE)
    assert scenario.scenario_id == "demo-basic"
    assert len(scenario.steps) == 2
    assert scenario.steps[0].action == "run_odds_worker"
    assert scenario.steps[1].checkpoint_note == "hi"
    assert scenario.steps[0].provider_data == {}
    assert scenario.steps[0].inject_failure is False
    assert scenario.steps[0].worker_kwargs == {}


def test_missing_top_level_field_raises():
    data = {k: v for k, v in BASE.items() if k != "title"}
    with pytest.raises(ScenarioValidationError, match="title"):
        load_scenario(data)


def test_missing_step_field_raises():
    data = {**BASE, "steps": [{"virtual_now": "2026-09-14T12:00:00+00:00"}]}
    with pytest.raises(ScenarioValidationError, match="action"):
        load_scenario(data)


def test_invalid_action_raises():
    data = {**BASE, "steps": [{"virtual_now": "2026-09-14T12:00:00+00:00", "action": "delete_everything"}]}
    with pytest.raises(ScenarioValidationError, match="unknown scenario action"):
        load_scenario(data)


def test_malformed_initial_virtual_now_raises():
    data = {**BASE, "initial_virtual_now": "not-a-date"}
    with pytest.raises(ScenarioValidationError, match="initial_virtual_now"):
        load_scenario(data)


def test_malformed_step_virtual_now_raises():
    data = {**BASE, "steps": [{"virtual_now": "not-a-date", "action": "checkpoint"}]}
    with pytest.raises(ScenarioValidationError, match="virtual_now"):
        load_scenario(data)


def test_empty_scenario_id_raises():
    data = {**BASE, "scenario_id": ""}
    with pytest.raises(ScenarioValidationError, match="scenario_id"):
        load_scenario(data)


def test_empty_steps_raises():
    data = {**BASE, "steps": []}
    with pytest.raises(ScenarioValidationError, match="no steps"):
        load_scenario(data)


def test_step_time_moving_backward_raises():
    data = {
        **BASE,
        "steps": [
            {"virtual_now": "2026-09-14T13:00:00+00:00", "action": "checkpoint"},
            {"virtual_now": "2026-09-14T12:00:00+00:00", "action": "checkpoint"},
        ],
    }
    with pytest.raises(ScenarioValidationError, match="must move forward"):
        load_scenario(data)


def test_step_time_equal_to_previous_is_allowed():
    data = {
        **BASE,
        "steps": [
            {"virtual_now": "2026-09-14T12:00:00+00:00", "action": "checkpoint"},
            {"virtual_now": "2026-09-14T12:00:00+00:00", "action": "checkpoint"},
        ],
    }
    scenario = load_scenario(data)
    assert len(scenario.steps) == 2


def test_first_step_before_initial_virtual_now_raises():
    data = {**BASE, "initial_virtual_now": "2026-09-14T14:00:00+00:00"}
    with pytest.raises(ScenarioValidationError, match="must move forward"):
        load_scenario(data)


def test_phase_requirements_only_phase_3_allowed():
    data = {**BASE, "phase_requirements": ["phase_4"]}
    with pytest.raises(ScenarioValidationError, match="DEMO-3 may only build phase_3 scenarios"):
        load_scenario(data)


def test_phase_requirements_empty_is_allowed():
    data = {**BASE, "phase_requirements": []}
    scenario = load_scenario(data)
    assert scenario.phase_requirements == []


def test_provider_data_inject_failure_and_worker_kwargs_round_trip():
    data = {
        **BASE,
        "steps": [
            {
                "virtual_now": "2026-09-14T12:00:00+00:00",
                "action": "run_odds_worker",
                "provider_data": {"odds": {"g1": [{"foo": "bar"}]}},
                "inject_failure": True,
                "worker_kwargs": {"target_game_ids": ["g1"]},
            },
        ],
    }
    scenario = load_scenario(data)
    step = scenario.steps[0]
    assert step.provider_data == {"odds": {"g1": [{"foo": "bar"}]}}
    assert step.inject_failure is True
    assert step.worker_kwargs == {"target_game_ids": ["g1"]}


def test_scenario_step_direct_construction_validates_action_too():
    with pytest.raises(ScenarioValidationError):
        ScenarioStep(virtual_now=__import__("datetime").datetime(2026, 1, 1), action="not_a_real_action")


def test_valid_actions_is_the_documented_fixed_vocabulary():
    assert VALID_ACTIONS == {
        "advance_time",
        "run_master_refresh",
        "run_odds_worker",
        "run_player_props_worker",
        "run_injury_worker",
        "run_weather_worker",
        "run_news_worker",
        "run_pregame_worker",
        "run_postgame_worker",
        "checkpoint",
    }
