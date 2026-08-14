"""Cross-provider team identity resolution (Volume 3 §4.0, team_provider_ids
table -- Phase 3E-3, 2026-08-13).

Mirrors `app/persistence/game_identity.py` exactly, deliberately -- same
problem (a single provider's own entity representation with no way for a
second vendor's representation to coexist), same fix (a general mapping
table with the same two-unique-constraint shape). SportsDataIO identifies
teams by abbreviation ("KC", "SEA"); The Odds API identifies them by full
name ("Kansas City Chiefs", "Seattle Seahawks") -- confirmed directly from
this project's own already-captured fixtures.

No fuzzy matching lives here or anywhere else in this module: a provider's
team representation either has an existing team_provider_ids row (resolves)
or it doesn't (absent from the result, caller decides what to do -- create
a mapping via a known/documented backfill, or treat as unresolved).
"""
from __future__ import annotations

import httpx


class TeamIdentityError(Exception):
    """Raised when a team_provider_ids read or write fails on Supabase's
    side -- same boundary distinction as GameIdentityError."""


async def resolve_team_ids(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    provider_team_ids: list[str],
) -> dict[str, str]:
    """Maps provider_team_id -> teams.id for the given provider_name. A
    provider team id with no matching mapping row is simply absent from
    the returned dict -- callers decide how to handle that, this function
    doesn't guess.
    """
    if not provider_team_ids:
        return {}
    response = await client.get(
        "/rest/v1/team_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "provider_team_id": f"in.({','.join(provider_team_ids)})",
            "select": "team_id,provider_team_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise TeamIdentityError(
            f"failed to resolve team ids for provider {provider_name}: "
            f"{response.status_code} {response.text}"
        )
    return {row["provider_team_id"]: row["team_id"] for row in response.json()}


async def link_provider_team_id(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    team_id: str,
    provider_name: str,
    provider_team_id: str,
) -> None:
    """Creates the (provider_name, provider_team_id) -> team_id mapping.
    Uses PostgREST upsert-on-conflict against the (team_id, provider_name)
    unique constraint, so re-linking an already-mapped team is idempotent
    rather than raising a duplicate-key error.
    """
    response = await client.post(
        "/rest/v1/team_provider_ids",
        params={"on_conflict": "team_id,provider_name"},
        json={
            "team_id": team_id,
            "provider_name": provider_name,
            "provider_team_id": provider_team_id,
        },
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201):
        raise TeamIdentityError(
            f"failed to link provider team id {provider_name}:{provider_team_id} "
            f"to team {team_id}: {response.status_code} {response.text}"
        )
