"""Read-only "latest snapshot" queries against the append-only category
tables (Volume 3 §4) -- Phase 3E-2.

Master Refresh reads these to assemble `daily_game_intelligence`'s
odds/injuries/weather fields without ever calling the corresponding
provider adapter itself (Decision 1, 2026-08-13): those categories remain
owned by their specialized workers, which write these tables. A category
with no row yet (the specialized worker hasn't run) is a legitimate,
expected "unavailable" result, not an error -- callers get `None` back,
never a fabricated zero/neutral value.

`news` deliberately has no equivalent here: Volume 3 defines no
`news_snapshots`-style history table (confirmed by direct inspection --
`news` exists only as `daily_game_intelligence.news` jsonb). See
`app/persistence/daily_game_intelligence.py` for how that asymmetry is
handled during assembly.
"""
from __future__ import annotations

import httpx


class SnapshotQueryError(Exception):
    """Raised when a snapshot-table read fails on Supabase's side."""


async def _latest_row(
    client: httpx.AsyncClient, headers: dict, *, table: str, game_id: str, extra_params: dict | None = None
) -> dict | None:
    params = {
        "game_id": f"eq.{game_id}",
        "select": "*",
        "order": "captured_at.desc",
        "limit": "1",
    }
    if extra_params:
        params.update(extra_params)
    response = await client.get(f"/rest/v1/{table}", params=params, headers=headers)
    if response.status_code != 200:
        raise SnapshotQueryError(
            f"failed to read latest {table} for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def latest_odds_line(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    """Latest non-prop line (moneyline/spread/total) -- distinct from
    `latest_prop_line`, since both share the `odds_snapshots` table and
    are only distinguished by `market_type`."""
    return await _latest_row(
        client, headers, table="odds_snapshots", game_id=game_id, extra_params={"market_type": "neq.prop"}
    )


async def latest_prop_line(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    return await _latest_row(
        client, headers, table="odds_snapshots", game_id=game_id, extra_params={"market_type": "eq.prop"}
    )


async def latest_injury_report(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    return await _latest_row(client, headers, table="injury_reports", game_id=game_id)


async def latest_weather_snapshot(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    return await _latest_row(client, headers, table="weather_snapshots", game_id=game_id)
