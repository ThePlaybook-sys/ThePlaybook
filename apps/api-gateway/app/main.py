import os
from datetime import datetime, timezone

import httpx
import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    # No privacy policy live yet (Volume 1 §10) to disclose PII collection —
    # revisit once one is in place.
    send_default_pii=False,
    # Without this, the SDK defaults every event to "production" regardless
    # of which Railway environment it actually came from.
    environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
)

app = FastAPI(title="The Playbook — API Gateway")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api-gateway"}


# DEMO-4: mounted unconditionally (unlike sports-intel-layer's demo router,
# which mounts only in the demo environment) -- every route here proxies to
# sports-intel-layer, whose own isolation guard refuses outside demo, and
# is itself gated by the demo-operator token (app.demo_routes' own
# docstring, Mac's Option A). Mounting api-gateway's demo routes everywhere
# is harmless: calling them from dev/staging/production without the demo
# environment's own DEMO_OPERATOR_TOKEN/SPORTS_INTEL_LAYER_URL configured
# simply 500s, never reaches real demo data.
from app.demo_routes import login_router as demo_login_router  # noqa: E402
from app.demo_routes import router as demo_router  # noqa: E402

app.include_router(demo_login_router)
app.include_router(demo_router)

# Phase 6 Milestone 2 -- thin read-only exposure of existing Phase 1-5
# data (Volume 5 v5.0). See each module's own docstring for scope.
from app.recommendations import router as recommendations_router  # noqa: E402
from app.subscription import router as subscription_router  # noqa: E402
from app.track_record import router as track_record_router  # noqa: E402

app.include_router(recommendations_router)
app.include_router(track_record_router)
app.include_router(subscription_router)


if os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev") == "dev":

    @app.get("/sentry-debug")
    async def trigger_error():
        division_by_zero = 1 / 0


class OnboardingComplete(BaseModel):
    # Required and non-blank: this is the schema-level half of AC #4 ("attempting
    # to complete onboarding without a jurisdiction value is blocked with a clear
    # message"). Pydantic's own validation error on a missing/blank field already
    # satisfies "clear message, not silent failure" without extra custom logic.
    jurisdiction_state: str = Field(min_length=1)
    display_name: str | None = None
    persona_classification: str | None = None
    betting_experience: str | None = None
    primary_goal: str | None = None
    risk_tolerance: str | None = None
    preferred_unit_size: float | None = None
    max_parlay_legs: int | None = None


async def _postgrest_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}


@app.get("/v1/user/profile")
async def get_profile(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    supabase_url = os.environ["SUPABASE_URL"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{supabase_url}/rest/v1/user_profiles",
            params={"id": f"eq.{current_user.id}", "select": "*"},
            headers=await _postgrest_headers(),
        )
    if response.status_code != 200 or not response.json():
        raise HTTPException(status_code=404, detail="Profile not found")
    return response.json()[0]


@app.patch("/v1/user/profile")
async def complete_onboarding(
    body: OnboardingComplete, current_user: CurrentUser = Depends(get_current_user)
) -> dict:
    supabase_url = os.environ["SUPABASE_URL"]
    update = body.model_dump(exclude_none=True)
    update["onboarding_completed_at"] = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.patch(
            f"{supabase_url}/rest/v1/user_profiles",
            params={"id": f"eq.{current_user.id}"},
            json=update,
            headers={**await _postgrest_headers(), "Prefer": "return=representation"},
        )
    if response.status_code != 200 or not response.json():
        raise HTTPException(status_code=404, detail="Profile not found")
    return response.json()[0]
