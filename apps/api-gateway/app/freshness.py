"""Phase 6 Milestone 7.1 -- source-data-freshness read model.

Exposes the single most recent `master_refresh_runs` row so the frontend
can show "how fresh is MANSA's underlying data" as a page-level concept,
structurally separate from any recommendation's own decision timestamp
(`recommendation_activation_snapshots.activated_at`, already exposed via
`recommendations.py`'s `decidedAt` field) -- HQ's explicit M7.1
instruction: never collapse the two into a generic "Updated." A thin
read only: no new refresh logic, no polling, no computation beyond
selecting and reshaping one row.

`master_refresh_runs` has RLS enabled with no policy (default-deny to
anon/authenticated) -- only the service-role client this module reuses
from every other Milestone 2+ read route can see it.

Three real states, distinguished honestly rather than collapsed:
- no row at all -> `status: null` ("no refresh has ever run here")
- latest row has no `completed_at` yet -> a run is in progress
- latest row has `completed_at` -> the freshness timestamp to show
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, get_current_user
from app.supabase_client import new_client, postgrest_headers

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/freshness")
async def get_source_freshness(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with new_client() as client:
        response = await client.get(
            "/rest/v1/master_refresh_runs",
            params={
                "select": "status,started_at,completed_at,games_in_slate",
                "order": "started_at.desc",
                "limit": "1",
            },
            headers=postgrest_headers(),
        )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return {"status": None, "startedAt": None, "completedAt": None, "gamesInSlate": None}

    row = rows[0]
    return {
        "status": row["status"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
        "gamesInSlate": row["games_in_slate"],
    }
