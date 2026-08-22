"""Read-only `user_profiles` access (Milestone 4.6, Decision F). Feeds
Bankroll Coach's `bankroll_profile`. Confirmed live against dev: every
real (non-fixture) `user_profiles` row has `optional_bankroll IS NULL` --
Phase 6 onboarding UI doesn't exist yet, so this read path must degrade
correctly the moment it's used, not merely in a synthetic test."""
from __future__ import annotations

import httpx


class UserProfilesReadError(Exception):
    """Raised when a `user_profiles` read fails on Supabase's side."""


async def read_user_profile(client: httpx.AsyncClient, headers: dict, *, user_id: str) -> dict | None:
    """Reads one `user_profiles` row by id. Returns `None` when no row
    exists -- never a synthesized shape, matching this package's other
    readers' exact convention."""
    response = await client.get(
        "/rest/v1/user_profiles",
        params={"id": f"eq.{user_id}", "select": "id,risk_tolerance,preferred_unit_size,optional_bankroll"},
        headers=headers,
    )
    if response.status_code != 200:
        raise UserProfilesReadError(f"failed to read user_profiles {user_id}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None
