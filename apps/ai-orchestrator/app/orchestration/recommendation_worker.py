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
from app.features.candidate import MarketCandidate, candidate_key as compute_candidate_key
from app.features.candidate_generation import generate_candidates_for_game
from app.features.strategy import EvaluatedCandidate
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
from app.persistence.recommendations import (
    mark_recommendation_cycle_completed,
    read_completed_paid_cycle_for_game,
    read_recommendation_by_correlation_id,
)
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
    #: Milestone 5.1 -- set only when this candidate reached a finalized
    #: consensus_snapshots row AND has a computable EV (i.e. `candidate.
    #: american_odds is not None`). This is the raw material the Strategy
    #: Engine (`app.features.strategy`) needs -- qualification filtering
    #: (Decision X) happens in the Strategy Engine itself, not here; this
    #: module hands over every candidate that COULD be evaluated for
    #: Strategy, not just the ones that ultimately qualify.
    strategy_input: EvaluatedCandidate | None = None


#: HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20). One internal status, reused at
#: candidate level and game level, for the state MANSA previously had no word
#: for: the analytical/model pipeline did not produce enough usable evidence
#: to make a qualification decision.
#:
#: **This is deliberately NOT a customer-facing product outcome.** HQ's
#: decision is explicit that No Bet keeps its existing meaning -- "analysis
#: completed and nothing qualified" -- and that an analysis failure is simply
#: not a No Bet. So this status lives only in the internal worker contract;
#: no new `GameDecision.outcome`, no new `recommendation_products` type, and
#: no change to any existing API shape.
#:
#: Named rather than reusing the existing `"failed"`, because `"failed"`
#: already means "this candidate raised an exception". An incomplete analysis
#: raised nothing -- every step returned, they just returned nothing usable --
#: and collapsing the two would lose exactly the distinction that let this
#: defect hide.
ANALYSIS_INCOMPLETE = "analysis_incomplete"


def _analysis_incomplete(shared_chain, strategy_input) -> bool:
    """Whether this candidate's analytical chain failed to produce the
    minimum usable output the Strategy Engine needs.

    A candidate is incomplete when it has NO `strategy_input` **and** the
    chain never produced an EV at all -- i.e. the probability -> EV -> risk
    sequence did not complete far enough to decide anything.

    It is NOT incomplete when `shared_chain.ev` exists but carries no
    `ev_per_dollar`. That is the documented, legitimate case of a candidate
    with no `american_odds`: the analysis ran to completion and simply found
    nothing EV-computable, which is real information rather than a failure.

    A `partial` chain that still yielded a usable `strategy_input` is also
    not incomplete -- HQ's STATE 4: some degradation, but a valid decision
    survives. The degradation stays visible via `shared_chain_status`.
    """
    if strategy_input is not None:
        return False
    return shared_chain.ev is None


@dataclass
class GameRecommendationResult:
    #: `None` only for `status="skipped_ineligible"` -- the deterministic
    #: pre-LLM gate returns before any `recommendations` row is created,
    #: because nothing was computed and the next cycle must be free to
    #: retry once odds arrive.
    recommendation_id: str | None
    fan_out_status: str
    sportsbook_used: str | None
    game_skipped_reason: str | None
    candidates: list[CandidateRunResult] = field(default_factory=list)
    #: Pre-Phase-6 Operational Readiness Gate, Decision 5 -- "computed"
    #: (the normal path: the agent committee actually ran this call) or
    #: "skipped_already_computed" (this exact `correlation_id` already
    #: reached `cycle_completed_at` on a PRIOR call; nothing here was
    #: recomputed, `candidates` is `[]`). Callers (`apps/workers`) must
    #: treat a skipped game as contributing no NEW strategy input this
    #: cycle -- it already contributed its own, in the earlier cycle that
    #: actually computed it.
    status: str = "computed"


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
    strategy_input: EvaluatedCandidate | None = None
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

        # Milestone 5.1: the Strategy Engine needs this candidate's frozen
        # market fields + EV + final confidence. `candidate`/`shared_chain.ev`
        # are the SAME in-memory objects this cycle already computed --
        # never re-derived or re-read back from persistence, so what
        # Strategy sees is exactly what was evaluated, not a later,
        # possibly-moved price (Invariant 7's "never a live reference"
        # discipline, applied one step earlier at the source).
        if shared_chain.ev is not None and shared_chain.ev.ev_per_dollar is not None:
            strategy_input = EvaluatedCandidate(
                game_id=game_id,
                recommendation_id=recommendation_id,
                consensus_snapshot_id=finalize_result.consensus_snapshot_id,
                candidate_key=compute_candidate_key(candidate),
                market_type=candidate.market_type,
                selection=candidate.selection,
                sportsbook=candidate.sportsbook,
                american_odds=candidate.american_odds,
                point=candidate.point,
                decimal_odds=shared_chain.ev.decimal_odds,
                ev_per_dollar=shared_chain.ev.ev_per_dollar,
                final_aggregate_confidence=finalize_result.final_aggregate_confidence,
            )

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
        # HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20). `evaluated` used to be
        # returned unconditionally here, including when the analytical chain
        # had produced nothing at all. That was the quiet half of the
        # empty-No-Bet defect: a candidate with no usable output reported
        # SUCCESS, so neither the nested failure census nor any status check
        # could see it, and the game went on to be written as an active
        # No Bet. See `_analysis_incomplete` for the precise distinction.
        status=ANALYSIS_INCOMPLETE if _analysis_incomplete(shared_chain, strategy_input) else "evaluated",
        shared_chain_status=shared_chain.status,
        consensus_status=shared_consensus.status,
        second_pass_triggered=second_pass_triggered,
        bankroll_coach_user_count=bankroll_coach_user_count,
        strategy_input=strategy_input,
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
    module docstring).

    **Pre-Phase-6 Operational Readiness Gate, Decision 5.** Before doing
    ANY of the expensive work below (game-level fan-out, candidate
    generation, the Decision & Advisory chain, consensus, Bankroll
    Coach), checks whether this exact `correlation_id` already reached
    `recommendations.cycle_completed_at` on a prior call -- if so, returns
    immediately with `status="skipped_already_computed"` and empty
    `candidates`, recomputing nothing. This is the DB-authoritative check
    Decision 5 requires: a `recommendations` row existing is NOT
    sufficient (Milestone 4.9's own correlation-id upsert creates that
    row as the very FIRST step, before any real work happens -- a crash
    partway through would otherwise look identical to a completed run);
    only `cycle_completed_at IS NOT NULL` means the cycle genuinely ran
    to its normal end. A genuinely new Master Refresh run always
    produces a new `correlation_id` (Milestone 4.9's own `f"{run_id}:
    {game_id}"` derivation, unchanged here), so this can never block a
    legitimately new cycle for the same game."""
    retry_engine = retry_engine or RetryEngine()
    now = now or datetime.now(timezone.utc)

    game = await get_game(client, headers, game_id=game_id)
    if game is None:
        raise RecommendationWorkerError(f"game_id={game_id!r} not found -- cannot run recommendation")

    existing = await read_recommendation_by_correlation_id(client, headers, correlation_id=correlation_id)
    if existing is not None and existing.get("cycle_completed_at") is not None:
        return GameRecommendationResult(
            recommendation_id=existing["id"],
            fan_out_status="skipped_already_computed",
            sportsbook_used=None,
            game_skipped_reason=None,
            candidates=[],
            status="skipped_already_computed",
        )

    # HQ Recomputation V1 (2026-09-18): one successful paid cycle per
    # canonical game, and `run_id` is explicitly NOT the reason a game
    # becomes eligible again. The check above is correlation-scoped and so
    # only ever protects a retry within ONE master_refresh_run; this one is
    # keyed on the game itself and therefore holds across days.
    #
    # Defence in depth: `apps/workers` already excludes completed games
    # from the slate. This is the same rule at the service that actually
    # spends, so a caller that skipped that filter still cannot buy a
    # second committee run for a finished game. Zero LLM calls either way.
    completed_paid = await read_completed_paid_cycle_for_game(client, headers, game_id=game_id)
    if completed_paid is not None:
        return GameRecommendationResult(
            recommendation_id=completed_paid["id"],
            fan_out_status="skipped_already_computed",
            sportsbook_used=None,
            game_skipped_reason="game_already_completed_a_paid_cycle",
            candidates=[],
            status="skipped_already_computed",
        )

    # ---------------------------------------------------------------
    # DETERMINISTIC PRE-LLM ELIGIBILITY GATE (2026-09-18).
    #
    # Everything from here to the fan-out is free: database reads and
    # pure functions, no model request of any kind. It runs FIRST, and
    # that ordering is the whole point of this block.
    #
    # It used to run second. The 6-agent game-level fan-out executed
    # before candidate generation, so a game with no odds, stale odds, or
    # no configured reference sportsbook still cost 6 LLM calls to
    # discover it was ineligible -- and an unset
    # `REFERENCE_SPORTSBOOK_PREFERENCE` raised only AFTER the committee
    # had already run. On 2026-09-17 that shape meant 257 games each
    # invoked the fan-out before anything could stop them.
    #
    # Nothing about scoring, probability, EV or candidate construction
    # changes here -- `generate_candidates_for_game` is called with the
    # identical arguments it always was, and still owns sportsbook
    # selection and freshness. Only WHEN it is called has changed.
    # ---------------------------------------------------------------
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

    # No candidates means no work a committee could do. Return before any
    # agent runs, with the reason `generate_candidates_for_game` already
    # computed -- `no_configured_sportsbook_has_fresh_data` when no
    # preferred book had fresh V1-market data, which covers "no odds at
    # all", "stale odds", and "reference sportsbook unavailable" alike.
    #
    # `cycle_completed_at` is deliberately NOT marked and no
    # `recommendations` row is created: nothing was computed, so the next
    # cycle must be free to try again once odds arrive. That is also what
    # stops a deterministically-ineligible game from accumulating one
    # orphan marker row per run.
    if not candidate_generation.candidates:
        return GameRecommendationResult(
            recommendation_id=None,
            fan_out_status="skipped_ineligible",
            sportsbook_used=candidate_generation.sportsbook_used,
            game_skipped_reason=candidate_generation.game_skipped_reason or "no_candidates_generated",
            candidates=[],
            status="skipped_ineligible",
        )

    # ---------------------------------------------------------------
    # Past this line, and only past it, LLM work is authorized.
    # ---------------------------------------------------------------
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

    # HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20), STATE 3. Analysis was
    # attempted but produced ZERO usable analytical candidates -- every
    # candidate either raised or came back with no EV at all. That is an
    # analysis failure, and an analysis failure is NOT a No Bet.
    #
    # Returning before the completion marker is the whole point. Left as it
    # was, this path stamped `cycle_completed_at`, handed an empty candidate
    # list to the Strategy Engine, and got back `no_bet` -- which the Engine
    # cannot distinguish from "evaluated, nothing qualified", because in both
    # cases nothing qualifies. The game was then permanently consumed by
    # Recomputation V1 while having produced no intelligence at all.
    #
    # `cycle_completed_at` stays NULL here, exactly as it does for a crash,
    # so the game remains eligible for bounded retry on the next cycle.
    if candidate_results and not any(c.strategy_input is not None for c in candidate_results):
        return GameRecommendationResult(
            recommendation_id=recommendation_id,
            fan_out_status=fan_out_result.status,
            sportsbook_used=candidate_generation.sportsbook_used,
            game_skipped_reason=candidate_generation.game_skipped_reason,
            candidates=candidate_results,
            status=ANALYSIS_INCOMPLETE,
        )

    # Pre-Phase-6 Operational Readiness Gate, Decision 5: the LAST step,
    # once every candidate has been attempted (success or isolated failure
    # -- both mean the cycle itself reached its normal end). Any exception
    # raised anywhere above this line leaves `cycle_completed_at` NULL,
    # which is exactly what keeps a crashed attempt retryable.
    #
    # No longer unconditional (HQ fix above): a cycle that produced no usable
    # analytical candidate returns before reaching this line. Completion now
    # means what it says -- a recommendation or a genuine No Bet, each after
    # analysis actually ran.
    await mark_recommendation_cycle_completed(client, headers, recommendation_id=recommendation_id, completed_at_iso=now.isoformat())

    return GameRecommendationResult(
        recommendation_id=recommendation_id,
        fan_out_status=fan_out_result.status,
        sportsbook_used=candidate_generation.sportsbook_used,
        game_skipped_reason=candidate_generation.game_skipped_reason,
        candidates=candidate_results,
    )
