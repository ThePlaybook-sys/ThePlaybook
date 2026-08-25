"""Read-only `master_refresh_runs` access (Milestone 4.9). This service
never writes this table -- `sports-intel-layer`'s own `run_master_refresh`
owns creation/completion (Milestone 4.9-1). The Recommendation Worker
reads it directly via its own service-role Supabase access rather than a
new sports-intel-layer HTTP endpoint (Mac's approved "durable-state
coordination through Supabase" decision)."""
from __future__ import annotations

import httpx


class MasterRefreshRunsReadError(Exception):
    """Raised when a `master_refresh_runs` read fails on Supabase's
    side."""


#: Both a completion status the Worker treats as eligible to proceed on
#: -- `partial` is included deliberately: an individual game/category
#: failure inside one Master Refresh run doesn't invalidate every OTHER
#: game's own already-assembled `daily_game_intelligence`, and this
#: milestone's per-game/candidate/user isolation discipline already
#: assumes partial upstream data is a normal, not exceptional, case.
#: `running`/`failed` are never eligible -- a run still in progress has
#: no guaranteed-complete slate yet, and a fully failed run produced
#: nothing trustworthy to build on.
ELIGIBLE_STATUSES = ("success", "partial")


async def read_latest_eligible_run(client: httpx.AsyncClient, headers: dict) -> dict | None:
    """Returns the most recently COMPLETED (`success` or `partial`)
    `master_refresh_runs` row, ordered by `completed_at` descending, or
    `None` if no such run exists yet. Never returns a `running` or
    `failed` run."""
    response = await client.get(
        "/rest/v1/master_refresh_runs",
        params={
            "status": f"in.({','.join(ELIGIBLE_STATUSES)})",
            "select": "id,started_at,completed_at,status,season_string,games_in_slate",
            "order": "completed_at.desc.nullslast",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise MasterRefreshRunsReadError(
            f"failed to read master_refresh_runs: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None
