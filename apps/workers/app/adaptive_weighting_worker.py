"""The Adaptive Weighting Worker's own orchestration entry point
(Milestone 5.5). Unlike `app.recommendation_worker`/`app.postgame_grading_worker`,
this service has NOTHING to discover -- the evaluation window is purely a
function of wall-clock time, not of which games/products currently exist
-- so this module is a thin, single-call wrapper, not a discovery-then-
dispatch loop. `ai-orchestrator` owns every evidence read, guardrail
check, and PROPOSE-ONLY persistence decision (Decision 21 -- no
duplicated AI/business logic in this service, the same boundary already
established for the Recommendation Worker and the Postgame Grading
Worker)."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.ai_orchestrator_client import AiOrchestratorCallError, run_adaptive_weighting

#: Decision 8 -- the Blueprint's own rolling 90-day minimum. A caller may
#: widen this later; `ai-orchestrator`'s own endpoint rejects anything
#: narrower regardless (defense in depth, never relied on solely here).
EVALUATION_WINDOW_DAYS = 90


@dataclass
class AdaptiveWeightingWorkerResult:
    status: str  # "completed" | "failed"
    response: dict | None = None
    error: str | None = None


async def run_adaptive_weighting_worker_cycle(
    *, ai_orchestrator_client: httpx.AsyncClient, ai_orchestrator_base_url: str, internal_token: str
) -> AdaptiveWeightingWorkerResult:
    """Runs one Adaptive Weighting Worker cycle -- a single call to
    `ai-orchestrator`'s internal endpoint. Never raises -- a transport/
    non-2xx failure is reported as `status="failed"`, the same finite-job
    convention every other worker cycle in this codebase follows."""
    try:
        response = await run_adaptive_weighting(
            ai_orchestrator_client,
            base_url=ai_orchestrator_base_url,
            internal_token=internal_token,
            evaluation_window_days=EVALUATION_WINDOW_DAYS,
        )
    except AiOrchestratorCallError as exc:
        return AdaptiveWeightingWorkerResult(status="failed", error=str(exc))
    return AdaptiveWeightingWorkerResult(status="completed", response=response)
