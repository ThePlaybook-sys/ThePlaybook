"""Cross-provider player identity resolution (Volume 3 §4.0, player_provider_ids
table -- Phase 3E-8, Decision 1, Option B, 2026-08-18).

Mirrors `app/persistence/team_identity.py`/`app/persistence/game_identity.py`
exactly, deliberately -- same problem (`players.external_provider_id` is a
single bare column with no way for a second vendor's own player
representation to coexist), same fix (a general mapping table with the same
two-unique-constraint shape).

No fuzzy matching lives here or anywhere else in this module: a provider's
player representation either has an existing player_provider_ids row
(resolves) or it doesn't (absent from the result, caller decides what to do
-- create a mapping via a known/documented backfill, or treat as unresolved).

Unlike team_identity.py, this module also owns *creating* `players` rows
(`ensure_player`) -- the `players` table itself was never populated by any
existing code before this phase (Roster data only ever landed in
`daily_game_intelligence.players`, a jsonb working field, never normalized
rows), so there is no pre-existing row for a provider mapping to attach to
the way there was for `teams`.
"""
from __future__ import annotations

import httpx


class PlayerIdentityError(Exception):
    """Raised when a players/player_provider_ids read or write fails on
    Supabase's side -- same boundary distinction as TeamIdentityError/
    GameIdentityError."""


async def resolve_player_ids(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    provider_player_ids: list[str],
) -> dict[str, str]:
    """Maps provider_player_id -> players.id for the given provider_name. A
    provider player id with no matching mapping row is simply absent from
    the returned dict -- callers decide how to handle that, this function
    doesn't guess.
    """
    if not provider_player_ids:
        return {}
    response = await client.get(
        "/rest/v1/player_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "provider_player_id": f"in.({','.join(provider_player_ids)})",
            "select": "player_id,provider_player_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PlayerIdentityError(
            f"failed to resolve player ids for provider {provider_name}: "
            f"{response.status_code} {response.text}"
        )
    return {row["provider_player_id"]: row["player_id"] for row in response.json()}


async def link_provider_player_id(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    player_id: str,
    provider_name: str,
    provider_player_id: str,
) -> None:
    """Creates the (provider_name, provider_player_id) -> player_id mapping.
    Uses PostgREST upsert-on-conflict against the (player_id, provider_name)
    unique constraint, so re-linking an already-mapped player is idempotent
    rather than raising a duplicate-key error.
    """
    response = await client.post(
        "/rest/v1/player_provider_ids",
        params={"on_conflict": "player_id,provider_name"},
        json={
            "player_id": player_id,
            "provider_name": provider_name,
            "provider_player_id": provider_player_id,
        },
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201):
        raise PlayerIdentityError(
            f"failed to link provider player id {provider_name}:{provider_player_id} "
            f"to player {player_id}: {response.status_code} {response.text}"
        )


async def ensure_player(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    provider_player_id: str,
    name: str,
    team_id: str | None,
    position: str | None,
) -> str:
    """Returns the internal players.id for (provider_name, provider_player_id),
    creating both the players row and its player_provider_ids mapping on
    first sight. Idempotent: a second call with the same provider identity
    resolves to the same players.id without creating a duplicate row --
    this is the one place a fresh player enters the system, always through
    an explicit provider identity, never through name-matching alone.
    """
    existing = await resolve_player_ids(
        client, headers, provider_name=provider_name, provider_player_ids=[provider_player_id]
    )
    player_id = existing.get(provider_player_id)
    if player_id is not None:
        return player_id

    insert_response = await client.post(
        "/rest/v1/players",
        json={"name": name, "team_id": team_id, "position": position},
        headers={**headers, "Prefer": "return=representation"},
    )
    if insert_response.status_code not in (200, 201):
        raise PlayerIdentityError(
            f"failed to create player {name!r}: {insert_response.status_code} {insert_response.text}"
        )
    new_player_id = insert_response.json()[0]["id"]

    await link_provider_player_id(
        client,
        headers,
        player_id=new_player_id,
        provider_name=provider_name,
        provider_player_id=provider_player_id,
    )
    return new_player_id
