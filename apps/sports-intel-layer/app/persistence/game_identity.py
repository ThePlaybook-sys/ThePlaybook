"""Cross-provider game identity resolution (Volume 3 §4.0, game_provider_ids table --
Phase 3E-1, Decision 2, 2026-08-13).

Replaces games.external_provider_id's hidden single-vendor assumption --
app/persistence/odds_snapshots.py used to resolve every game by matching that
one column against The Odds API's event id, with no way for a second vendor
(SportsDataIO's GameKey) to ever coexist. This module is the one place that
reads/writes game_provider_ids; every persistence module that needs to turn a
provider's own game id into games.id goes through it rather than querying
games directly.
"""
from __future__ import annotations

import httpx


class GameIdentityError(Exception):
    """Raised when a game_provider_ids read or write fails on Supabase's side --
    deliberately distinct from PersistenceError/ProviderError so callers can
    tell this is a resolution-layer failure, not their own write failing or
    the vendor failing."""


async def resolve_game_ids(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    provider_game_ids: list[str],
) -> dict[str, str]:
    """Maps provider_game_id -> games.id for the given provider_name. A
    provider id with no matching mapping row is simply absent from the
    returned dict -- callers decide how to handle that (skip it, create a
    new game), this function doesn't guess.
    """
    if not provider_game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{provider_name}",
            "provider_game_id": f"in.({','.join(provider_game_ids)})",
            "select": "game_id,provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GameIdentityError(
            f"failed to resolve game ids for provider {provider_name}: "
            f"{response.status_code} {response.text}"
        )
    return {row["provider_game_id"]: row["game_id"] for row in response.json()}


async def link_provider_id(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_name: str,
    provider_game_id: str,
) -> None:
    """Creates the (provider_name, provider_game_id) -> game_id mapping.
    Uses PostgREST upsert-on-conflict against the (game_id, provider_name)
    unique constraint, so re-linking an already-mapped game (e.g. re-running
    Schedule ingestion) is idempotent rather than raising a duplicate-key
    error -- it corrects the provider_game_id on that row instead.
    """
    response = await client.post(
        "/rest/v1/game_provider_ids",
        params={"on_conflict": "game_id,provider_name"},
        json={
            "game_id": game_id,
            "provider_name": provider_name,
            "provider_game_id": provider_game_id,
        },
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201):
        raise GameIdentityError(
            f"failed to link provider id {provider_name}:{provider_game_id} to "
            f"game {game_id}: {response.status_code} {response.text}"
        )
