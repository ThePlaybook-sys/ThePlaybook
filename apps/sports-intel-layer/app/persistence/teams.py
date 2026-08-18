"""Read-only `teams` lookup the News Worker needs (Phase 3E-7): team_id ->
canonical `teams.name`.

A different lookup direction from `team_identity.py` (which resolves a
*provider's* team representation, e.g. SportsDataIO's `"KC"`, to our own
`teams.id`) -- this resolves our own `teams.id` to the human-readable
canonical name (`"Kansas City Chiefs"`) that `NewsAdapter.fetch_news`'s
`team` parameter expects, since NewsAPI's query string has no use for an
internal uuid or a vendor abbreviation. Neither existing team module
performs this direction, so it gets its own small function rather than
being bolted onto either.
"""
from __future__ import annotations

import httpx


class TeamsQueryError(Exception):
    """Raised when a `teams` read fails on Supabase's side."""


async def list_teams_by_id(
    client: httpx.AsyncClient, headers: dict, *, team_ids: list[str]
) -> dict[str, str]:
    """Maps teams.id -> teams.name for the given ids. A team id with no
    matching row is simply absent from the returned dict -- callers decide
    how to handle that, this function doesn't guess."""
    if not team_ids:
        return {}
    response = await client.get(
        "/rest/v1/teams",
        params={
            "id": f"in.({','.join(team_ids)})",
            "select": "id,name",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise TeamsQueryError(
            f"failed to list teams by id: {response.status_code} {response.text}"
        )
    return {row["id"]: row["name"] for row in response.json()}
