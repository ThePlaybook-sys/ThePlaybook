"""Read-only `odds_snapshots` access (Milestone 4.5). Duplicated rather
than imported from `sports-intel-layer`'s own `odds_snapshots.py`, per
this repo's established convention (separate deployable services, no
shared package) -- but this reader is keyed by the internal `game_id`
directly (confirmed live: `odds_snapshots.game_id` is already FK'd to
`games.id`, not a provider-external id), so unlike sports-intel-layer's
`read_latest_odds_snapshots` it needs no `game_provider_ids` resolution
step.

Returns *all* snapshots for a game, ordered by `captured_at` ascending --
not just the latest one (`daily_game_intelligence.odds` already carries a
single latest snapshot; this reader exists specifically because line
movement needs the full history DGI does not carry)."""
from __future__ import annotations

import httpx


class OddsSnapshotsReadError(Exception):
    """Raised when an `odds_snapshots` read fails on Supabase's side."""


async def read_odds_snapshots(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> list[dict]:
    """Reads every `odds_snapshots` row for `game_id`, ordered by
    `captured_at` ascending. Returns `[]` when no snapshots exist --
    never `None`, so callers can distinguish "no odds history at all"
    (empty list here) from other failure modes (raised exception)."""
    response = await client.get(
        "/rest/v1/odds_snapshots",
        params={
            "game_id": f"eq.{game_id}",
            "select": "sportsbook,market_type,line_data,captured_at",
            "order": "captured_at.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise OddsSnapshotsReadError(
            f"failed to read odds_snapshots for game_id={game_id!r}: {response.status_code} {response.text}"
        )
    return response.json()
