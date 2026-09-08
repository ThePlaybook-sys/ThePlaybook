"""Read-only access for the Phase 8.1 Contextual Intelligence Foundation
Pass (2026-09-08), new and additive -- does not modify or import from
any Phase 4/Milestone 7.1 persistence module, only sits alongside them.
Mirrors this package's own established convention exactly (injected
`httpx.AsyncClient` + headers, no self-contained client construction,
raised exceptions rather than swallowed failures, `[]`/`None` for "really
nothing here" vs. a raised exception for a real read failure).

**Table-wide reads, not per-game.** Unlike `odds_snapshots.py`/
`market_integrity.py`'s per-game readers, this module's job is building
the CROSS-GAME comparable pools this pass's "comparable historical
context" instruction requires -- `read_all_weather_snapshots`/
`read_all_odds_snapshots` fetch every row in the table, matching
`app.persistence.market_integrity.read_news_article_history_for_teams`'s
own established precedent for this project's real current scale (a
handful of real rows per table -- 2026-09-07's Phase 8.0.5 closeout
confirmed 4 real weather rows, 138 odds rows, 97 news rows; fetching all
and filtering/grouping in Python is simple, honest, and correct at this
volume, the same reasoning that precedent's own module docstring already
gives)."""
from __future__ import annotations

import httpx


class ContextIntelligenceReadError(Exception):
    """Raised when a context-intelligence read fails on Supabase's side."""


async def read_all_weather_snapshots(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `weather_snapshots` row in the table (`game_id`,
    `weather_data`, `captured_at`), oldest first. Real scale today: a
    handful of rows (Phase 8.0.5's own live-verified count). Callers are
    responsible for filtering to rows carrying `weather_data.source ==
    "weatherapi"` -- the one real, disclosed marker (Phase 8.0.5 Weather
    Activation) that distinguishes a real captured observation from the
    one pre-existing fixture row, which carries no `source` key at all."""
    response = await client.get(
        "/rest/v1/weather_snapshots",
        params={"select": "game_id,weather_data,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read weather_snapshots: {response.status_code} {response.text}")
    return response.json()


async def read_all_odds_snapshots(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Every `odds_snapshots` row in the table (`game_id`, `sportsbook`,
    `market_type`, `line_data`, `captured_at`), oldest first. Used to
    build the cross-game comparable pool for market-movement similarity
    -- the target game's own history is read via the existing
    `app.persistence.odds_snapshots.read_odds_snapshots` (Milestone 4.5),
    unchanged, not duplicated here."""
    response = await client.get(
        "/rest/v1/odds_snapshots",
        params={"select": "game_id,sportsbook,market_type,line_data,captured_at", "order": "captured_at.asc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read odds_snapshots: {response.status_code} {response.text}")
    return response.json()


async def read_game_venue_context(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> dict | None:
    """Reads the one `games` row this pass's venue dimension needs
    (`id`, `home_team`, `away_team`, `scheduled_start`, `venue_id`,
    `venue_lat`, `venue_long`, `venue_type`, `stadium`). A separate,
    dedicated read rather than widening `app.persistence.games.get_game`
    (Phase 4, Milestone 4.1/4.4, frozen) -- mirrors that same package's
    own `get_game_for_grading` precedent: "grading is a new, unrelated
    consumer with its own field needs," applied identically here. Returns
    `None` when no row exists."""
    response = await client.get(
        "/rest/v1/games",
        params={
            "id": f"eq.{game_id}",
            "select": "id,home_team,away_team,scheduled_start,venue_id,venue_lat,venue_long,venue_type,stadium",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read game {game_id!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def read_venue(client: httpx.AsyncClient, headers: dict, *, venue_id: str) -> dict | None:
    """Reads one canonical `venues` row (sport-agnostic since Phase
    8.0.5 Pass 2 -- reused here with zero redesign, per this pass's own
    multi-sport architecture rule). Returns `None` when no row exists."""
    response = await client.get(
        "/rest/v1/venues",
        params={"id": f"eq.{venue_id}", "select": "id,name,city,state,venue_type"},
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(f"failed to read venue {venue_id!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def read_games_sharing_venue(
    client: httpx.AsyncClient, headers: dict, *, venue_id: str, exclude_game_id: str
) -> list[dict]:
    """Every OTHER real `games` row (`id`, `scheduled_start`) sharing
    `venue_id` -- the venue dimension's own comparable-sample-size
    signal ("how many other tracked games do we have real data for at
    this exact venue"). Returns `[]` when none exist."""
    response = await client.get(
        "/rest/v1/games",
        params={
            "venue_id": f"eq.{venue_id}",
            "id": f"neq.{exclude_game_id}",
            "select": "id,scheduled_start",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ContextIntelligenceReadError(
            f"failed to read games sharing venue_id={venue_id!r}: {response.status_code} {response.text}"
        )
    return response.json()


__all__ = [
    "ContextIntelligenceReadError",
    "read_all_weather_snapshots",
    "read_all_odds_snapshots",
    "read_game_venue_context",
    "read_venue",
    "read_games_sharing_venue",
]
