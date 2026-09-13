"""MySportsFeeds `game_boxscore` adapter (MANSA Phase 8 Player-Game
Persistence Design + Implementation Pass, 2026-09-10, HQ-authorized).

Parses MySportsFeeds' real `games/{id}/boxscore.json` response (the exact
shape Gate B confirmed live -- HTTP 200, game 163541, NE @ SEA,
`playedStatus: "COMPLETED"`, 34 away + 35 home real player entries; see
`docs/ops/phase-8-gate-b-player-game-persistence-2026-09-10.md` and the
committed fixture `docs/ops/fixtures/gate-b-msf-game-boxscore-163541-
2026-09-10.json`) into provider-neutral `PlayerStatLine` objects.

**This is a PURE PARSING function -- no network I/O, no live client.**
Per this pass's explicit "no new provider calls" instruction, this module
only ever transforms an already-fetched payload (dict in, `AdapterResponse`
out). A live-fetching wrapper (mirroring `MySportsFeedsPlayerSeasonStatsAdapter`'s
`fetch_*` pattern) is a separate, later, explicitly-authorized pass -- not
built here.

**This is the only place in the codebase that knows MySportsFeeds'
`game_boxscore` response shape.** Everything downstream (persistence,
tests) only ever sees provider-neutral `PlayerStatLine` objects, matching
every other adapter in this project.

## Real shape, as Gate B actually observed it (not SDK-inferred)

```
{
  "game": {"id": 163541, "awayTeam": {"id": 50, "abbreviation": "NE"},
            "homeTeam": {"id": 79, "abbreviation": "SEA"},
            "playedStatus": "COMPLETED", ...},
  "stats": {
    "away": {"players": [{"player": {"id", "firstName", "lastName",
                                       "position", "jerseyNumber"},
                            "playerStats": [{...category dicts...}]}, ...],
              "teamStats": [...]},
    "home": {...same shape...}
  },
  "scoring": {"awayScoreTotal": 10, "homeScoreTotal": 13, ...},
  "lastUpdatedOn": "2026-09-10T12:45:08.670Z"
}
```

Each player's real per-category stat groups (Gate B's real observation,
all 69 players): `fumbles`, `passing`, `rushing`, `receiving`, `tackles`,
`interceptions`, `kickoffReturns`, `puntReturns`, `fieldGoals`, `punting`,
`kickoffs`, `extraPointAttempt`, `twoPointAttempts`, `miscellaneous`,
`snapCounts`. The entire per-player stats block passes through into
`PlayerStatLine.stats` verbatim, unreshaped, unfiltered -- matching every
other stats adapter in this project (`MySportsFeedsPlayerSeasonStatsAdapter`,
`SportsDataIOPlayerStatsAdapter`).

## `snapCounts` / `miscellaneous.gamesStarted` -- confirmed unreliable in
## this real capture, disclosed structurally, never silently dropped

Gate B's real payload showed `snapCounts.{offenseSnaps,defenseSnaps,
specialTeamSnaps}` and `miscellaneous.gamesStarted` as **uniformly zero
across all 69 players and both team totals** -- including players with
real, substantial, non-zero performance in the same payload (e.g. Drake
Maye: 178 pass yards, 47 rush yards, yet 0 offense snaps). This is the
same pattern `MySportsFeedsPlayerSeasonStatsAdapter` already disclosed for
`gamesStarted` in a different MSF feed (Phase 8.3C) -- schema-present,
but not populated at this tier/endpoint, not a real zero-usage signal.

Per HQ's explicit instruction ("do not convert zero-valued provider
placeholders into evidence of zero usage"), this adapter does NOT strip,
zero-out, or silently trust these fields -- the raw values pass through
completely untouched (provenance-preserving), but each persisted
`stats` dict gets one additional, MANSA-authored sibling key,
`_unreliable_fields`, naming exactly which dotted paths are known
unreliable in this capture and why. This is a structural, machine-checkable
disclosure -- any future reader (a Context Intelligence dimension, a
report, a test) can check for this key rather than relying on someone
remembering a docstring warning. The key is prefixed with `_` so it can
never collide with a real MySportsFeeds stat-category name (none of which
start with `_`).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.adapters.models import AdapterResponse, PlayerStatLine

_logger = logging.getLogger(__name__)

PROVIDER_NAME = "mysportsfeeds"

#: Dotted paths within a player's raw stats block that Gate B's real
#: capture confirmed are schema-present but not reliably populated at
#: this tier -- see module docstring. Never removed from the persisted
#: stats dict, only flagged.
UNRELIABLE_FIELD_PATHS = ["snapCounts", "miscellaneous.gamesStarted"]

_UNRELIABLE_FIELDS_REASON = (
    "Gate B (2026-09-10, game 163541) observed these fields as uniformly "
    "zero across all 69 players and both team totals in a real completed-"
    "game payload, including players with substantial non-zero performance "
    "elsewhere in the same response. Schema-present, not confirmed real "
    "participation data at this tier -- do not treat as evidence of zero "
    "usage or as a reliable participation signal."
)


def _sided_players(payload: dict[str, Any]) -> list[tuple[dict[str, Any], str, str | None]]:
    """Returns (player_entry, team_abbreviation, team_provider_id) triples
    for both sides. Neither identifier lives on the player entry itself
    (confirmed directly against the real Gate B payload -- a player
    object carries only `id`/`firstName`/`lastName`/`position`/
    `jerseyNumber`, no team field of any kind); every player's team
    identity is entirely determined by which side array
    (`stats.away.players` vs `stats.home.players`) it sits in, so both
    identifiers are attached here, once per side, from `game.{away,home}Team`.

    `team_abbreviation` (`game.{away,home}Team.abbreviation`, e.g. "NE") --
    supporting/consistency evidence only as of the Pre-Live Worker
    Hardening pass (2026-09-13); no longer the primary identity path (see
    that pass's own report for why: only 12/32 teams ever had an
    abbreviation-scheme `mysportsfeeds` `team_provider_ids` row, so
    resolving through it required a piecemeal per-team backfill).

    `team_provider_id` (`game.{away,home}Team.id`, e.g. 50 -- stringified,
    `None` only if genuinely absent from the payload) -- the PRIMARY team
    identity path as of the same pass. Real, numeric, and now backed by a
    complete 32-team `team_provider_ids` mapping (Sunday Ingestion
    Foundation Build, 2026-09-11) -- safe to trust as primary evidence in
    a way the abbreviation scheme's 12/32 partial coverage never was."""
    game = payload.get("game", {})
    away_team = game.get("awayTeam", {}) or {}
    home_team = game.get("homeTeam", {}) or {}
    away_abbr = away_team.get("abbreviation")
    home_abbr = home_team.get("abbreviation")
    away_provider_team_id = str(away_team["id"]) if away_team.get("id") is not None else None
    home_provider_team_id = str(home_team["id"]) if home_team.get("id") is not None else None
    stats = payload.get("stats", {})
    away_players = stats.get("away", {}).get("players", []) or []
    home_players = stats.get("home", {}).get("players", []) or []
    return [(p, away_abbr, away_provider_team_id) for p in away_players] + [
        (p, home_abbr, home_provider_team_id) for p in home_players
    ]


def _with_unreliable_marker(raw_stats: dict[str, Any]) -> dict[str, Any]:
    """Every real MySportsFeeds field is preserved verbatim; only a new
    MANSA-authored `_unreliable_fields`/`_unreliable_fields_reason` sibling
    key is added -- never a mutation of any real provider value."""
    return {
        **raw_stats,
        "_unreliable_fields": UNRELIABLE_FIELD_PATHS,
        "_unreliable_fields_reason": _UNRELIABLE_FIELDS_REASON,
    }


def parse_game_boxscore(payload: dict[str, Any]) -> AdapterResponse[list[PlayerStatLine]]:
    """Parses one real MySportsFeeds `game_boxscore` response body into
    provider-neutral `PlayerStatLine` objects, one per player who has a
    real `playerStats` entry. A malformed/missing player row is skipped
    and logged, never guessed -- matching every other stats adapter in
    this project. `provider_reported_at` is MySportsFeeds' own
    `lastUpdatedOn` field, parsed if present, never fabricated if absent
    or unparseable."""
    lines: list[PlayerStatLine] = []
    for entry, team, provider_team_id in _sided_players(payload):
        try:
            player = entry["player"]
            provider_player_id = str(player["id"])
            player_name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
            # Real provider-reported position (Phase 8 Automatic Player
            # Identity pass, 2026-09-11 -- see PlayerStatLine.position's
            # own docstring). Confirmed present directly on Gate B's real
            # `player` object (e.g. {"id": 166956, ..., "position": "LS"}),
            # never nested, never guessed when a row genuinely lacks it.
            position = player.get("position")
            stat_blocks = entry["playerStats"]
            if not isinstance(stat_blocks, list) or not stat_blocks:
                raise TypeError("playerStats was empty or not a list")
            raw_stats = stat_blocks[0]
            if not isinstance(raw_stats, dict):
                raise TypeError("playerStats[0] was not an object")
        except (KeyError, TypeError, IndexError) as exc:
            _logger.warning(
                "skipping malformed mysportsfeeds game_boxscore player row (id=%r): %s",
                entry.get("player", {}).get("id") if isinstance(entry.get("player"), dict) else None,
                exc,
            )
            continue

        lines.append(
            PlayerStatLine(
                game_external_id=str(payload["game"]["id"]),
                player_external_id=provider_player_id,
                player_name=player_name,
                team=team or "",
                stats=_with_unreliable_marker(raw_stats),
                position=position if isinstance(position, str) and position else None,
                provider_team_id=provider_team_id,
            )
        )

    last_updated_on = payload.get("lastUpdatedOn")
    provider_reported_at = None
    if isinstance(last_updated_on, str):
        try:
            provider_reported_at = datetime.fromisoformat(last_updated_on.replace("Z", "+00:00"))
        except ValueError:
            # Never fabricated -- an unparseable timestamp stays None.
            provider_reported_at = None

    return AdapterResponse(value=lines, source=PROVIDER_NAME, provider_reported_at=provider_reported_at)


__all__ = ["PROVIDER_NAME", "UNRELIABLE_FIELD_PATHS", "parse_game_boxscore"]
