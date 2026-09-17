import os

import httpx
import sentry_sdk
from fastapi import Depends, FastAPI

from pydantic import BaseModel

from app import supabase_client
from app.adaptive_weighting_worker import run_adaptive_weighting_worker_cycle
from app.internal_auth import require_internal_token
from app.postgame_grading_worker import run_postgame_grading_worker_cycle
from app.recommendation_worker import run_recommendation_worker_cycle

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # No privacy policy live yet (Volume 1 §10) to disclose PII collection —
    # revisit once one is in place.
    send_default_pii=False,
    # Without this, the SDK defaults every event to "production" regardless
    # of which Railway environment it actually came from.
    environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
)

app = FastAPI(title="The Playbook — Background Workers")


def _ai_orchestrator_base_url() -> str:
    """The base URL every internal call to `ai-orchestrator` is built
    from, read from this service's own `AI_ORCHESTRATOR_URL` -- the same
    name `api-gateway` already uses (`app.internal_client`).

    This used to read Railway's `RAILWAY_SERVICE_AI_ORCHESTRATOR_URL`,
    and that was a real, live defect (2026-09-16). Railway auto-injects a
    variable of that exact name onto every service in the project, and
    its value is a bare public domain with **no scheme**, which httpx
    rejects with "Request URL is missing an 'http://' or 'https://'
    protocol." The variable was never deliberately configured here --
    PROGRESS.md records it as a known-missing, flagged-for-decision item
    since Phase 4 -- but `os.environ[...]` never raised `KeyError`,
    because Railway's own injection silently satisfied the lookup. So a
    URL the project believed was absent was present and wrong, and
    postgame grading failed once every thirty minutes inside a 200 OK for
    hours before cron Sentry instrumentation surfaced it.

    Setting an explicit service variable of that same name does NOT fix
    it: Railway's injection still wins (verified live on dev, the tick
    after failed identically). An application-owned name is therefore the
    only correct fix -- and it restores the property that matters, that a
    genuinely unset URL fails loudly here rather than quietly at the
    transport layer."""
    return os.environ["AI_ORCHESTRATOR_URL"]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "workers"}


class GameCycleResponseItem(BaseModel):
    game_id: str
    correlation_id: str
    status: str
    error: str | None


class RunRecommendationCycleResponse(BaseModel):
    status: str
    run_id: str | None
    games: list[GameCycleResponseItem]
    strategy: dict | None = None
    strategy_error: str | None = None


@app.post(
    "/v1/internal/recommendation-worker/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunRecommendationCycleResponse,
)
async def internal_run_recommendation_cycle() -> RunRecommendationCycleResponse:
    """Milestone 4.9's Recommendation Worker trigger. Something external
    to this application (a Railway Cron Job, or an external scheduler --
    a deliberate, explicitly-flagged open item; see this milestone's
    completion report) calls this on a schedule shortly after each
    Master Refresh; this endpoint itself never self-schedules, mirroring
    `ai-orchestrator`'s own internal endpoint (which never self-schedules
    either). Reachable only via `INTERNAL_SERVICE_TOKEN`."""
    ai_orchestrator_base_url = _ai_orchestrator_base_url()
    internal_token = os.environ["INTERNAL_SERVICE_TOKEN"]

    headers = supabase_client.auth_headers()
    async with supabase_client.new_client() as db_client, httpx.AsyncClient(timeout=120.0) as orchestrator_client:
        result = await run_recommendation_worker_cycle(
            db_client,
            headers,
            ai_orchestrator_client=orchestrator_client,
            ai_orchestrator_base_url=ai_orchestrator_base_url,
            internal_token=internal_token,
        )

    return RunRecommendationCycleResponse(
        status=result.status,
        run_id=result.run_id,
        games=[
            GameCycleResponseItem(game_id=g.game_id, correlation_id=g.correlation_id, status=g.status, error=g.error)
            for g in result.games
        ],
        strategy=result.strategy,
        strategy_error=result.strategy_error,
    )


class RunPostgameGradingCycleResponse(BaseModel):
    status: str
    game_ids: list[str]
    response: dict | None = None
    error: str | None = None


@app.post(
    "/v1/internal/postgame-grading/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunPostgameGradingCycleResponse,
)
async def internal_run_postgame_grading_cycle() -> RunPostgameGradingCycleResponse:
    """Milestone 5.4's Postgame Grading Worker trigger. Something
    external to this application (a Railway Cron Job, or an external
    scheduler -- the same deliberate, explicitly-flagged open item as
    the Recommendation Worker's own trigger, Milestone 4.9) calls this on
    a schedule; this endpoint itself never self-schedules. Reachable
    only via `INTERNAL_SERVICE_TOKEN`."""
    ai_orchestrator_base_url = _ai_orchestrator_base_url()
    internal_token = os.environ["INTERNAL_SERVICE_TOKEN"]

    headers = supabase_client.auth_headers()
    async with supabase_client.new_client() as db_client, httpx.AsyncClient(timeout=120.0) as orchestrator_client:
        result = await run_postgame_grading_worker_cycle(
            db_client,
            headers,
            ai_orchestrator_client=orchestrator_client,
            ai_orchestrator_base_url=ai_orchestrator_base_url,
            internal_token=internal_token,
        )

    return RunPostgameGradingCycleResponse(status=result.status, game_ids=result.game_ids, response=result.response, error=result.error)


class RunAdaptiveWeightingCycleResponse(BaseModel):
    status: str
    response: dict | None = None
    error: str | None = None


@app.post(
    "/v1/internal/adaptive-weighting/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunAdaptiveWeightingCycleResponse,
)
async def internal_run_adaptive_weighting_cycle() -> RunAdaptiveWeightingCycleResponse:
    """Milestone 5.5's Adaptive Weighting Worker trigger. An external
    scheduler (Railway Cron Job, or equivalent -- unconfigured, same
    disclosed open item as the Recommendation Worker's and Postgame
    Grading Worker's own triggers) calls this on a schedule; this
    endpoint never self-schedules. Reachable only via
    `INTERNAL_SERVICE_TOKEN`."""
    ai_orchestrator_base_url = _ai_orchestrator_base_url()
    internal_token = os.environ["INTERNAL_SERVICE_TOKEN"]

    async with httpx.AsyncClient(timeout=120.0) as orchestrator_client:
        result = await run_adaptive_weighting_worker_cycle(
            ai_orchestrator_client=orchestrator_client, ai_orchestrator_base_url=ai_orchestrator_base_url, internal_token=internal_token
        )

    return RunAdaptiveWeightingCycleResponse(status=result.status, response=result.response, error=result.error)


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
