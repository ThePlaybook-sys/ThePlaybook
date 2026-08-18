"""Read-only `games` queries Master Refresh needs beyond what
`app/persistence/schedule.py` already writes -- Phase 3E-2.

Deliberately read-only and separate from `schedule.py` (which owns
writes): these queries support REST computation and slate assembly,
neither of which creates or mutates a `games` row.
"""
from __future__ import annotations

from datetime import date, datetime

import httpx


class GamesQueryError(Exception):
    """Raised when a `games` read fails on Supabase's side."""


async def find_previous_final_game(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    team: str,
    before: datetime,
) -> dict | None:
    """Returns the most recent `status='final'` game (by `scheduled_start`)
    involving `team` (as either home or away) strictly before `before`, or
    None if no such game exists (season opener).

    Matches `team` by exact string equality against `home_team`/`away_team`
    -- the same known limitation flagged in the 3E-1/3E-2 planning (SportsDataIO's
    abbreviations vs. other sources' full names aren't reconciled here, per
    Mac's explicit instruction not to solve team identity in this pass).
    Since Master Refresh only ever writes SportsDataIO-sourced `games` rows,
    this resolves correctly for games Master Refresh itself created; it is
    not guaranteed to bridge across differently-sourced historical rows
    (e.g. the pre-3E-1 seed data's full team names).
    """
    response = await client.get(
        "/rest/v1/games",
        params={
            "status": "eq.final",
            "or": f"(home_team.eq.{team},away_team.eq.{team})",
            "scheduled_start": f"lt.{before.isoformat()}",
            "select": "id,home_team,away_team,scheduled_start,status",
            "order": "scheduled_start.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesQueryError(
            f"failed to find previous final game for {team!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def list_games_in_window(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    start: date,
    end: date,
) -> list[dict]:
    """Returns every `games` row with `scheduled_start` in [start, end)
    (UTC calendar dates) -- Master Refresh's slate for a given run, read
    back after `schedule.py` has already upserted the day's Schedule.
    """
    response = await client.get(
        "/rest/v1/games",
        params={
            "scheduled_start": [f"gte.{start.isoformat()}", f"lt.{end.isoformat()}"],
            "select": (
                "id,external_provider_id,home_team,away_team,scheduled_start,stadium,status,"
                "season_type,week,venue_lat,venue_long,venue_type"
            ),
            "order": "scheduled_start.asc",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GamesQueryError(
            f"failed to list games in window {start}-{end}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()
