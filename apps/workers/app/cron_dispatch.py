"""Pre-Phase-6 Operational Readiness Gate, Decision 3 (2026-08-27).

The finite Railway Cron Job entry point for this service's three
internal cycles. Deliberately NOT a FastAPI route -- `worker-scheduled`
itself stays exactly as it was (Decision 2: always-on, unchanged),
because Railway Cron Jobs run a service's *start command* on a schedule
and require the process to exit when done -- they cannot "call an
endpoint" on an already-running server (confirmed against Railway's own
docs before writing this). This module is deployed as a SEPARATE,
short-lived Railway service (or several, one per differing cadence, per
Decision 4) whose start command is `python -m app.cron_dispatch`, reusing
this exact codebase/image -- not a second copy of it.

**This module is an infrastructure adapter, not business logic.** It
does exactly four things: start, POST to one already-existing internal
endpoint on the (unchanged, always-on) `worker-scheduled` service over
Railway's private network, log the result, exit 0/1. It duplicates
nothing -- no eligibility rule, no guardrail, no grading/weighting
logic. Every real decision still lives exactly where it already did:
inside `app.recommendation_worker`/`app.postgame_grading_worker`/
`app.adaptive_weighting_worker`, called via `worker-scheduled`'s own
HTTP endpoints, unchanged.

Target selected via `CRON_DISPATCH_TARGET` (one of `recommendation-
worker`, `postgame-grading`, `adaptive-weighting`) -- one script, one
image, multiple Railway Cron Job services differing only in this env var
and their own `cronSchedule`, per Decision 4's "smallest number of cron
services that preserves correct cadence" instruction."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger("cron_dispatch")

_TARGET_PATHS = {
    "recommendation-worker": "/v1/internal/recommendation-worker/run",
    "postgame-grading": "/v1/internal/postgame-grading/run",
    "adaptive-weighting": "/v1/internal/adaptive-weighting/run",
}


class CronDispatchError(Exception):
    """Raised for any failure dispatching to `worker-scheduled` -- the
    caller (`main`) is the only place this is caught, converting it into
    a non-zero exit code rather than a Python traceback as the job's
    final state."""


async def dispatch(*, target: str, base_url: str, internal_token: str, client: httpx.AsyncClient) -> dict:
    """POSTs to the one `worker-scheduled` endpoint `target` names.
    Returns the parsed JSON response on any 2xx. Raises `CronDispatchError`
    on a non-2xx response or transport failure -- this function makes no
    judgment about WHETHER the underlying cycle found anything to do,
    only whether the call itself succeeded; `worker-scheduled`'s own
    endpoints already return an honest `status`/`no_eligible_run`-style
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
        raise CronDispatchError(f"transport failure calling worker-scheduled{path}: {exc}") from exc
    if response.status_code != 200:
        raise CronDispatchError(f"worker-scheduled{path} returned {response.status_code}: {response.text}")
    return response.json()


async def _run() -> int:
    target = os.environ["CRON_DISPATCH_TARGET"]
    base_url = os.environ["RAILWAY_SERVICE_WORKER_SCHEDULED_URL"]
    internal_token = os.environ["INTERNAL_SERVICE_TOKEN"]

    _logger.info("cron_dispatch starting target=%s base_url=%s", target, base_url)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            result = await dispatch(target=target, base_url=base_url, internal_token=internal_token, client=client)
    except CronDispatchError as exc:
        _logger.error("cron_dispatch failed target=%s error=%s", target, exc)
        return 1

    _logger.info("cron_dispatch succeeded target=%s result=%s", target, result)
    return 0


def main() -> None:
    exit_code = asyncio.run(_run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
