import logging
import os

import httpx
import sentry_sdk
from fastapi import FastAPI

logger = logging.getLogger("sports-intel-layer.diagnostics")

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


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0

    @app.on_event("startup")
    async def _sportsdataio_connectivity_probe() -> None:
        """TEMPORARY diagnostic (Mac, 2026-08-11) -- answers exactly one
        question: can Railway dev's outbound network reach api.sportsdata.io
        at all, independent of this coding sandbox's own egress policy
        (already confirmed blocked). Deliberately unauthenticated -- no API
        key is read, sent, or logged here. Only the outcome type and, if a
        response came back, its HTTP status code are logged -- never a
        response body, header, or URL containing a key. To be removed in a
        follow-up commit once the result is reported, regardless of outcome.

        Gated on RAILWAY_SERVICE_ID (only set when actually running on
        Railway) in addition to the dev-only block above, so this never
        fires during `pytest` (local or CI) or any other non-Railway
        context -- it would otherwise attempt a real network call as a side
        effect of running the test suite, which is not what this is for.
        """
        if not os.environ.get("RAILWAY_SERVICE_ID"):
            return
        target = "https://api.sportsdata.io/v3/nfl/scores/json/CurrentSeason"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(target)
            logger.warning(
                "SPORTSDATAIO_CONNECTIVITY_PROBE: reached host, status=%s",
                response.status_code,
            )
        except httpx.TimeoutException:
            logger.warning("SPORTSDATAIO_CONNECTIVITY_PROBE: timed out (no response)")
        except httpx.ConnectError as exc:
            logger.warning("SPORTSDATAIO_CONNECTIVITY_PROBE: connect error: %s", type(exc).__name__)
        except httpx.HTTPError as exc:
            logger.warning("SPORTSDATAIO_CONNECTIVITY_PROBE: transport error: %s", type(exc).__name__)
