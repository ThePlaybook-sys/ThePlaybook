import os

import httpx
import sentry_sdk
from fastapi import Depends, FastAPI

from pydantic import BaseModel

from app import supabase_client
from app.internal_auth import require_internal_token
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
    ai_orchestrator_base_url = os.environ["RAILWAY_SERVICE_AI_ORCHESTRATOR_URL"]
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
    )


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
