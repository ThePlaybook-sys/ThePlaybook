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

from dataclasses import dataclass, field

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


@dataclass
class GameCycleResult:
    game_id: str
    correlation_id: str
    status: str  # "dispatched" | "failed"
    response: dict | None = None
    error: str | None = None


@dataclass
class WorkerCycleResult:
    status: str  # "no_eligible_run" | "completed"
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

    game_ids = await read_eligible_game_ids(supabase_client, supabase_headers)

    games: list[GameCycleResult] = []
    for game_id in game_ids:
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
            games.append(GameCycleResult(game_id=game_id, correlation_id=correlation_id, status="failed", error=str(exc)))
            continue
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

    return WorkerCycleResult(status="completed", run_id=run["id"], games=games, strategy=strategy_result, strategy_error=strategy_error)
