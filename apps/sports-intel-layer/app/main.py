import os

import sentry_sdk
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.environment_safety import assert_demo_isolation
from app.internal_auth import require_internal_token
from app.master_refresh.production_clients import build_real_master_refresh_clients
from app.master_refresh.run import run_master_refresh

# DEMO-1 (2026-08-19): hard-fail startup before anything else runs if a demo deployment's
# environment tag and database target disagree. Deliberately checked before sentry_sdk.init
# and app construction -- a demo isolation violation must prevent the process from ever
# reaching a state where it could serve a request or emit telemetry.
assert_demo_isolation(
    railway_environment_name=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
    supabase_url=os.environ.get("SUPABASE_URL", ""),
)

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # No privacy policy live yet (Volume 1 §10) to disclose PII collection —
    # revisit once one is in place.
    send_default_pii=False,
    # Without this, the SDK defaults every event to "production" regardless
    # of which Railway environment it actually came from.
    environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
)

app = FastAPI(title="The Playbook — Sports Intelligence Layer")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "sports-intel-layer"}


class RunMasterRefreshResponse(BaseModel):
    status: str
    run_id: str | None
    season_string: str | None
    games_in_slate: int
    games_created: int
    games_updated: int
    roster_failures: list[str]
    roster_ingestion_failures: list[str]
    player_id_resolution_failed: bool
    daily_game_intelligence_written: int
    daily_game_intelligence_failures: list[str]
    error: str | None


@app.post(
    "/v1/internal/master-refresh/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunMasterRefreshResponse,
)
async def internal_run_master_refresh() -> RunMasterRefreshResponse:
    """Pre-Phase-6 Operational Readiness Gate, Decision 6: the Master
    Refresh runtime invocation path this project never had before this
    endpoint (Finding 1 of the STOP report preceding this gate --
    `sports-intel-layer` exposed no route beyond `/health`/`/sentry-debug`
    that could ever run `run_master_refresh`). Constructs the real
    `SportsDataIOScheduleAdapter`/`SportsDataIORosterAdapter` via
    `run_master_refresh`'s own default (no injected fixture adapter) --
    every call to this endpoint makes a real, spendable SportsDataIO
    Schedule call. Nothing calls this automatically yet in DEV without a
    human or the cron dispatcher explicitly doing so (see `apps/workers/
    app/cron_dispatch.py`'s `master-refresh` target) -- this readiness
    gate's own Decision 5 explicitly forbids spending the project's last
    reserved SportsDataIO call merely to exercise this endpoint, so it is
    wired but deliberately left unexercised against the live provider.
    Reachable only via `INTERNAL_SERVICE_TOKEN`, identical to every other
    internal endpoint in this project. Never duplicates `run_master_refresh`'s
    own logic -- this is a thin HTTP-to-function adapter only. Real
    credential/client construction lives in `app.master_refresh.
    production_clients` (not here) -- see that module's own docstring for
    why: DEMO-1's isolation guard forbids `app.main`'s own source from
    ever naming a provider/service-role credential directly."""
    supabase_client, sportsdataio_client, sportsdataio_api_key = build_real_master_refresh_clients()
    async with supabase_client, sportsdataio_client:
        result = await run_master_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sportsdataio_client,
            sportsdataio_api_key=sportsdataio_api_key,
        )

    return RunMasterRefreshResponse(
        status=result.status,
        run_id=result.run_id,
        season_string=result.season_string,
        games_in_slate=result.games_in_slate,
        games_created=result.games_created,
        games_updated=result.games_updated,
        roster_failures=result.roster_failures,
        roster_ingestion_failures=result.roster_ingestion_failures,
        player_id_resolution_failed=result.player_id_resolution_failed,
        daily_game_intelligence_written=result.daily_game_intelligence_written,
        daily_game_intelligence_failures=result.daily_game_intelligence_failures,
        error=result.error,
    )


# DEMO-4, Decision 4: mounted only in the demo environment -- defense in depth,
# matching the existing dev-only /sentry-debug conditional-mount convention below.
# Every route inside this router independently re-verifies isolation on every
# request regardless (app.demo.router's own docstring); this mount-time check is
# deliberately not relied on as the only guard.
if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "demo":
    from app.demo.router import router as demo_router

    app.include_router(demo_router)


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
