"""Explicit, fixture-backed player-identity backfill (Phase 3E-8, Decision 1).

**Not a runtime fuzzy-matching mechanism**, same discipline as
`team_backfill.py`'s `TEAM_BACKFILL`: `PLAYER_BACKFILL` is a static,
manually-curated list -- the single place a provider's player representation
is decided, so no worker ever normalizes player names/ids ad hoc.

**Provenance discipline, identical bar to `team_backfill.py`'s 3E-4A
tightening: every entry here is confirmed by a direct read of this
repository's own already-captured SportsDataIO fixtures -- never filled in
from general/public NFL knowledge, even where well-known.** No live provider
call was made or is authorized for this phase (Mac's explicit instruction).

**Coverage is small and explicitly incomplete -- reported, not hidden.**
Exactly four real players have ever been captured by this project, across
two fixture files:
  - `rosters_normal.json` (2 rows, both Kansas City Chiefs)
  - `player_stats_week_bulk_normal.json` (2 rows, one Buffalo Bills, one
    New England Patriots -- from two different games, neither of which
    overlaps the games in `team_stats_week_bulk_normal.json`)
This is the entire universe of real player identity evidence available
without a live call. `PLAYER_BACKFILL` contains exactly these four --
nothing more. Every other player any future real PlayerGameStatsByWeek
response returns will have no `player_provider_ids` mapping yet, and
`resolve_player_ids`/`ensure_player`'s existing "absent means unresolved,
never guessed" behavior handles that correctly -- see Postgame Worker's own
module docstring for how an unresolved player is surfaced, not silently
dropped or fabricated.
"""
from __future__ import annotations

import httpx

from app.persistence.player_identity import ensure_player
from app.persistence.team_identity import resolve_team_ids

#: Every entry confirmed via direct read of tests/fixtures/sportsdataio/
#: rosters_normal.json and player_stats_week_bulk_normal.json -- PlayerID,
#: Name, Team, Position all taken verbatim from those captures.
PLAYER_BACKFILL: list[dict] = [
    {
        "provider_player_id": "24924",
        "name": "Xavier Worthy",
        "team_abbrev": "KC",
        "position": "WR",
    },
    {
        "provider_player_id": "17958",
        "name": "Emmanuel Ogbah",
        "team_abbrev": "KC",
        "position": "DL",
    },
    {
        "provider_player_id": "19801",
        "name": "Josh Allen",
        "team_abbrev": "BUF",
        "position": "QB",
    },
    {
        "provider_player_id": "19862",
        "name": "Harold Landry III",
        "team_abbrev": "NE",
        "position": "LB",
    },
]

_PROVIDER_NAME = "sportsdataio"


async def backfill_known_players(client: httpx.AsyncClient, headers: dict) -> int:
    """Creates/links every player in PLAYER_BACKFILL. Idempotent (via
    `ensure_player`'s resolve-before-create) -- safe to call more than once.
    Returns the number of players created-or-confirmed.
    """
    team_abbrevs = sorted({entry["team_abbrev"] for entry in PLAYER_BACKFILL})
    team_ids = await resolve_team_ids(
        client, headers, provider_name=_PROVIDER_NAME, provider_team_ids=team_abbrevs
    )

    count = 0
    for entry in PLAYER_BACKFILL:
        team_id = team_ids.get(entry["team_abbrev"])
        await ensure_player(
            client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_player_id=entry["provider_player_id"],
            name=entry["name"],
            team_id=team_id,
            position=entry["position"],
        )
        count += 1
    return count
