import logging
import os

import sentry_sdk
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.environment_safety import assert_demo_isolation
from app.internal_auth import require_internal_token
from app.master_refresh.production_clients import (
    MissingCredentialError,
    build_real_master_refresh_clients,
    build_real_odds_worker_clients,
)
from app.master_refresh.run import run_master_refresh
from app.persistence.odds_snapshots import read_last_polled_at
from app.workers.odds_worker import run_odds_worker

_logger = logging.getLogger("sports-intel-layer.main")

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


# TEMPORARY — Phase 7 Milestone 7.0B Gate B, HQ-authorized real-event discovery
# probe, corrected retry (2026-09-02). Same shape/intent as the first attempt
# (commit 065f864, reverted in 89ebc6a): a dev-only, environment-gated startup
# check that makes exactly one real call using the EXISTING, unmodified
# TheOddsApiOddsAdapter/build_real_odds_worker_clients (never duplicates or
# bypasses either), logging only non-secret event metadata (provider event
# id/home/away/kickoff/bookmaker+market names) to this service's own deploy
# logs. Only correction from the first attempt: every log line here uses
# logger.warning(), not logger.info() -- this service configures no logging
# level anywhere (confirmed: no basicConfig/dictConfig in app or Dockerfile),
# so the first attempt's INFO-level lines were silently dropped by Python's
# default root logger level (WARNING). Never raises -- a failure here must
# never block the real server from starting. To be reverted in this same
# session once the discovery result has been read from Railway's deploy
# logs; this must never remain in the codebase past Gate B's real-event
# discovery step.
if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.on_event("startup")
    async def _gate_b_real_event_discovery_probe() -> None:
        from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter

        try:
            _, the_odds_api_client, the_odds_api_key = build_real_odds_worker_clients()
        except MissingCredentialError as exc:
            _logger.warning("GATE_B_DISCOVERY_PROBE: skipped, credential not configured (%s)", exc)
            return

        try:
            async with the_odds_api_client:
                adapter = TheOddsApiOddsAdapter(client=the_odds_api_client, api_key=the_odds_api_key)
                response = await adapter.fetch_odds([])
        except Exception as exc:  # never block real startup on a diagnostic failure
            _logger.warning("GATE_B_DISCOVERY_PROBE: failed: %s", exc)
            return

        events: dict[str, dict] = {}
        for line in response.value:
            entry = events.setdefault(
                line.game_external_id,
                {
                    "home_team": line.home_team,
                    "away_team": line.away_team,
                    "commence_time": line.commence_time.isoformat() if line.commence_time else None,
                    "sportsbooks": set(),
                    "market_types": set(),
                },
            )
            entry["sportsbooks"].add(line.sportsbook)
            entry["market_types"].add(line.market_type)

        for event_id, entry in events.items():
            _logger.warning(
                "GATE_B_DISCOVERY_PROBE: event_id=%s home=%r away=%r commence_time=%s "
                "sportsbooks=%s market_types=%s",
                event_id,
                entry["home_team"],
                entry["away_team"],
                entry["commence_time"],
                sorted(entry["sportsbooks"]),
                sorted(entry["market_types"]),
            )
        _logger.warning("GATE_B_DISCOVERY_PROBE: total_events=%d", len(events))


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


class RunOddsWorkerResponse(BaseModel):
    status: str
    games_considered: int
    games_due: int
    games_skipped_not_due: int
    lines_persisted: int
    newly_linked: int
    unresolved_events: list[str]
    failures: list[str]
    error: str | None


@app.post(
    "/v1/internal/odds-worker/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunOddsWorkerResponse,
)
async def internal_run_odds_worker() -> RunOddsWorkerResponse:
    """Phase 7 Milestone 7.0B, Gate A: the Odds Worker runtime invocation
    path this project never had before this endpoint (Milestone 7.0A's
    STOP report -- `run_odds_worker`'s only two callers were Demo Mode's
    isolated scenario rig and the equally-unreachable Pregame Worker; no
    HTTP route, no cron-dispatch target, existed anywhere). Reuses the
    EXISTING `run_odds_worker` (`app.workers.odds_worker`) unchanged --
    this is a thin HTTP-to-function adapter only, same shape as
    `internal_run_master_refresh` above, never a second implementation.

    **Safe missing-credential failure (HQ's explicit requirement):**
    `build_real_odds_worker_clients()` raises `MissingCredentialError`
    -- not a raw `KeyError` -- before any Supabase or provider network
    call is attempted if the odds-provider credential isn't configured.
    Caught here and returned as a clean, structured `status="failed"`
    result with an operational error message; the credential's own name
    and value are never referenced anywhere in this module (DEMO-1's
    isolation guard, `tests/test_environment_safety.py`, forbids it by
    name here exactly as it already does for every other provider
    credential above), matching the identical pattern already
    established for Master Refresh's own credential above.

    **Cadence realism (Milestone 7.0B, §1/§5 construction-contract audit):**
    `run_odds_worker`'s own `last_polled_at` parameter defaults to `None`
    per game, which its own docstring documents as "treat every due game
    as never-polled" -- always safe for a single call, but it would make
    `app.workers.windows`'s adaptive cadence meaningless for a stateless
    HTTP-triggered caller like this one, since every invocation would see
    every non-kicked-off candidate game as due regardless of how recently
    it was actually fetched. `read_last_polled_at()` derives real
    per-game state from already-persisted `odds_snapshots.captured_at`
    history instead of adding new state storage -- so the existing,
    already-correct adaptive cadence in `app.workers.windows` actually
    governs real fetch frequency, and repeated invocation (e.g. from a
    5-minute cron) makes at most one real provider request when at least
    one game is genuinely due, zero otherwise (`run_odds_worker`'s own
    `if not due_games: return` check, confirmed unchanged by direct
    reading -- this endpoint never bypasses it).

    **Concurrency:** Railway's own cron platform guarantees a running
    cron job's next tick is skipped, never stacked, if the previous run
    is still active (confirmed via Railway's own documentation) -- the
    primary protection for the one real caller this milestone wires
    (`cron-odds-worker`). No additional application-level lock is added
    here: `odds_snapshots`' append-only INSERT semantics make a rare
    genuine overlap (e.g. a manual out-of-schedule call racing a
    scheduled one) produce a harmless duplicate observation, not a data
    integrity issue, and this project's other cron-dispatched workers
    rely on the identical no-extra-lock convention.

    Reachable only via `INTERNAL_SERVICE_TOKEN`, identical to every other
    internal endpoint in this project. No recommendation, ranking, or
    anomaly-classification logic of any kind."""
    try:
        supabase_client, the_odds_api_client, the_odds_api_key = build_real_odds_worker_clients()
    except MissingCredentialError as exc:
        return RunOddsWorkerResponse(
            status="failed",
            games_considered=0,
            games_due=0,
            games_skipped_not_due=0,
            lines_persisted=0,
            newly_linked=0,
            unresolved_events=[],
            failures=[],
            error=str(exc),
        )

    async with supabase_client, the_odds_api_client:
        last_polled_at = await read_last_polled_at()
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=the_odds_api_client,
            the_odds_api_key=the_odds_api_key,
            last_polled_at=last_polled_at,
        )

    return RunOddsWorkerResponse(
        status=result.status,
        games_considered=result.games_considered,
        games_due=result.games_due,
        games_skipped_not_due=result.games_skipped_not_due,
        lines_persisted=result.lines_persisted,
        newly_linked=result.newly_linked,
        unresolved_events=result.unresolved_events,
        failures=result.failures,
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
