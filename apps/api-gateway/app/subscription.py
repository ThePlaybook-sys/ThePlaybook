"""Phase 6 Milestone 2 -- the authenticated user's own subscription
tier/status only (Volume 5 v5.0 §6/HQ Final Decision 9). No entitlement
inference, no other user's row is ever reachable (filtered by
`user_id = eq.{current_user.id}` server-side, same as every other
own-row read in this module).

Never fabricates a 'free' tier for a user with no subscription row --
returns null/null, matching `app.entitlement.read_active_subscription_
tier`'s own "never default to any tier" rule. That distinction is the
frontend's to render, not this route's to paper over.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, get_current_user
from app.supabase_client import new_client, postgrest_headers

router = APIRouter(prefix="/v1/user", tags=["subscription"])


@router.get("/subscription")
async def get_own_subscription(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with new_client() as client:
        response = await client.get(
            "/rest/v1/subscriptions",
            params={
                "user_id": f"eq.{current_user.id}",
                "select": "tier,status,billing_period,current_period_end",
                "order": "created_at.desc",
                "limit": "1",
            },
            headers=postgrest_headers(),
        )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return {"tier": None, "status": None, "billingPeriod": None, "currentPeriodEnd": None}
    row = rows[0]
    return {
        "tier": row["tier"],
        "status": row["status"],
        "billingPeriod": row["billing_period"],
        "currentPeriodEnd": row["current_period_end"],
    }
