import os

import sentry_sdk
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.environment_safety import assert_demo_isolation
from app.internal_auth import require_internal_token
from app.master_refresh.production_clients import (
    MissingCredentialError,
    build_real_balldontlie_injury_worker_clients,
    build_real_master_refresh_clients,
    build_real_news_worker_clients,
    build_real_odds_worker_clients,
    build_real_weather_worker_clients,
)
from app.master_refresh.run import run_master_refresh
from app.persistence.odds_snapshots import read_last_polled_at
from app.persistence.weather_snapshots import read_last_polled_at as read_weather_last_polled_at
from app.adapters.providers.gnews import GNewsNewsAdapter
from app.workers.balldontlie_injury_worker import run_balldontlie_injury_worker
from app.workers.news_worker import run_news_worker
from app.workers.odds_worker import run_odds_worker
from app.workers.weather_worker import run_weather_worker

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


class RunBallDontLieInjuryWorkerResponse(BaseModel):
    status: str
    games_considered: int
    games_linked: int
    teams_resolved: int
    reports_fetched: int
    reports_persisted: int
    failures: list[str]
    error: str | None


@app.post(
    "/v1/internal/balldontlie-injury-worker/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunBallDontLieInjuryWorkerResponse,
)
async def internal_run_balldontlie_injury_worker() -> RunBallDontLieInjuryWorkerResponse:
    """Phase 8.0.5 Data Activation Pass 1 (2026-09-07): the BALLDONTLIE
    Injury Worker's runtime invocation path, same minimal shape as
    `internal_run_odds_worker` above -- a thin HTTP-to-function adapter
    only, never a second implementation of `run_balldontlie_injury_worker`
    (`app.workers.balldontlie_injury_worker`).

    **Does not touch the reserved SportsDataIO trial call, by
    construction, not just by convention** -- this endpoint never
    constructs `build_real_master_refresh_clients`/`SportsDataIOInjuryAdapter`;
    it exclusively uses `build_real_balldontlie_injury_worker_clients`,
    a completely separate credential/provider path from SportsDataIO's
    own untouched `injury_worker.py`.

    Same safe missing-credential failure as every other internal endpoint:
    `MissingCredentialError` -- never a raw `KeyError` -- returns a clean
    `status="failed"` result. Reachable only via `INTERNAL_SERVICE_TOKEN`."""
    try:
        supabase_client, balldontlie_client, balldontlie_api_key = build_real_balldontlie_injury_worker_clients()
    except MissingCredentialError as exc:
        return RunBallDontLieInjuryWorkerResponse(
            status="failed",
            games_considered=0,
            games_linked=0,
            teams_resolved=0,
            reports_fetched=0,
            reports_persisted=0,
            failures=[],
            error=str(exc),
        )

    async with supabase_client, balldontlie_client:
        result = await run_balldontlie_injury_worker(
            supabase_client=supabase_client,
            balldontlie_client=balldontlie_client,
            balldontlie_api_key=balldontlie_api_key,
        )

    return RunBallDontLieInjuryWorkerResponse(
        status=result.status,
        games_considered=result.games_considered,
        games_linked=result.games_linked,
        teams_resolved=result.teams_resolved,
        reports_fetched=result.reports_fetched,
        reports_persisted=result.reports_persisted,
        failures=result.failures,
        error=result.error,
    )


class RunNewsWorkerResponse(BaseModel):
    status: str
    games_considered: int
    teams_considered: int
    teams_due: int
    teams_skipped_not_due: int
    teams_unresolved: list[str]
    teams_fetched: int
    articles_dropped_unresolved: int
    games_updated: int
    games_skipped_no_data: int
    history_rows_written: int
    teams_skipped_quota_guard: int
    provider_requests_used_today: int | None
    failures: list[str]
    error: str | None


@app.post(
    "/v1/internal/news-worker/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunNewsWorkerResponse,
)
async def internal_run_news_worker() -> RunNewsWorkerResponse:
    """Phase 8.0.5 Data Activation Pass 1 (2026-09-07): News Worker's
    runtime invocation path, same minimal shape as `internal_run_odds_worker`
    above. Reuses the EXISTING `run_news_worker` (`app.workers.news_worker`)
    completely unchanged.

    **Uses GNews, not NewsAPI, for this specific call site only --
    HQ's explicit instruction, not a change to `news_worker.py`'s own
    default.** `run_news_worker`'s own hardcoded default
    (`NewsAPINewsAdapter`, whose own credential is confirmed absent
    from this environment) is left completely untouched; this endpoint
    instead explicitly constructs and injects `GNewsNewsAdapter` via
    `run_news_worker`'s own pre-existing `news_adapter` dependency-
    injection seam -- the same seam every worker test in this project
    already uses to swap adapters, not a new mechanism. Volume 2 §8's
    NewsAPI-vs-GNews vendor decision remains exactly as undecided as it
    was before this endpoint existed.

    Same safe missing-credential failure as every other internal endpoint:
    `MissingCredentialError` (credential unset) -- never a raw
    `KeyError` -- returns a clean `status="failed"` result. Reachable
    only via `INTERNAL_SERVICE_TOKEN`."""
    try:
        supabase_client, gnews_client, gnews_api_key = build_real_news_worker_clients()
    except MissingCredentialError as exc:
        return RunNewsWorkerResponse(
            status="failed",
            games_considered=0,
            teams_considered=0,
            teams_due=0,
            teams_skipped_not_due=0,
            teams_unresolved=[],
            teams_fetched=0,
            articles_dropped_unresolved=0,
            games_updated=0,
            games_skipped_no_data=0,
            history_rows_written=0,
            failures=[],
            error=str(exc),
        )

    async with supabase_client, gnews_client:
        result = await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=gnews_client,
            newsapi_key=gnews_api_key,
            news_adapter=GNewsNewsAdapter(client=gnews_client, api_key=gnews_api_key),
            # Phase 8.0.5 Data Activation Pass 2 (2026-09-07): Pass 1's live
            # pull hit real GNews rate limiting on 8/10 teams with zero
            # inter-call spacing. 5s matches the 2026-09-03 GNews
            # validation's own confirmed-safe spacing (0/9 calls rate
            # limited at that pace, vs. 4/9 at 1.5s) -- a real, evidence-
            # based value, not invented.
            inter_call_delay_seconds=5.0,
            # Phase 8.0.5 Pass 2.2 (2026-09-07): THE fix for the real bug
            # Pass 2.1 diagnosed -- this call site never passed a real
            # last_polled_at at all, so every team read as due on every
            # single cron tick regardless of _POLL_INTERVAL_SECONDS.
            # persist_state=True makes both last_polled_at and a durable
            # daily quota guard real (app.persistence.news_worker_poll_state
            # / app.persistence.news_provider_quota) -- see news_worker.py's
            # own docstring for the full mechanism.
            persist_state=True,
        )

    return RunNewsWorkerResponse(
        status=result.status,
        games_considered=result.games_considered,
        teams_considered=result.teams_considered,
        teams_due=result.teams_due,
        teams_skipped_not_due=result.teams_skipped_not_due,
        teams_unresolved=result.teams_unresolved,
        teams_fetched=result.teams_fetched,
        articles_dropped_unresolved=result.articles_dropped_unresolved,
        games_updated=result.games_updated,
        games_skipped_no_data=result.games_skipped_no_data,
        history_rows_written=result.history_rows_written,
        teams_skipped_quota_guard=result.teams_skipped_quota_guard,
        provider_requests_used_today=result.provider_requests_used_today,
        failures=result.failures,
        error=result.error,
    )


class RunWeatherWorkerResponse(BaseModel):
    status: str
    games_considered: int
    games_due: int
    games_in_game: list[str]
    games_skipped_not_due: int
    games_skipped_dome: list[str]
    games_skipped_unresolved_location: list[str]
    snapshots_persisted: int
    failures: list[str]
    error: str | None


@app.post(
    "/v1/internal/weather-worker/run",
    dependencies=[Depends(require_internal_token)],
    response_model=RunWeatherWorkerResponse,
)
async def internal_run_weather_worker() -> RunWeatherWorkerResponse:
    """Phase 8.0.5 Weather Activation (2026-09-07): Weather Worker's real
    invocation path, same minimal shape as `internal_run_odds_worker`
    above. Reuses the EXISTING `run_weather_worker`
    (`app.workers.weather_worker`) completely unchanged in its own
    signature -- this endpoint is a thin HTTP-to-function adapter only.

    **Real `last_polled_at`, from day one -- learned from Pass 2.1's News
    incident, not repeated here.** `run_weather_worker`'s own
    `last_polled_at=None` default safely means "treat every candidate as
    never-polled" for a single call, but would defeat its own cadence gate
    for a repeatedly invoked cron caller. Exactly like
    `internal_run_odds_worker` above, this endpoint calls
    `app.persistence.weather_snapshots.read_last_polled_at()` -- which
    derives real per-game state from already-persisted
    `weather_snapshots.captured_at` history, no new state storage needed
    (unlike News, whose own history table couldn't serve this role) --
    before invoking the worker.

    Same safe missing-credential failure as every other internal endpoint:
    `MissingCredentialError` (credential unset) -- never a raw
    `KeyError` -- returns a clean `status="failed"` result. Reachable
    only via `INTERNAL_SERVICE_TOKEN`."""
    try:
        supabase_client, weatherapi_client, weatherapi_api_key = build_real_weather_worker_clients()
    except MissingCredentialError as exc:
        return RunWeatherWorkerResponse(
            status="failed",
            games_considered=0,
            games_due=0,
            games_in_game=[],
            games_skipped_not_due=0,
            games_skipped_dome=[],
            games_skipped_unresolved_location=[],
            snapshots_persisted=0,
            failures=[],
            error=str(exc),
        )

    async with supabase_client, weatherapi_client:
        last_polled_at = await read_weather_last_polled_at()
        result = await run_weather_worker(
            supabase_client=supabase_client,
            weatherapi_client=weatherapi_client,
            weatherapi_key=weatherapi_api_key,
            last_polled_at=last_polled_at,
        )

    return RunWeatherWorkerResponse(
        status=result.status,
        games_considered=result.games_considered,
        games_due=result.games_due,
        games_in_game=result.games_in_game,
        games_skipped_not_due=result.games_skipped_not_due,
        games_skipped_dome=result.games_skipped_dome,
        games_skipped_unresolved_location=result.games_skipped_unresolved_location,
        snapshots_persisted=result.snapshots_persisted,
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

    if os.environ.get("RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC") == "1":
        import json
        import logging

        _msf_game_boxscore_diag_logger = logging.getLogger(
            "sports-intel-layer.diagnostics.msf_game_boxscore_diagnostic"
        )

        @app.on_event("startup")
        async def _run_msf_game_boxscore_diagnostic_once() -> None:
            """TEMPORARY, one-shot diagnostic hook for MANSA Gate B's
            HQ-authorized game_boxscore diagnostic (2026-09-10, see
            `app.diagnostics.msf_game_boxscore_diagnostic`'s own module
            docstring). Exactly ONE real MySportsFeeds call, guarded by
            the same `activation_run_markers` mechanism every prior MSF
            diagnostic pass has used (a new dedicated run_key). Diagnostic
            only -- persists a raw evidence envelope to `game_events`
            (the existing raw-capture table), never to canonical
            `player_stats`/`team_stats`, and never touches recommendation
            logic or Context Intelligence.

            Logs only a REDACTED summary (`redact_for_logging`) -- never
            the full response body, never any response header value,
            never the credential -- per Gate B's explicit "do not print
            the full raw payload or credential into logs" requirement.
            The durable record of this call lives in the `game_events`
            row this diagnostic writes, not in Railway's own log
            retention."""
            from app.diagnostics.msf_game_boxscore_diagnostic import (
                redact_for_logging,
                run_msf_game_boxscore_diagnostic,
            )

            _msf_game_boxscore_diag_logger.warning("MSF_GAME_BOXSCORE_DIAGNOSTIC_START")
            try:
                result = await run_msf_game_boxscore_diagnostic()
            except Exception as exc:  # last-resort guard -- a diagnostic must never crash startup
                _msf_game_boxscore_diag_logger.error(
                    "MSF_GAME_BOXSCORE_DIAGNOSTIC_UNEXPECTED_FAILURE %s", exc, exc_info=True
                )
            else:
                _msf_game_boxscore_diag_logger.warning(
                    "MSF_GAME_BOXSCORE_DIAGNOSTIC_RESULT %s",
                    json.dumps(redact_for_logging(result), default=str),
                )
            _msf_game_boxscore_diag_logger.warning("MSF_GAME_BOXSCORE_DIAGNOSTIC_DONE")

    if os.environ.get("RUN_MSF_WEEK1_SCHEDULE_RECOVERY") == "1":
        import json
        import logging

        _msf_week1_recovery_logger = logging.getLogger(
            "sports-intel-layer.diagnostics.msf_week1_schedule_recovery"
        )

        @app.on_event("startup")
        async def _run_msf_week1_schedule_recovery_once() -> None:
            """TEMPORARY, one-shot diagnostic hook for MANSA's HQ-authorized
            MSF Week 1 Identity Recovery (2026-09-11, see
            `app.diagnostics.msf_week1_schedule_recovery`'s own module
            docstring). Exactly ONE real MySportsFeeds schedule-level call,
            guarded by the same `activation_run_markers` mechanism every
            prior diagnostic pass has used. Diagnostic only -- persists a
            raw evidence envelope to `game_events` (the existing raw-capture
            table), never to canonical `games`/`game_provider_ids`/
            `team_provider_ids`, and never touches recommendation logic or
            Context Intelligence.

            Logs only a REDACTED summary (`redact_for_logging`) -- never
            the full response body, never any response header value, never
            the credential."""
            from app.diagnostics.msf_week1_schedule_recovery import (
                redact_for_logging as redact_msf_schedule_recovery_for_logging,
                run_msf_week1_schedule_recovery,
            )

            _msf_week1_recovery_logger.warning("MSF_WEEK1_SCHEDULE_RECOVERY_START")
            try:
                result = await run_msf_week1_schedule_recovery()
            except Exception as exc:  # last-resort guard -- a diagnostic must never crash startup
                _msf_week1_recovery_logger.error(
                    "MSF_WEEK1_SCHEDULE_RECOVERY_UNEXPECTED_FAILURE %s", exc, exc_info=True
                )
            else:
                _msf_week1_recovery_logger.warning(
                    "MSF_WEEK1_SCHEDULE_RECOVERY_RESULT %s",
                    json.dumps(redact_msf_schedule_recovery_for_logging(result), default=str),
                )
            _msf_week1_recovery_logger.warning("MSF_WEEK1_SCHEDULE_RECOVERY_DONE")
