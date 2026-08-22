"""Tests for app.agents.committee_context (Milestone 4.6): participation
metadata distinguishing DEFERRED-BECAUSE-NO-CAPABILITY from
FAILED-DURING-THIS-RUN."""
from __future__ import annotations

from app.agents.committee_context import BUILT_AGENTS, CONFIGURED_AGENTS, build_participation_metadata
from app.orchestration.fanout import AgentRunResult, FanOutResult


def test_configured_agents_is_the_full_17_agent_roster():
    assert len(CONFIGURED_AGENTS) == 17


def test_built_agents_is_a_subset_of_configured_agents():
    assert BUILT_AGENTS <= CONFIGURED_AGENTS


def test_deferred_agents_never_counted_as_failures_when_all_built_agents_succeed():
    results = [AgentRunResult(agent_name=name, status="success") for name in sorted(BUILT_AGENTS)]
    fan_out_result = FanOutResult(status="full", results=results)

    metadata = build_participation_metadata(fan_out_result)

    assert metadata.fan_out_status == "full"
    assert metadata.successful_agents == BUILT_AGENTS
    assert metadata.failed_agents == frozenset()
    assert metadata.deferred_agents == CONFIGURED_AGENTS - BUILT_AGENTS
    assert metadata.attempted_agents == BUILT_AGENTS
    # Deferred agents (11 of 17 today) never appear in attempted/successful/failed:
    assert metadata.deferred_agents.isdisjoint(metadata.attempted_agents)


def test_committee_completeness_reflects_built_over_configured():
    fan_out_result = FanOutResult(status="full", results=[])
    metadata = build_participation_metadata(fan_out_result)
    assert metadata.committee_completeness == len(BUILT_AGENTS) / len(CONFIGURED_AGENTS)
    assert 0.0 < metadata.committee_completeness < 1.0  # honestly incomplete today


def test_a_real_runtime_failure_is_distinct_from_a_deferred_agent():
    results = [
        AgentRunResult(agent_name="injury_intelligence_agent", status="success"),
        AgentRunResult(agent_name="weather_agent", status="failed", error="timeout"),
    ]
    fan_out_result = FanOutResult(status="partial", results=results)

    metadata = build_participation_metadata(fan_out_result)

    assert metadata.fan_out_status == "partial"
    assert "weather_agent" in metadata.failed_agents
    assert "weather_agent" not in metadata.deferred_agents  # it's built and ran -- just failed this cycle
    assert "referee_tendencies_agent" in metadata.deferred_agents  # never built, never attempted
    assert "referee_tendencies_agent" not in metadata.failed_agents
