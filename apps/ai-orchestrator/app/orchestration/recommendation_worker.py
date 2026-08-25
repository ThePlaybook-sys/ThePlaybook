"""Top-level Recommendation Worker orchestration entry point (Milestone
4.9). Ties together, for ONE game:

1. Game-level fan-out, once (`app.orchestration.cycle.
   run_recommendation_cycle`) -- the 6 game-level Context & Data agents
   (Injury, Weather, Vegas Line, Closing Line Movement, Travel &
   Fatigue, Rest Days), Decision 2's shared half.
2. Candidate generation, once (`app.features.candidate_generation.
   generate_candidates_for_game`) -- V1 scope, reference-sportsbook
   policy (Decision 1), reading `REFERENCE_SPORTSBOOK_PREFERENCE` via
   `app.config`.
3. Per candidate: the shared Decision & Advisory chain, once
   (`app.orchestration.cycle.run_candidate_evaluation`).
4. Per candidate: consensus + Meta Agent, once
   (`app.orchestration.consensus.run_shared_consensus`).
5. Per candidate: Elite reconciliation, AT MOST once, only when at least
   one of this cycle's active subscribers is Elite tier
   (`app.orchestration.consensus.run_elite_reconciliation`) -- "active
   subscribers" resolved once per game via `app.persistence.
   subscriptions.read_active_subscribers` (Mac's approved answer,
   2026-08-24, to Volume 4 Section 3.1's "the worker iterates active
   users"), never re-queried per candidate.
6. Per candidate, per active subscriber: Bankroll Coach
   (`app.orchestration.cycle.run_bankroll_coach_evaluation`).

Never called directly by sports-intel-layer or any other service --
reached only through the `POST /v1/internal/recommendation-worker/run-
game` endpoint (`app.main`), itself reachable only via
`INTERNAL_SERVICE_TOKEN` (Volume 2 Section 6/10). The caller (`apps/
workers`, Milestone 4.9-7) owns game eligibility (only
`master_refresh_runs.status in ('success', 'partial')`) and derives a
stable `correlation_id` from `(master_refresh_run_id, game_id)` -- this
module trusts both are already correct, exactly like `run_recommendation_
cycle` already trusts its own `correlation_id` parameter (Milestone 4.5).

**Failure isolation (Mac's explicit requirement):** one candidate's
failure (a persistence-layer exception, not just an isolated agent/LLM
failure -- those are already isolated inside `run_candidate_evaluation`/
`run_shared_consensus`/`run_bankroll_coach_step`, which never raise)
must not prevent the other candidates in this game from being evaluated.
Each candidate's full pipeline therefore runs inside its own `try/except`,
recorded as `CandidateRunResult(status="failed", error=...)` rather than
aborting the game. Likewise, one user's Bankroll Coach call failing at
the persistence layer must not block the next user's. Game-level
failures (the game itself doesn't exist, the game-level fan-out call
itself raises) are NOT caught here -- that isolation is the caller's
job, exactly like isolating one game's failure from the rest of a slate
is Milestone 4.9-7's job, not this module's."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.agents.closing_line_movement import ClosingLineMovementAgent
from app.agents.committee_context import ParticipationMetadata, build_participation_metadata
from app.agents.injury_intelligence import InjuryIntelligenceAgent
from app.agents.rest_days import RestDaysAgent
from app.agents.travel_fatigue import TravelFatigueAgent
from app.agents.vegas_line import VegasLineAgent
from app.agents.weather import WeatherAgent
from app.config import reference_sportsbook_preference
from app.features.candidate import MarketCandidate
from app.features.candidate_generation import generate_candidates_for_game
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry
from app.orchestration.consensus import (
    EliteReconciliationResult,
    finalize_consensus,
    run_elite_reconciliation,
    run_shared_consensus,
)
from app.orchestration.cycle import run_bankroll_coach_evaluation, run_candidate_evaluation, run_recommendation_cycle
from app.persistence.games import get_game
from app.persistence.odds_snapshots import read_odds_snapshots
from app.persistence.subscriptions import read_active_subscribers

#: The 6 game-level (Milestone 4.4) Context & Data agents -- run once per
#: game via the shared fan-out, never per candidate/user. No module-level
#: registry of "all of them together" existed before this milestone;
#: every prior caller (tests, `app.agents.committee_context.
#: CONFIGURED_AGENTS`) named them individually or as bare strings.
GAME_LEVEL_AGENT_CLASSES = (
    InjuryIntelligenceAgent,
    WeatherAgent,
    VegasLineAgent,
    ClosingLineMovementAgent,
    TravelFatigueAgent,
    RestDaysAgent,
)


class RecommendationWorkerError(Exception):
    """Raised for a game-level precondition this module cannot safely
    proceed past (the game itself doesn't exist) -- never caught inside
    this module, see module docstring's failure-isolation section."""


@dataclass
class CandidateRunResult:
    candidate: MarketCandidate
    status: str  # "evaluated" | "failed"
    shared_chain_status: str | None = None  # SharedCandidateChainResult.status, when status="evaluated"
    consensus_status: str | None = None  # "no_consensus" | "computed", when status="evaluated"
    second_pass_triggered: bool = False
    bankroll_coach_user_count: int = 0
    error: str | None = None


@dataclass
class GameRecommendationResult:
    recommendation_id: str
    fan_out_status: str
    sportsbook_used: str | None
    game_skipped_reason: str | None
    candidates: list[CandidateRunResult] = field(default_factory=list)


def _parse_captured_at(row: dict) -> dict:
    value = row["captured_at"]
    if isinstance(value, datetime):
        return row
    return {**row, "captured_at": datetime.fromisoformat(value.replace("Z", "+00:00"))}


def _parse_kickoff(game: dict) -> datetime:
    value = game["scheduled_start"]
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _evaluate_one_candidate(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    game_id: str,
    correlation_id: str,
    candidate: MarketCandidate,
    home_team: str,
    away_team: str,
    upstream_outputs: tuple,
    participation: ParticipationMetadata,
    subscribers: list[dict],
    elite_tier_present: bool,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None,
    retry_engine: RetryEngine,
) -> CandidateRunResult:
    shared_chain = await run_candidate_evaluation(
        client,
        headers,
        recommendation_id=recommendation_id,
        game_id=game_id,
        correlation_id=correlation_id,
        candidate=candidate,
        upstream_outputs=upstream_outputs,
        participation=participation,
        routing_rules=routing_rules,
        adapter_registry=adapter_registry,
        model_providers=model_providers,
        retry_engine=retry_engine,
    )

    shared_consensus = await run_shared_consensus(
        client,
        headers,
        recommendation_id=recommendation_id,
        correlation_id=correlation_id,
        game_id=game_id,
        candidate=candidate,
        home_team=home_team,
        away_team=away_team,
        participation=participation,
        routing_rules=routing_rules,
        adapter_registry=adapter_registry,
        model_providers=model_providers,
        retry_engine=retry_engine,
    )

    second_pass_triggered = False
    if shared_consensus.status == "computed":
        elite: EliteReconciliationResult | None = None
        if elite_tier_present:
            elite = await run_elite_reconciliation(
                shared_consensus,
                client,
                headers,
                tier="elite",
                routing_rules=routing_rules,
                adapter_registry=adapter_registry,
                model_providers=model_providers,
                retry_engine=retry_engine,
            )
        finalize_result = await finalize_consensus(
            client,
            headers,
            recommendation_id=recommendation_id,
            candidate=candidate,
            participation=participation,
            shared=shared_consensus,
            elite=elite,
        )
        second_pass_triggered = finalize_result.second_pass_triggered

    bankroll_coach_user_count = 0
    if shared_chain.probability is not None:
        for subscriber in subscribers:
            try:
                await run_bankroll_coach_evaluation(
                    client,
                    headers,
                    recommendation_id=recommendation_id,
                    candidate=candidate,
                    shared_chain_context=shared_chain.context,
                    routing_rule=routing_rules["bankroll_coach_analysis"],
                    adapter_registry=adapter_registry,
                    user_id=subscriber["user_id"],
                    model_providers=model_providers,
                    retry_engine=retry_engine,
                )
            except Exception:  # noqa: BLE001 -- deliberate: one user's failure never blocks the next user's
                continue
            bankroll_coach_user_count += 1

    return CandidateRunResult(
        candidate=candidate,
        status="evaluated",
        shared_chain_status=shared_chain.status,
        consensus_status=shared_consensus.status,
        second_pass_triggered=second_pass_triggered,
        bankroll_coach_user_count=bankroll_coach_user_count,
    )


async def run_game_recommendation(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    correlation_id: str,
    prompt_version: str,
    agent_version: str,
    routing_rules: dict[str, dict],
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
    now: datetime | None = None,
) -> GameRecommendationResult:
    """Runs one full Recommendation Worker cycle for `game_id`. Raises
    `RecommendationWorkerError` if the game itself can't be found --
    every other failure is isolated at the candidate or user level (see
    module docstring)."""
    retry_engine = retry_engine or RetryEngine()
    now = now or datetime.now(timezone.utc)

    game = await get_game(client, headers, game_id=game_id)
    if game is None:
        raise RecommendationWorkerError(f"game_id={game_id!r} not found -- cannot run recommendation")

    recommendation_id, fan_out_result = await run_recommendation_cycle(
        client,
        headers,
        game_id=game_id,
        correlation_id=correlation_id,
        prompt_version=prompt_version,
        agent_version=agent_version,
        agents=[cls() for cls in GAME_LEVEL_AGENT_CLASSES],
        routing_rules=routing_rules,
        adapter_registry=adapter_registry,
        model_providers=model_providers,
        retry_engine=retry_engine,
    )
    participation = build_participation_metadata(fan_out_result)

    odds_rows = [_parse_captured_at(r) for r in await read_odds_snapshots(client, headers, game_id=game_id)]
    candidate_generation = generate_candidates_for_game(
        game_id=game_id,
        home_team=game["home_team"],
        away_team=game["away_team"],
        kickoff=_parse_kickoff(game),
        now=now,
        odds_rows=odds_rows,
        reference_sportsbook_preference=reference_sportsbook_preference(),
    )

    subscribers = await read_active_subscribers(client, headers)
    elite_tier_present = any(subscriber["tier"] == "elite" for subscriber in subscribers)

    candidate_results: list[CandidateRunResult] = []
    for candidate in candidate_generation.candidates:
        try:
            result = await _evaluate_one_candidate(
                client,
                headers,
                recommendation_id=recommendation_id,
                game_id=game_id,
                correlation_id=correlation_id,
                candidate=candidate,
                home_team=game["home_team"],
                away_team=game["away_team"],
                upstream_outputs=tuple(r.output for r in fan_out_result.successes),
                participation=participation,
                subscribers=subscribers,
                elite_tier_present=elite_tier_present,
                routing_rules=routing_rules,
                adapter_registry=adapter_registry,
                model_providers=model_providers,
                retry_engine=retry_engine,
            )
        except Exception as exc:  # noqa: BLE001 -- deliberate: one candidate's failure never blocks the rest
            result = CandidateRunResult(candidate=candidate, status="failed", error=str(exc))
        candidate_results.append(result)

    return GameRecommendationResult(
        recommendation_id=recommendation_id,
        fan_out_status=fan_out_result.status,
        sportsbook_used=candidate_generation.sportsbook_used,
        game_skipped_reason=candidate_generation.game_skipped_reason,
        candidates=candidate_results,
    )
