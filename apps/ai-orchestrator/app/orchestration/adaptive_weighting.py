"""Milestone 5.5's Adaptive Agent Weighting orchestration -- ties the
deterministic engine (`app.features.adaptive_weighting`) to persistence
(`app.persistence.adaptive_weighting`) for one committee-wide evaluation
window. Reachable only from `app.main`'s new internal endpoint, called by
`apps/workers` on a schedule (Decision 21 -- `worker-scheduled`, no new
Railway service).

**V1 is PROPOSE-ONLY (Decision 2) -- read this before touching this
module.** Nothing here writes `agents.current_weight`. Every persisted
`adaptive_weight_proposals` row's `applied_weight` column is always
`NULL`; there is no code path in this module, or anywhere in this
milestone, that could set it. Applying a proposal is a separate, not-yet
-authorized future capability.

**Evidence-gathering scope, disclosed:** this module reads EVERY
`recommendation_leg_grade_events` row (reduced to the latest,
non-superseded row per leg -- Decision 17), filters to `WIN`/`LOSS`
terminal outcomes only, and for each such leg reads that leg's own
game-level committee outputs (`candidate_key IS NULL` rows -- the same
nine voting agents Milestone 5.4's own agent-correctness classifier
already targets). This is an unbounded scan today (matching Milestone
5.4's own accepted MVP scope limitation for its `bankroll_preservation`
sweep) -- acceptable given current data volumes, flagged for future
optimization once real evidence volume grows."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from app.features.adaptive_weighting import (
    ADAPTIVE_WEIGHT_LEARNING_RATE,
    ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE,
    WEIGHTING_VERSION,
    Observation,
    ObservationInput,
    aggregate_roi,
    check_sample_size_guardrail,
    classify_and_price_observation,
    clamp_to_max_change,
    committee_average_roi as compute_committee_average_roi,
    compute_performance_delta,
    compute_raw_proposed_weight,
    validate_evaluation_window,
)
from app.features.consensus import resolve_candidate_direction
from app.features.postgame_review import realized_direction
from app.persistence.adaptive_weighting import (
    persist_proposal,
    persist_proposal_observation,
    read_all_agents,
    read_latest_leg_grade_events,
    read_recommendation_legs_by_ids,
)
from app.persistence.consensus_snapshots import read_game_level_agent_outputs
from app.persistence.games import get_game_for_grading

_TERMINAL_DIRECTIONAL = ("WIN", "LOSS")


@dataclass
class AgentEvaluationResult:
    agent_id: str
    agent_name: str
    status: str  # "created" | "unchanged" | "corrected"
    proposal_status: str  # "proposed" | "rejected_insufficient_sample"
    sample_size: int
    roi: float | None
    performance_delta: float | None
    guardrail_adjusted_proposed_weight: float | None


@dataclass
class CommitteeEvaluationResult:
    evaluation_window_start: str
    evaluation_window_end: str
    committee_average_roi: float | None
    agents: list[AgentEvaluationResult] = field(default_factory=list)


def _latest_leg_grade_events(rows: list[dict]) -> dict[str, dict]:
    """Reduces an ordered (`recommendation_leg_id.asc, created_at.asc`)
    list to the latest row per leg -- Decision 17's "latest authoritative,
    non-superseded grade," computed in Python since PostgREST has no
    "latest per group" query."""
    latest: dict[str, dict] = {}
    for row in rows:
        latest[row["recommendation_leg_id"]] = row
    return latest


async def _gather_observations_by_agent(
    client: httpx.AsyncClient, headers: dict, *, window_start: date, window_end: date
) -> dict[str, list[tuple[Observation, str]]]:
    """Returns `{agent_name: [(Observation, directional_lean), ...]}` for
    every classifiable observation whose leg's latest grade became
    authoritative within `[window_start, window_end)`. Only agent NAMES
    are known at this layer (game-level outputs are read by name); the
    caller maps names to `agents.id`."""
    all_events = await read_latest_leg_grade_events(client, headers)
    latest_by_leg = _latest_leg_grade_events(all_events)

    qualifying_events = []
    for event in latest_by_leg.values():
        if event["outcome"] not in _TERMINAL_DIRECTIONAL:
            continue
        graded_at = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")).date()
        if not (window_start <= graded_at < window_end):
            continue
        qualifying_events.append(event)

    if not qualifying_events:
        return {}

    leg_ids = [e["recommendation_leg_id"] for e in qualifying_events]
    legs_by_id = {leg["id"]: leg for leg in await read_recommendation_legs_by_ids(client, headers, leg_ids=leg_ids)}

    observations_by_agent: dict[str, list[tuple[Observation, str]]] = {}
    for event in qualifying_events:
        leg = legs_by_id.get(event["recommendation_leg_id"])
        if leg is None:
            continue
        game = await get_game_for_grading(client, headers, game_id=leg["game_id"])
        if game is None:
            continue
        try:
            candidate_direction = resolve_candidate_direction(
                market_type=leg["market_type"], selection=leg["selection"], home_team=game["home_team"], away_team=game["away_team"]
            )
        except Exception:  # noqa: BLE001 -- an unresolvable leg simply contributes no observations
            continue
        realized = realized_direction(candidate_direction=candidate_direction, outcome=event["outcome"])
        if realized is None:
            continue

        agent_rows = await read_game_level_agent_outputs(client, headers, recommendation_id=leg["recommendation_id"])
        for agent_row in agent_rows:
            observation = classify_and_price_observation(
                ObservationInput(
                    recommendation_leg_grade_event_id=event["id"],
                    directional_lean=agent_row["directional_lean"],
                    realized_direction=realized,
                    outcome=event["outcome"],
                    decimal_odds=leg["decimal_odds"],
                )
            )
            if observation is None:
                continue
            observations_by_agent.setdefault(agent_row["agent_name"], []).append((observation, agent_row["directional_lean"]))

    return observations_by_agent


async def evaluate_committee(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    evaluation_window_start: date,
    evaluation_window_end: date,
    learning_rate: float = ADAPTIVE_WEIGHT_LEARNING_RATE,
    weighting_version: str = WEIGHTING_VERSION,
) -> CommitteeEvaluationResult:
    """Evaluates every agent in `agents` against classifiable observations
    in `[evaluation_window_start, evaluation_window_end)`. Raises
    `app.features.adaptive_weighting.EvaluationWindowTooShortError`
    (Decision 8) BEFORE evaluating or persisting anything for any agent
    when the window is narrower than the 90-day hard minimum -- the
    whole evaluation request is rejected, never silently widened."""
    validate_evaluation_window(window_start_days_before_end=(evaluation_window_end - evaluation_window_start).days)

    agents = await read_all_agents(client, headers)
    observations_by_agent = await _gather_observations_by_agent(
        client, headers, window_start=evaluation_window_start, window_end=evaluation_window_end
    )

    agent_rois: dict[str, float | None] = {}
    for agent in agents:
        observations = [obs for obs, _lean in observations_by_agent.get(agent["name"], [])]
        agent_rois[agent["id"]] = aggregate_roi(observations)

    committee_avg = compute_committee_average_roi(list(agent_rois.values()))

    results: list[AgentEvaluationResult] = []
    for agent in agents:
        agent_observations = observations_by_agent.get(agent["name"], [])
        sample_size = len(agent_observations)
        roi = agent_rois[agent["id"]]
        performance_delta = compute_performance_delta(agent_roi=roi, committee_average_roi_value=committee_avg)
        raw_weight = compute_raw_proposed_weight(
            current_weight=float(agent["current_weight"]), learning_rate=learning_rate, performance_delta=performance_delta
        )
        clamped_weight = clamp_to_max_change(current_weight=float(agent["current_weight"]), raw_proposed_weight=raw_weight)

        meets_sample_guardrail = check_sample_size_guardrail(sample_size)
        proposal_status = "proposed" if meets_sample_guardrail else "rejected_insufficient_sample"
        rejection_reason = (
            None
            if meets_sample_guardrail
            else f"sample_size={sample_size} is below the required minimum of {ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE}"
        )

        persist_status, proposal_id = await persist_proposal(
            client,
            headers,
            agent_id=agent["id"],
            previous_weight=float(agent["current_weight"]),
            raw_proposed_weight=raw_weight,
            guardrail_adjusted_proposed_weight=clamped_weight,
            evaluation_window_start=evaluation_window_start.isoformat(),
            evaluation_window_end=evaluation_window_end.isoformat(),
            sample_size=sample_size,
            roi=roi,
            committee_average_roi=committee_avg,
            performance_delta=performance_delta,
            learning_rate=learning_rate,
            weighting_version=weighting_version,
            status=proposal_status,
            rejection_reason=rejection_reason,
        )

        if persist_status in ("created", "corrected"):
            for observation, lean in agent_observations:
                await persist_proposal_observation(
                    client,
                    headers,
                    proposal_id=proposal_id,
                    recommendation_leg_grade_event_id=observation.recommendation_leg_grade_event_id,
                    classification=observation.classification,
                    directional_lean=lean,
                    notional_pnl=observation.notional_pnl,
                )

        results.append(
            AgentEvaluationResult(
                agent_id=agent["id"],
                agent_name=agent["name"],
                status=persist_status,
                proposal_status=proposal_status,
                sample_size=sample_size,
                roi=roi,
                performance_delta=performance_delta,
                guardrail_adjusted_proposed_weight=clamped_weight,
            )
        )

    return CommitteeEvaluationResult(
        evaluation_window_start=evaluation_window_start.isoformat(),
        evaluation_window_end=evaluation_window_end.isoformat(),
        committee_average_roi=committee_avg,
        agents=results,
    )
