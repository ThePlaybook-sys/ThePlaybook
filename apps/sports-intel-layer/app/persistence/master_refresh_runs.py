"""`master_refresh_runs` persistence (Milestone 4.9) -- the durable
record that a specific Master Refresh execution occurred, when it
completed, and how it went. Confirmed by direct inspection this did not
exist before this milestone: `MasterRefreshResult` (`app.master_refresh.
run`) is a pure in-memory dataclass, discoverable by nothing outside the
process that produced it. This module is the fix -- a row created BEFORE
the refresh's crash-prone work begins, updated once at completion, never
updated again after that (mirrors `recommendation_agent_outputs`'s
append-only-after-write discipline in spirit, though no DB trigger
enforces it here since exactly one completion update is the entire
lifecycle of a row, not an ongoing stream of writes to prevent).

Status vocabulary matches `MasterRefreshResult.status` exactly
('success'/'partial'/'failed'), plus 'running' for the interval between
creation and completion -- no second, unrelated vocabulary."""
from __future__ import annotations

import httpx


class MasterRefreshRunsError(Exception):
    """Raised when a `master_refresh_runs` read/write fails on Supabase's
    side."""


async def start_master_refresh_run(client: httpx.AsyncClient, headers: dict) -> str:
    """Creates one `master_refresh_runs` row with `status='running'`
    BEFORE any crash-prone refresh work begins -- this row's existence,
    not a later write, is what a retry discovers and reasons about.
    Returns the new row's `id`."""
    response = await client.post(
        "/rest/v1/master_refresh_runs",
        json={"status": "running"},
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise MasterRefreshRunsError(f"failed to start master_refresh_run: {response.status_code} {response.text}")
    rows = response.json()
    if not rows:
        raise MasterRefreshRunsError("master_refresh_run insert returned no row")
    return rows[0]["id"]


async def complete_master_refresh_run(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    run_id: str,
    status: str,
    season_string: str | None,
    games_in_slate: int,
    completed_at_iso: str,
) -> None:
    """Updates the run's row exactly once, at completion -- `status` must
    already be 'success'/'partial'/'failed' (never 'running' again, never
    re-derived here; the caller's own `MasterRefreshResult.status` is the
    single source of truth this function transcribes, not recomputes).
    A partial refresh is persisted as 'partial', never silently upgraded
    to 'success' -- the whole reason this table exists is to preserve
    that distinction honestly for the Recommendation Worker to read."""
    response = await client.patch(
        "/rest/v1/master_refresh_runs",
        params={"id": f"eq.{run_id}"},
        json={
            "status": status,
            "season_string": season_string,
            "games_in_slate": games_in_slate,
            "completed_at": completed_at_iso,
        },
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 204):
        raise MasterRefreshRunsError(
            f"failed to complete master_refresh_run {run_id!r}: {response.status_code} {response.text}"
        )
