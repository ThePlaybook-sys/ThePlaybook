"""Pre-Phase-6 Operational Readiness Gate, Decision 3 (2026-08-27; target
table widened for Decision 6, same date). Widened again for Phase 7
Milestone 7.0B (2026-09-02, `odds-worker` target) -- same generic
dispatcher, no new mechanism. Comment-only touch 2026-09-07 (Phase 7
Controlled Real Odds Activation) to force a real rebuild for
`cron-odds-worker`, whose own `apps/workers` build root had no other
changed file to trigger one -- no behavior change.

The finite Railway Cron Job entry point for this project's schedulable
internal cycles. Deliberately NOT a FastAPI route --
`worker-scheduled` itself stays exactly as it was (Decision 2: always-on,
unchanged), because Railway Cron Jobs run a service's *start command* on
a schedule and require the process to exit when done -- they cannot
"call an endpoint" on an already-running server (confirmed against
Railway's own docs before writing this). This module is deployed as a
SEPARATE, short-lived Railway service (one per differing cadence/target,
per Decision 4) whose start command is `python -m app.cron_dispatch`,
reusing this exact codebase/image -- not a second copy of it.

**This module is an infrastructure adapter, not business logic.** It
does exactly four things: start, POST to one already-existing internal
endpoint over Railway's private network, log the result, exit 0/1. It
duplicates nothing -- no eligibility rule, no guardrail, no grading/
weighting/refresh/fetch logic. Every real decision still lives exactly
where it already did: inside `app.recommendation_worker`/
`app.postgame_grading_worker`/`app.adaptive_weighting_worker` (all three
called via `worker-scheduled`'s own HTTP endpoints, unchanged), inside
`sports-intel-layer`'s `app.master_refresh.run.run_master_refresh`
(called via its own internal endpoint, Decision 6), or inside
`sports-intel-layer`'s `app.workers.odds_worker.run_odds_worker` (called
via its own internal endpoint, Phase 7 Milestone 7.0B) -- unchanged by
this module either way.

Target selected via `CRON_DISPATCH_TARGET` (one of `recommendation-
worker`, `postgame-grading`, `adaptive-weighting`, `master-refresh`,
`odds-worker`) -- one script, one image, multiple Railway Cron Job
services differing only in this env var, their own
`CRON_DISPATCH_BASE_URL`, and their own `cronSchedule`, per Decision 4's
"smallest number of cron services that preserves correct cadence"
instruction.

`CRON_DISPATCH_BASE_URL` (not a target-specific constant) is deliberately
generic rather than hardcoded to `worker-scheduled`: three of the five
targets live on `worker-scheduled`, but `master-refresh` and
`odds-worker` both live on `sports-intel-layer` -- a different service
entirely. Each deployed cron service's own env vars name which internal
service it talks to; this module has no opinion about which service that
is, only which path to POST to for a given target name."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx
import sentry_sdk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger("cron_dispatch")


# ===========================================================================
# Sentry (2026-09-16, "CRON SENTRY + ODDS API BUDGET ARMING")
# ===========================================================================
#
# WHY THIS MODULE NEEDED ITS OWN INIT. Every FastAPI service in this project
# already calls `sentry_sdk.init()` in its own `app/main.py`, and
# `apps/workers/app/main.py` is no exception -- but the cron services do not
# run it. Their start command is `python -m app.cron_dispatch`, a DIFFERENT
# entry point in the SAME image, so the SDK was installed
# (`sentry-sdk[fastapi]` in requirements.txt) and never initialized. The
# 2026-09-16 coverage audit found the consequence: nine cron services, the
# entire schedule -> odds -> recommendation -> grading pipeline, reporting
# nothing at all, while three of them crashed silently for hours.
#
# The coverage boundary was never "which app" -- it was "FastAPI entry point
# vs. cron entry point", and this is the cron side of it.
#
# FLUSH IS NOT OPTIONAL HERE. Sentry's transport is asynchronous and
# background-threaded, which is fine for a long-lived web process but not for
# a finite job that calls `sys.exit` seconds later: without an explicit
# flush, a captured event can be discarded before it ever leaves the
# container. Every exit path below flushes.

#: Statuses that are NORMAL OPERATION and must never raise a Sentry event,
#: per HQ's explicit list: paused/disabled, successful-empty, budget or
#: throttle pauses, and ordinary success. A cron that correctly does nothing
#: is not an error, and treating it as one would train the alert to be
#: ignored -- which costs more than having no alert at all.
_NON_ERROR_STATUSES = frozenset(
    {
        "success",
        "completed",
        "paused",
        "disabled",
        "skipped",
        "no_eligible_run",
        # The Odds Worker's own two deliberate, named stop conditions. Both
        # mean "the guard worked", which is the system behaving correctly.
        "skipped_credit_guard",
        "skipped_daily_budget",
    }
)


def _init_sentry() -> None:
    """Initializes Sentry for a cron process, with the identity tags the
    coverage audit found missing.

    `dsn` is read with `.get`, matching every other service in this project:
    an unset DSN disables the SDK rather than crashing a cron job over
    telemetry configuration. Telemetry must never be the reason a scheduled
    job fails to run.

    **The DSN value is supplied as a Railway variable REFERENCE** rather than
    a copied literal, so it is resolved server-side at deploy time and never
    passes through a session, a log line, or this repository.
    """
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        send_default_pii=False,
        environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
        # Release attribution. RAILWAY_GIT_COMMIT_SHA is the value we
        # actually want (it maps an event to a commit); the deployment id is
        # a weaker but still useful fallback that at least distinguishes one
        # build from another. Both may legitimately be absent, in which case
        # Sentry simply records no release -- never a fabricated one.
        release=os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("RAILWAY_DEPLOYMENT_ID")
        or None,
    )
    # The audit's §6 finding: four services shared one Sentry project with no
    # way to tell them apart, because Sentry's default `server_name` on
    # Railway is an opaque container id. These two tags make an event
    # attributable to a service AND to the specific job it was running, which
    # is what makes a per-service or per-target alert rule possible at all.
    sentry_sdk.set_tag("service", os.environ.get("RAILWAY_SERVICE_NAME", "unknown-cron"))
    sentry_sdk.set_tag("cron_target", os.environ.get("CRON_DISPATCH_TARGET", "unset"))


def _flush() -> None:
    """Flushes pending events before the process exits. Bounded so a Sentry
    outage can never hold a cron job open indefinitely."""
    try:
        sentry_sdk.flush(timeout=5.0)
    except Exception:  # pragma: no cover - telemetry must never fail the job
        _logger.warning("sentry flush failed", exc_info=True)


#: Payload keys that hold a worker's per-item results. Deliberately
#: generic rather than a Recommendation-Worker special case: every worker
#: in this project reports the same shape -- a list of dicts, each with a
#: `status` and/or an `error` -- so one rule covers grading's `legs` and
#: `products`, recommendation's `games`, and anything later that follows
#: the house convention.
_NESTED_RESULT_KEYS = ("games", "legs", "products", "items")


def _nested_failure_census(result: dict) -> tuple[int, int, str] | None:
    """Counts per-item failures across every known nested collection.

    Returns `(failed, total, sample_error)` when at least one item failed,
    or `None` when there is nothing nested to judge -- which includes the
    genuinely healthy case where every item succeeded, so a clean
    `completed` run stays silent exactly as before.

    An item counts as failed when it carries `status="failed"` or a
    non-null `error`. Both are checked because the two worker families
    differ: postgame grading sets a per-leg `status`, while the
    Recommendation Worker's per-game entries carry the error text.
    """
    failed = 0
    total = 0
    sample: str | None = None
    for key in _NESTED_RESULT_KEYS:
        items = result.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            total += 1
            error = item.get("error")
            if item.get("status") == "failed" or error:
                failed += 1
                if sample is None:
                    sample = str(error) if error else "status=failed with no detail reported"
    if not failed:
        return None
    return failed, total, sample or "no detail reported"


def result_failure_summary(result: dict) -> tuple[str, str] | None:
    """Classifies a 2xx worker payload as reportable or not.

    Returns `(level, summary)` when the worker reported real trouble, or
    `None` when it reported normal operation.

    **This is the half of cron monitoring that HTTP status codes cannot
    see, and the reason the odds credit leak went unnoticed for hours.**
    Workers in this project are deliberately written never to raise --
    `run_odds_worker`'s own docstring says "Always returns an
    `OddsWorkerResult`, never raises" -- so a total failure arrives as a
    `status` field inside a **200 OK**. Without this function, a worker could
    fail on every single cycle and Sentry would never see an event, because
    nothing ever threw.

    Two levels, deliberately distinguished:

    * `error`   -- `status="failed"`: the cycle did not do its job. This is
                   the case HQ named explicitly.
    * `warning` -- a status outside the known-good set that also carries a
                   non-empty `failures` list (in practice `partial`): the
                   cycle partly worked. **HQ's directive did not name this
                   case either way**, so it is reported at a lower severity
                   rather than silently dropped -- twelve consecutive
                   `partial` cycles were exactly the shape of the credit
                   leak, and a `partial` that carries failures is not
                   "successful processing" by any reading. Flagged as a
                   judgment call for HQ to overrule.
    """
    status = result.get("status")
    if status == "failed":
        detail = result.get("error") or result.get("failures") or "no detail reported"
        return "error", f"worker reported status=failed: {detail}"

    # Nested failures are checked BEFORE the known-good status set, not
    # after it. Ordering is the whole fix: on 2026-09-17 the
    # Recommendation Worker reported `status="completed"` while every one
    # of its 257 games carried an `error`, and because "completed" is a
    # member of `_NON_ERROR_STATUSES` this function returned `None`
    # without ever looking inside. A total failure can wear a success
    # status, so the payload has to be inspected before the label is
    # trusted.
    nested = _nested_failure_census(result)
    if nested is not None:
        failed, total, sample = nested
        scope = "every item" if failed == total else f"{failed} of {total} items"
        level = "error" if failed == total else "warning"
        return level, f"worker reported status={status!r} but {scope} failed: {sample}"

    if status in _NON_ERROR_STATUSES:
        return None
    failures = result.get("failures")
    if failures:
        return "warning", f"worker reported status={status!r} with failures: {failures}"
    return None

_TARGET_PATHS = {
    "recommendation-worker": "/v1/internal/recommendation-worker/run",
    "postgame-grading": "/v1/internal/postgame-grading/run",
    "adaptive-weighting": "/v1/internal/adaptive-weighting/run",
    "master-refresh": "/v1/internal/master-refresh/run",
    #: Phase 7 Milestone 7.0B (2026-09-02): the first Phase 3E specialized
    #: worker to gain a real invocation path -- lives on `sports-intel-layer`,
    #: same as `master-refresh`, not `worker-scheduled`. Only Odds Worker was
    #: activated that milestone; see the two entries directly below for the
    #: first real activation of a second/third specialized worker.
    "odds-worker": "/v1/internal/odds-worker/run",
    #: Phase 8.0.5 Data Activation Pass 1 (2026-09-07): the BALLDONTLIE
    #: Injury Worker's real invocation path -- lives on `sports-intel-layer`,
    #: same as `odds-worker`. Target mapping added now so recurring
    #: activation (once separately authorized) is a config-only change, no
    #: further code -- no Railway Cron Job service targets this yet; HQ
    #: authorized only a one-time controlled proof pull this pass, not
    #: recurring polling (`docs/ops/phase-8.0.5-data-activation-pass-1-2026-09-07.md`).
    "balldontlie-injury-worker": "/v1/internal/balldontlie-injury-worker/run",
    #: Phase 8.0.5 Data Activation Pass 1 (2026-09-07): News Worker's real
    #: invocation path (GNews-backed for this call site only -- see
    #: `app.main.internal_run_news_worker`'s own docstring; `news_worker.py`'s
    #: own NewsAPI default is unchanged). Same "target mapped, no cron
    #: service created yet" status as the entry above.
    "news-worker": "/v1/internal/news-worker/run",
    #: Phase 8.0.5 Weather Activation (2026-09-07): Weather Worker's real
    #: invocation path -- lives on `sports-intel-layer`, same as
    #: `odds-worker`/`news-worker`. Uses a real, persisted
    #: `last_polled_at` (derived from `weather_snapshots.captured_at`)
    #: from its very first cron tick, per Pass 2.1's News incident.
    "weather-worker": "/v1/internal/weather-worker/run",
    #: Postgame Dispatcher + Sunday Recovery (2026-09-14): the MSF
    #: postgame ingestion worker's real invocation path -- lives on
    #: `sports-intel-layer`, same as `odds-worker`/`news-worker`/
    #: `weather-worker`. Closes the exact gap the Sunday Postgame
    #: Ingestion Audit found: the worker and its single-game endpoint both
    #: already existed and were both already correct; nothing had ever
    #: called either automatically until this target/endpoint pair.
    "msf-postgame-worker": "/v1/internal/msf-postgame/dispatch",
    #: Canonical Schedule + Finalization Hardening (2026-09-15): turns a
    #: `confirmed_complete` MySportsFeeds postgame observation into a
    #: finalized canonical game -- lives on `sports-intel-layer`, same as
    #: `msf-postgame-worker`. Deliberately a SEPARATE target from that one
    #: rather than a step inside it: the dispatcher is a full zero-call
    #: no-op when `MSF_POSTGAME_ENABLED=false`, and finalization must keep
    #: draining the already-captured backlog while ingestion is paused for
    #: cost, since it makes no provider call at all. Costs zero provider
    #: calls of any kind, so it is safe on any cadence.
    "canonical-finalization": "/v1/internal/canonical-finalization/run",
    #: Master Refresh V2 (2026-09-15): the schedule-only refresh --
    #: exactly ONE SportsDataIO Schedule call and zero roster calls,
    #: versus up to 33 for the `master-refresh` target above. This is the
    #: target a daily canonical-schedule cron should use; `master-refresh`
    #: remains mapped for the combined run. Both are gated by
    #: `MASTER_REFRESH_ENABLED` on `sports-intel-layer` itself, so a tick
    #: against either spends nothing unless the refresh is explicitly
    #: enabled there.
    "schedule-refresh": "/v1/internal/schedule-refresh/run",
    #: Remaining unwired specialized workers: Player Props/Pregame -- see
    #: the Phase 3E specialized worker runtime invocation debt item
    #: recorded in PROGRESS.md.
}


class CronDispatchError(Exception):
    """Raised for any failure dispatching to `base_url` -- the caller
    (`main`) is the only place this is caught, converting it into a
    non-zero exit code rather than a Python traceback as the job's
    final state."""


async def dispatch(*, target: str, base_url: str, internal_token: str, client: httpx.AsyncClient) -> dict:
    """POSTs to the one internal endpoint `target` names, on whichever
    service `base_url` points at (`worker-scheduled` for three of the
    five targets, `sports-intel-layer` for `master-refresh` and
    `odds-worker`). Returns the
    parsed JSON response on any 2xx. Raises `CronDispatchError` on a
    non-2xx response or transport failure -- this function makes no
    judgment about WHETHER the underlying cycle found anything to do,
    only whether the call itself succeeded; the target endpoint's own
    response already returns an honest `status`/`no_eligible_run`-style
    result for "nothing to do this cycle", which is success, not an
    error, from this dispatcher's point of view."""
    if target not in _TARGET_PATHS:
        raise CronDispatchError(f"unknown CRON_DISPATCH_TARGET={target!r}; expected one of {sorted(_TARGET_PATHS)}")
    path = _TARGET_PATHS[target]
    try:
        response = await client.post(
            f"{base_url}{path}",
            headers={"X-Internal-Token": internal_token, "Content-Type": "application/json"},
            json={},
        )
    except httpx.HTTPError as exc:
        raise CronDispatchError(f"transport failure calling {base_url}{path}: {exc}") from exc
    if response.status_code != 200:
        raise CronDispatchError(f"{base_url}{path} returned {response.status_code}: {response.text}")
    return response.json()


async def _run() -> int:
    # Invalid configuration (a missing required variable) raises KeyError
    # here, at module-entry, before anything else can run -- one of the three
    # pre-init windows the coverage audit named. It is captured explicitly
    # rather than left to an excepthook, because the job exits immediately
    # afterwards and an unflushed event is a lost event.
    try:
        target = os.environ["CRON_DISPATCH_TARGET"]
        base_url = os.environ["CRON_DISPATCH_BASE_URL"]
        internal_token = os.environ["INTERNAL_SERVICE_TOKEN"]
    except KeyError as exc:
        _logger.error("cron_dispatch misconfigured: missing required variable %s", exc)
        sentry_sdk.capture_exception(exc)
        return 1

    # Re-tag now that the target is known: `_init_sentry` runs before this
    # and reads the same variable, but re-setting it here keeps the tag
    # correct even if initialization order ever changes.
    sentry_sdk.set_tag("cron_target", target)
    _logger.info("cron_dispatch starting target=%s base_url=%s", target, base_url)
    try:
        # 600s (was 120s until the msf-postgame-worker target, 2026-09-14):
        # that target's own endpoint can process up to
        # MAX_GAMES_PER_DISPATCH_TICK real games sequentially in one
        # request (observed live, SF@LAR Live Proof: ~2 minutes/game for a
        # full fetch + ~95-player resolve/persist cycle) -- a longer
        # client-side timeout is backward-safe for every other, much
        # faster target too, so this is a shared bump, not a per-target
        # special case.
        async with httpx.AsyncClient(timeout=600.0) as client:
            result = await dispatch(target=target, base_url=base_url, internal_token=internal_token, client=client)
    except CronDispatchError as exc:
        # Covers every dispatch-side failure in one place, because
        # `dispatch` already normalizes them: an unknown/invalid target, a
        # transport failure (DNS, connect, timeout, a malformed base URL --
        # the exact shape that had cron-weather-worker crashing every 15
        # minutes unseen), and any non-2xx response from the internal
        # endpoint.
        _logger.error("cron_dispatch failed target=%s error=%s", target, exc)
        sentry_sdk.capture_exception(exc)
        return 1
    except Exception as exc:
        # Anything genuinely unhandled. Captured and re-reported rather than
        # allowed to reach a bare traceback, so the event is flushed before
        # the process dies.
        _logger.exception("cron_dispatch crashed target=%s", target)
        sentry_sdk.capture_exception(exc)
        return 1

    # A 2xx does NOT mean the work succeeded -- see `result_failure_summary`.
    reportable = result_failure_summary(result)
    if reportable is not None:
        level, summary = reportable
        with sentry_sdk.new_scope() as scope:
            scope.set_level(level)
            scope.set_context("worker_result", result)
            sentry_sdk.capture_message(f"cron target {target}: {summary}")
        _logger.error("cron_dispatch target=%s reported failure: %s", target, summary)
        # Still exit 0: the dispatch itself worked, and the worker returned a
        # well-formed answer. Marking the Railway deployment CRASHED for a
        # structured worker failure would conflate two different conditions
        # and would make a budget pause look like a broken job. Sentry is now
        # the channel for this, which is the whole point of the change.
        _logger.info("cron_dispatch completed target=%s result=%s", target, result)
        return 0

    _logger.info("cron_dispatch succeeded target=%s result=%s", target, result)
    return 0


def main() -> None:
    _init_sentry()
    # Defaults to failure: if `_run` itself dies in a way it could not
    # report, the job must exit non-zero rather than let an unbound name
    # turn a real failure into a different, more confusing one.
    exit_code = 1
    try:
        exit_code = asyncio.run(_run())
    except BaseException as exc:  # noqa: BLE001 - last resort before exit
        _logger.exception("cron_dispatch aborted before it could report")
        sentry_sdk.capture_exception(exc)
    finally:
        _flush()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
