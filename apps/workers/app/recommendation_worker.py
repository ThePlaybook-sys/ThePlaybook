"""The Recommendation Worker's own orchestration entry point (Milestone
4.9). Owns exactly three responsibilities, and nothing else:

1. **Game eligibility.** Finds the most recently COMPLETED (`success` or
   `partial`) `master_refresh_runs` row -- `running`/`failed` are never
   eligible (`app.persistence.master_refresh_runs`) -- and every
   currently `status='scheduled'` game (`app.persistence.games`,
   mirroring `ai-orchestrator`'s own pregame-eligibility policy).
2. **Idempotent identity.** Derives a stable `correlation_id` from
   `(master_refresh_run_id, game_id)` -- `f"{run_id}:{game_id}"`. A
   retried cycle against the same run/game pair produces the exact same
   string, which `ai-orchestrator`'s `create_recommendation_cycle`
   upsert (Milestone 4.9-2, `on_conflict=correlation_id`) already
   recovers as the same `recommendations` row -- crash-safe idempotency
   lives entirely in that persistence layer; this module needs no retry
   bookkeeping of its own.
3. **Per-game dispatch and isolation.** Calls `ai-orchestrator`'s
   internal endpoint once per eligible game, via `app.
   ai_orchestrator_client.run_game_recommendation`. One game's failure
   (a real exception -- transport failure, non-2xx response) is
   isolated and recorded, never allowed to abort the rest of the slate
   -- mirrors every other per-unit isolation boundary this milestone
   already establishes (per-agent, per-candidate, per-subscriber).

**This module never duplicates AI/business logic.** Candidate
generation, the Decision & Advisory chain, consensus, and Bankroll Coach
all live entirely inside `ai-orchestrator` -- this module's only job is
to decide WHICH games are eligible this cycle and call the one endpoint
that does the real work, once per game."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.ai_orchestrator_client import AiOrchestratorCallError, finalize_slate_strategy, run_game_recommendation
from app.persistence.games import read_eligible_game_ids
from app.persistence.master_refresh_runs import read_latest_eligible_run

#: `recommendations.prompt_version`/`.agent_version` are a separate,
#: legacy/non-authoritative field (Milestone 4.8's own documented
#: framing) -- per-agent prompt provenance is resolved and persisted
#: independently inside `ai-orchestrator` via `resolve_active_prompt`.
#: These two constants exist only to satisfy that legacy column, not to
#: govern which prompts actually run.
WORKER_PROMPT_VERSION = "v1"
WORKER_AGENT_VERSION = "v1"

#: Hard ceiling on how many games one natural run may dispatch. **This is
#: a safety bound, not a scheduling policy** -- under the eligibility
#: contract in `read_eligible_game_ids` a real NFL slate inside the 7-day
#: horizon is ~16 games, so this is never reached in normal operation. It
#: exists so that a future selection defect, a bad migration, or a
#: mis-set clock cannot turn one scheduling mistake into hundreds of LLM
#: calls, the way the 2026-09-17 06:15 run turned a status-only filter
#: into 257 dispatches.
#:
#: **DERIVED, not a Blueprint number** -- the same class of decision as
#: `app.persistence.games.GRADING_CANDIDATE_LOOKBACK_DAYS`, and disclosed
#: the same way: an NFL week is at most 16 games, and a 7-day window can
#: straddle the tail of one week and the leading Thursday of the next, so
#: 20 leaves headroom for a legitimate straddle while still being an order
#: of magnitude below a full season. Overridable via
#: `RECOMMENDATION_MAX_GAMES_PER_RUN` without a deploy. **Flagged for HQ
#: confirmation** -- the mechanism is the important half; the exact
#: number is a product judgment.
DEFAULT_MAX_GAMES_PER_RUN = 20

#: How many consecutive dispatch failures carrying the SAME error end the
#: run. A deterministic misconfiguration -- an unset
#: `REFERENCE_SPORTSBOOK_PREFERENCE`, a bad internal token, a missing
#: model row -- fails identically on every game, so continuing past the
#: first few proves nothing and costs real work: on 2026-09-17 it burned
#: 257 dispatches and left 256 orphan marker rows to produce exactly one
#: fact, which the third game already knew. A transient per-game failure
#: does not repeat its message verbatim, so it does not trip this.
CONSECUTIVE_IDENTICAL_FAILURE_LIMIT = 3


#: An EXPLICIT, opt-in cap on how many eligible games one cycle actually
#: processes. Unset means no cap, which is the normal production state --
#: this exists for a staged activation, where the first live committee run
#: is deliberately held to a single game while its real cost and output
#: are observed.
#:
#: **This is not the same thing as `max_games_per_run()` and must never be
#: confused with it.** That is a SAFETY ceiling: a slate larger than it
#: means the eligibility contract is wrong, so the run refuses entirely
#: and dispatches nothing. This is a THROTTLE: the slate is correct, and
#: we are choosing to work a prefix of it on purpose.
#:
#: **It is not silent truncation.** A throttled cycle reports
#: `status="completed_limited"` rather than `"completed"`, and carries
#: `games_selected`/`games_processed`/`games_deferred`, so a partial pass
#: can never be read as a full slate. The deferred games are not failures
#: and are not marked -- they are simply untouched, and the next cycle
#: picks them up normally.
#:
#: **Ordering is not invented here.** The games arrive already sorted by
#: `scheduled_start` ascending (`read_eligible_game_ids`), which is
#: Volume 5's own "Neutral ordering (HQ Final Decision 1): game-scoped
#: cards order by `games.scheduled_start` ... Never EV or confidence."
#: Taking a prefix therefore means "the games kicking off soonest", which
#: is the architecture's existing rule rather than a new ranking.
MAX_GAMES_PER_CYCLE_ENV = "RECOMMENDATION_MAX_GAMES_PER_CYCLE"


def max_games_per_cycle() -> int | None:
    """`RECOMMENDATION_MAX_GAMES_PER_CYCLE` as a positive integer, or
    `None` when unset/blank (no throttle -- the normal state).

    A malformed or non-positive value returns `None` rather than raising:
    a typo in a throttle must not silently reduce the slate to something
    unintended, and no-throttle is the documented default. The safety
    ceiling still applies either way."""
    raw = os.environ.get(MAX_GAMES_PER_CYCLE_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def max_games_per_run() -> int:
    """`RECOMMENDATION_MAX_GAMES_PER_RUN` when set to a positive integer,
    otherwise `DEFAULT_MAX_GAMES_PER_RUN`. A malformed or non-positive
    value falls back to the default rather than raising -- this is a
    safety ceiling, and a typo in it must not itself become an outage."""
    raw = os.environ.get("RECOMMENDATION_MAX_GAMES_PER_RUN", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_GAMES_PER_RUN
    return value if value > 0 else DEFAULT_MAX_GAMES_PER_RUN


@dataclass
class GameCycleResult:
    game_id: str
    correlation_id: str
    status: str  # "dispatched" | "failed"
    response: dict | None = None
    error: str | None = None


@dataclass
class WorkerCycleResult:
    #: "no_eligible_run" | "completed" | "completed_limited" | "failed"
    #:
    #: `"failed"` is the FAIL-CLOSED outcome: the run refused to dispatch
    #: anything (the slate exceeded `max_games_per_run`) or stopped
    #: dispatching partway (`CONSECUTIVE_IDENTICAL_FAILURE_LIMIT`). It is
    #: deliberately the one status `cron_dispatch` already reports to
    #: Sentry at `error` level, so a bound being hit is never silent and
    #: is never dressed up as a complete run.
    status: str
    run_id: str | None
    games: list[GameCycleResult] = field(default_factory=list)
    #: Milestone 5.1 -- the Strategy Engine's slate-level finalization
    #: result. `None` when `status != "completed"`, or when the
    #: finalize-strategy call itself failed (see `strategy_error`) --
    #: every per-game dispatch above still succeeded/failed on its own
    #: terms regardless; this field is reported separately, never allowed
    #: to retroactively mark a game's own dispatch as failed.
    strategy: dict | None = None
    strategy_error: str | None = None
    #: Set only when `status="failed"`. Names which bound stopped the run
    #: and what it saw, so the Sentry event is actionable without needing
    #: the log.
    error: str | None = None
    #: How many games the eligibility contract selected, BEFORE any bound
    #: was applied. Reported even on a fail-closed run -- the whole point
    #: of the ceiling is that the number which tripped it is visible.
    games_selected: int = 0
    #: Games never attempted because the run stopped early. Non-zero means
    #: this run is explicitly INCOMPLETE; it is never presented as a full
    #: slate.
    games_not_attempted: int = 0
    #: Eligible games deliberately held back by the activation throttle
    #: (`RECOMMENDATION_MAX_GAMES_PER_CYCLE`). These are NOT failures and
    #: are NOT marked -- they are untouched, and the next cycle takes them
    #: normally. Reported separately from `games_not_attempted`'s
    #: stopped-early meaning so "we chose to defer" never reads as
    #: "something went wrong".
    games_deferred: int = 0


def _failure_signature(error: str, *, game_id: str) -> str:
    """The comparable shape of a dispatch failure, with this game's own id
    removed. `AiOrchestratorCallError` embeds `game_id=...` in its
    message, so two games hitting the identical deterministic fault
    produce two different strings; stripping the id is what lets the
    consecutive-failure breaker recognise one fault repeating rather than
    a series of unrelated ones."""
    return error.replace(game_id, "<game_id>")


def build_correlation_id(*, run_id: str, game_id: str) -> str:
    """The stable `(master_refresh_run_id, game_id)` identity every
    retry of the same run/game pair reproduces exactly -- never
    randomly generated, never including any wall-clock component."""
    return f"{run_id}:{game_id}"


async def run_recommendation_worker_cycle(
    supabase_client: httpx.AsyncClient,
    supabase_headers: dict,
    *,
    ai_orchestrator_client: httpx.AsyncClient,
    ai_orchestrator_base_url: str,
    internal_token: str,
    prompt_version: str = WORKER_PROMPT_VERSION,
    agent_version: str = WORKER_AGENT_VERSION,
    now: datetime | None = None,
) -> WorkerCycleResult:
    """Runs one full Recommendation Worker cycle. Returns `status=
    "no_eligible_run"` (empty `games`) when no Master Refresh run has
    completed yet -- never fabricates a run to proceed against.
    Otherwise dispatches one call per eligible game, isolating each
    game's own failure into its own `GameCycleResult` rather than
    raising."""
    run = await read_latest_eligible_run(supabase_client, supabase_headers)
    if run is None:
        return WorkerCycleResult(status="no_eligible_run", run_id=None, games=[])

    game_ids = await read_eligible_game_ids(supabase_client, supabase_headers, now=now or datetime.now(timezone.utc))
    selected = len(game_ids)

    # FAIL CLOSED, before a single dispatch. A slate larger than the
    # ceiling is not truncated and run anyway -- silent truncation would
    # report a "complete" cycle that quietly skipped games, which is the
    # failure mode this bound exists to prevent, not a milder version of
    # it. Nothing is dispatched, nothing is marked, and the status is the
    # one Sentry reports.
    ceiling = max_games_per_run()
    if selected > ceiling:
        return WorkerCycleResult(
            status="failed",
            run_id=run["id"],
            games=[],
            games_selected=selected,
            games_not_attempted=selected,
            error=(
                f"eligible slate of {selected} games exceeds the run ceiling of {ceiling} "
                f"(RECOMMENDATION_MAX_GAMES_PER_RUN) -- refusing to dispatch. A slate this "
                f"large means the eligibility contract is wrong, not that the week is busy."
            ),
        )

    # The explicit activation throttle, applied AFTER the safety ceiling
    # and never conflated with it. The slate is already ordered by
    # `scheduled_start` ascending, so a prefix is "soonest kickoff first"
    # per Volume 5's HQ Final Decision 1 -- not a new ranking rule.
    cycle_cap = max_games_per_cycle()
    deferred = 0
    if cycle_cap is not None and selected > cycle_cap:
        deferred = selected - cycle_cap
        game_ids = game_ids[:cycle_cap]

    games: list[GameCycleResult] = []
    consecutive_identical: int = 0
    last_error: str | None = None
    halt_error: str | None = None
    for index, game_id in enumerate(game_ids):
        correlation_id = build_correlation_id(run_id=run["id"], game_id=game_id)
        try:
            response = await run_game_recommendation(
                ai_orchestrator_client,
                base_url=ai_orchestrator_base_url,
                internal_token=internal_token,
                game_id=game_id,
                correlation_id=correlation_id,
                prompt_version=prompt_version,
                agent_version=agent_version,
            )
        except AiOrchestratorCallError as exc:
            error = str(exc)
            games.append(GameCycleResult(game_id=game_id, correlation_id=correlation_id, status="failed", error=error))
            # A deterministic misconfiguration fails identically on every
            # game. `_failure_signature` strips the per-game id so that
            # "the same fault" is recognised across different games --
            # without it, every message differs by its game_id and the
            # breaker never trips on exactly the case it is for.
            signature = _failure_signature(error, game_id=game_id)
            consecutive_identical = consecutive_identical + 1 if signature == last_error else 1
            last_error = signature
            if consecutive_identical >= CONSECUTIVE_IDENTICAL_FAILURE_LIMIT:
                halt_error = (
                    f"halted after {consecutive_identical} consecutive identical failures "
                    f"({consecutive_identical}/{selected} games attempted): {error}. "
                    f"This is a deterministic fault, not a per-game one -- continuing would "
                    f"repeat it on every remaining game and create one orphan marker row each."
                )
                return WorkerCycleResult(
                    status="failed",
                    run_id=run["id"],
                    games=games,
                    games_selected=selected,
                    games_not_attempted=selected - (index + 1),
                    games_deferred=deferred,
                    error=halt_error,
                )
            continue
        consecutive_identical = 0
        last_error = None
        games.append(GameCycleResult(game_id=game_id, correlation_id=correlation_id, status="dispatched", response=response))

    # Milestone 5.1: finalize the Strategy Engine's slate-level decision
    # exactly once, after every eligible game's dispatch above has
    # completed -- relaying each dispatched game's already-computed
    # strategy_input fields unmodified (see app.ai_orchestrator_client.
    # finalize_slate_strategy's own docstring). A game that failed to
    # dispatch is OMITTED here, never represented as no_bet -- it was
    # never evaluated at all, which is a different fact from "evaluated,
    # nothing qualified."
    #
    # Pre-Phase-6 Operational Readiness Gate, Decision 5: a game whose
    # ai-orchestrator response came back `status="skipped_already_computed"`
    # is ALSO omitted here, for the same reason -- it contributed no NEW
    # candidates THIS cycle (its own strategy_input was already relayed
    # in the earlier cycle that actually computed it). `finalize_slate_
    # strategy` has no idempotency of its own for a repeated
    # master_refresh_run_id (a real, separate, pre-existing gap this
    # readiness gate did not attempt to close -- see the completion
    # report) -- omitting already-computed games here is what keeps a
    # repeated cron fire against a fully-completed run from calling it
    # again at all (see the `if strategy_games:` guard below).
    strategy_games = [
        {
            "game_id": g.game_id,
            "recommendation_id": g.response["recommendation_id"],
            "candidates": [c["strategy_input"] for c in g.response["candidates"] if c.get("strategy_input")],
        }
        for g in games
        if g.status == "dispatched" and g.response.get("status") != "skipped_already_computed"
    ]

    strategy_result: dict | None = None
    strategy_error: str | None = None
    if strategy_games:
        try:
            strategy_result = await finalize_slate_strategy(
                ai_orchestrator_client,
                base_url=ai_orchestrator_base_url,
                internal_token=internal_token,
                master_refresh_run_id=run["id"],
                games=strategy_games,
            )
        except AiOrchestratorCallError as exc:
            strategy_error = str(exc)

    return WorkerCycleResult(
        # `completed_limited`, never plain `completed`, when the throttle
        # held games back -- a partial pass must not be readable as a
        # full slate.
        status="completed_limited" if deferred else "completed",
        run_id=run["id"],
        games=games,
        strategy=strategy_result,
        strategy_error=strategy_error,
        games_selected=selected,
        games_not_attempted=deferred,
        games_deferred=deferred,
    )
