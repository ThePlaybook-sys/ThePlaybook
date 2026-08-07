import os

import sentry_sdk
from fastapi import FastAPI

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
)

app = FastAPI(title="The Playbook — API Gateway")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api-gateway"}


@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
