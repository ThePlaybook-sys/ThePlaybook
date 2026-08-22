"""Participation metadata and the sequential decision chain's context
(Milestone 4.6). Distinguishes DEFERRED-BECAUSE-NO-CAPABILITY from
FAILED-DURING-THIS-RUN -- Mac's explicit instruction: intentionally
deferred agents (Referee Tendencies, the 8 Matchup & Form agents, Sharp
Money, Public Betting -- none built yet, no real data exists for them)
must never be counted as runtime failures the way a genuine
`AgentRunResult(status="failed")` is.

`CONFIGURED_AGENTS` is the full Volume 4 Section 2.2-2.4 fan-out roster
(17 agents) -- the intended end state. `BUILT_AGENTS` is updated as each
milestone adds real agents; both constants live here, not duplicated
per-caller, so `committee_completeness` always reflects the same ground
truth `run_fan_out`'s own callers use.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.contract import AgentOutput
from app.agents.probability_output import ProbabilityModelOutput
from app.features.candidate import MarketCandidate
from app.features.expected_value import EVResult
from app.features.kelly import KellyResult
from app.features.risk import RiskAssessment
from app.orchestration.fanout import FanOutResult

#: CONFIRMED FROM VOLUME 4 Sections 2.2-2.4 -- the full 17-agent fan-out
#: roster (Context & Data + Matchup & Form + Market). Excludes the 4
#: Decision & Advisory agents (sequential, not fan-out) and the Meta
#: Agent (post-consensus, not a fan-out participant).
CONFIGURED_AGENTS: frozenset[str] = frozenset(
    {
        "injury_intelligence_agent",
        "weather_agent",
        "travel_fatigue_agent",
        "rest_days_agent",
        "referee_tendencies_agent",
        "offensive_matchup_agent",
        "defensive_matchup_agent",
        "historical_trends_agent",
        "team_form_agent",
        "coaching_tendencies_agent",
        "motivation_agent",
        "playoff_importance_agent",
        "player_prop_agent",
        "vegas_line_agent",
        "closing_line_movement_agent",
        "sharp_money_agent",
        "public_betting_agent",
    }
)

#: Agents that exist as real code today (Milestones 4.4-4.5). Update this
#: set, not `CONFIGURED_AGENTS`, whenever a new fan-out agent is built.
BUILT_AGENTS: frozenset[str] = frozenset(
    {
        "injury_intelligence_agent",
        "weather_agent",
        "travel_fatigue_agent",
        "rest_days_agent",
        "vegas_line_agent",
        "closing_line_movement_agent",
    }
)


@dataclass(frozen=True)
class ParticipationMetadata:
    configured_agents: frozenset[str]
    built_agents: frozenset[str]
    deferred_agents: frozenset[str]
    attempted_agents: frozenset[str]
    successful_agents: frozenset[str]
    failed_agents: frozenset[str]
    fan_out_status: str  # "full" | "partial" | "failed" -- unchanged meaning from Milestone 4.4
    committee_completeness: float  # len(built_agents) / len(configured_agents)


def participation_metadata_to_json(participation: ParticipationMetadata) -> dict:
    """Serializes `ParticipationMetadata` into a plain, JSON-safe dict
    (frozensets sorted into lists) -- Milestone 4.7's persisted
    `consensus_snapshots.participation_metadata` shape. This is the only
    durable record of what was attempted/failed/deferred for a specific
    historical consensus run, since a failed or deferred agent leaves no
    row at all in `recommendation_agent_outputs`."""
    return {
        "configured_agents": sorted(participation.configured_agents),
        "built_agents": sorted(participation.built_agents),
        "deferred_agents": sorted(participation.deferred_agents),
        "attempted_agents": sorted(participation.attempted_agents),
        "successful_agents": sorted(participation.successful_agents),
        "failed_agents": sorted(participation.failed_agents),
        "fan_out_status": participation.fan_out_status,
        "committee_completeness": participation.committee_completeness,
    }


def build_participation_metadata(fan_out_result: FanOutResult) -> ParticipationMetadata:
    """Builds `ParticipationMetadata` from a completed `FanOutResult`.
    `deferred_agents`/`committee_completeness` are derived from the
    module-level `CONFIGURED_AGENTS`/`BUILT_AGENTS` constants, not from
    anything in `fan_out_result` itself -- a deferred agent was never
    attempted, so it cannot appear in `fan_out_result.results` at all."""
    attempted = frozenset(r.agent_name for r in fan_out_result.results)
    successful = frozenset(r.agent_name for r in fan_out_result.successes)
    failed = frozenset(r.agent_name for r in fan_out_result.failures)
    return ParticipationMetadata(
        configured_agents=CONFIGURED_AGENTS,
        built_agents=BUILT_AGENTS,
        deferred_agents=CONFIGURED_AGENTS - BUILT_AGENTS,
        attempted_agents=attempted,
        successful_agents=successful,
        failed_agents=failed,
        fan_out_status=fan_out_result.status,
        committee_completeness=len(BUILT_AGENTS) / len(CONFIGURED_AGENTS),
    )


@dataclass(frozen=True)
class SequentialDecisionContext:
    """Flows through the sequential Decision & Advisory chain
    (Probability Modeling -> EV -> Risk -> Bankroll Coach), progressively
    extended via `dataclasses.replace` as each deterministic computation
    completes -- NOT `AgentContext`/`ContextDataAgent` (Decision A): these
    four agents consume the committee's own outputs and a specific
    `MarketCandidate`, never per-game raw facts."""

    game_id: str
    correlation_id: str
    candidate: MarketCandidate
    upstream_outputs: tuple[AgentOutput, ...]
    participation: ParticipationMetadata
    #: Only Bankroll Coach reads this -- `None` for every real
    #: `user_profiles` row observed in dev to date (Milestone 4.6,
    #: Decision F). Never fabricated.
    bankroll_profile: dict | None = None
    probability: ProbabilityModelOutput | None = None
    ev: EVResult | None = None
    risk: RiskAssessment | None = None
    kelly: KellyResult | None = None
