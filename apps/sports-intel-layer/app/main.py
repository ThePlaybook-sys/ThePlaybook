import os

import sentry_sdk
from fastapi import FastAPI

from app.environment_safety import assert_demo_isolation

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


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
