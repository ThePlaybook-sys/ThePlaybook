"""The Postgame Grading Worker's own orchestration entry point (Milestone
5.4). Mirrors `app.recommendation_worker`'s own split exactly (see that
module's docstring): this service discovers candidate `game_ids` from its
own read of `games`, then makes exactly one call to `ai-orchestrator`'s
internal endpoint, which owns every grading decision (reconciliation-
eligibility, deterministic outcomes, product rollups, narrative
generation). This module never duplicates any of that logic -- per Mac's
explicit "no duplicated AI/business logic in workers" instruction, carried
forward unchanged from Milestone 4.9."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.ai_orchestrator_client import AiOrchestratorCallError, run_postgame_grading
from app.persistence.games import read_grading_candidate_game_ids


@dataclass
class PostgameGradingWorkerResult:
    status: str  # "no_candidates" | "completed" | "failed"
    game_ids: list[str]
    response: dict | None = None
    error: str | None = None


async def run_postgame_grading_worker_cycle(
    supabase_client: httpx.AsyncClient,
    supabase_headers: dict,
    *,
    ai_orchestrator_client: httpx.AsyncClient,
    ai_orchestrator_base_url: str,
    internal_token: str,
    now: datetime | None = None,
) -> PostgameGradingWorkerResult:
    """Runs one full Postgame Grading Worker cycle. `status=
    "no_candidates"` (never calls `ai-orchestrator` at all) when no game
    is even a coarse candidate this cycle -- never an empty-but-still-
    dispatched call. A transport/non-2xx failure from `ai-orchestrator`
    is reported as `status="failed"`, never raised -- this is a
    finite-job worker, same convention as every other worker cycle in
    this codebase."""
    now = now or datetime.now(timezone.utc)
    game_ids = await read_grading_candidate_game_ids(supabase_client, supabase_headers, now=now)
    if not game_ids:
        return PostgameGradingWorkerResult(status="no_candidates", game_ids=[])

    try:
        response = await run_postgame_grading(
            ai_orchestrator_client, base_url=ai_orchestrator_base_url, internal_token=internal_token, game_ids=game_ids
        )
    except AiOrchestratorCallError as exc:
        return PostgameGradingWorkerResult(status="failed", game_ids=game_ids, error=str(exc))

    return PostgameGradingWorkerResult(status="completed", game_ids=game_ids, response=response)
