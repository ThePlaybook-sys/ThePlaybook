import os

import sentry_sdk
from fastapi import FastAPI

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

    # TEMPORARY (Mac, 2026-08-14) -- SportsDataIO Team-identity live
    # verification, scoped to /v3/nfl/scores/json/Teams only. Removed in a
    # follow-up commit immediately after capture. See
    # app/diagnostics/sportsdataio_capture.py for the full approved plan
    # and safeguards.
    from app.diagnostics.sportsdataio_capture import router as _sportsdataio_router

    app.include_router(_sportsdataio_router)
