import os

import sentry_sdk
from fastapi import FastAPI

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # No privacy policy live yet (Volume 1 §10) to disclose PII collection —
    # revisit once one is in place.
    send_default_pii=False,
)

app = FastAPI(title="The Playbook — AI Orchestrator")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-orchestrator"}


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0
