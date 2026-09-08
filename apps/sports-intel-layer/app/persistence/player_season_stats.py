"""Persists season-aggregate PlayerSeasonStatLine data into player_stats
(Volume 3 §4.0), keyed by (player_id, season_id) instead of (player_id,
game_id) -- Phase 8.3D (2026-09-08, MANSA HQ-authorized).

**Provider-neutral, sport-agnostic by design.** This module knows nothing
about MySportsFeeds, NFL, or any specific stat category -- `stats` is an
opaque jsonb blob, preserved exactly as the caller supplies it, the same
"common cross-sport fields only... not a typed per-field model" contract
`TeamStatLine`/`PlayerStatLine` already establish in `app.adapters.
models`. A MySportsFeeds-specific *adapter* (`app.adapters.providers.
mysportsfeeds.MySportsFeedsPlayerSeasonStatsAdapter`) is the only place
that knows the real MSF response shape and produces `PlayerSeasonStatLine`
objects from it; a future NBA/other-sport/other-provider adapter would
produce the exact same `PlayerSeasonStatLine` shape from its own payload
and this function would not need to change at all.

**Why a new function instead of extending `persist_player_stats`.** The
real, confirmed MySportsFeeds `player_stats_totals` feed (Phase 8.3C,
2026-09-08 diagnostic: HTTP 200, real per-player passing/rushing/
receiving/defense/kicking/punting/returns/participation data) is
season-aggregate, not per-game -- the same schema mismatch Phase 8.3A
already resolved for `team_stats` by widening `game_id` nullable and
adding a nullable `season_id` (`20260908160000_team_player_stats_season_
scope.sql`). **That same migration already widened `player_stats`
identically** (confirmed by direct schema inspection before writing this
module: `player_stats.game_id` nullable, `player_stats.season_id` present,
FK to `seasons`) -- no new migration is needed for this pass. A
season-scoped row needs a different "latest row" lookup, keyed by
(player_id, season_id) rather than game_id -- the existing
`_latest_player_stats_row` in `player_stats.py` is game_id-keyed and
stays untouched, matching this arc's established "new function, don't
overload an existing one" pattern (`team_season_stats.py` was kept
separate from `team_stats.py` for the identical reason one pass ago).

**Identity resolution never creates a player, matching `persist_player_
stats`'s own existing, deliberate precedent** (see that module's
docstring) and HQ's explicit instruction this pass: "Identity resolution
must use canonical player identity and player_provider_ids. Never join
by player name." `resolve_player_ids` is read-only against
`player_provider_ids` -- a stat line whose player has no existing
mapping is reported as unresolved, never guessed, never auto-created
here. Player identity creation stays `roster_ingestion.ensure_player`'s
job alone, keeping "who is this player" and "what did they do this
season" as separate concerns, matching this whole arc's own repeated
architecture rule.

**Historical truth preserved, idempotency explicit.** Same idempotent,
correction-aware insert-only-if-different behavior as every other
snapshot-style persistence module in this codebase: a first observation
for a (player, season) pair always inserts; an identical re-ingestion
inserts nothing; a genuine correction (the incoming stats differ from
the latest existing row) inserts a NEW row, leaving every prior
observation untouched and queryable via `created_at` ordering -- this
function only ever INSERTs, matching `player_stats`'s own DB-level
append-only trigger (`block_snapshot_updates()`, live since
`20260818080000_team_stats_player_stats_append_only.sql`, blocks UPDATE
unconditionally).

**`gamesStarted` is provider data, not MANSA-verified participation
evidence.** Phase 8.3C's real capture showed `stats.miscellaneous.
gamesStarted` returning `0` for every one of 43 real players sampled,
including obvious starters -- this function does not filter, correct,
or specially interpret that field in any way (the whole `stats` blob is
opaque and passed through verbatim, same as every other field), and
nothing here or anywhere else in this codebase treats it as a trustworthy
participation signal. See the module docstring on
`MySportsFeedsPlayerSeasonStatsAdapter` for the full disclosure.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.persistence.player_identity import resolve_player_ids


class PlayerSeasonStatsPersistenceError(Exception):
    """Raised when a normalized season stat line can't be written to
    Supabase -- same PersistenceError/ProviderError boundary distinction
    as every other persistence module in this codebase."""


@dataclass
class PlayerSeasonStatLine:
    player: str
    """Provider-native player identifier (e.g. MySportsFeeds numeric
    player id, as a string), resolved against player_provider_ids the
    same way every other persistence module in this codebase resolves
    provider identifiers. Deliberately not typed to any one provider's
    id format (int vs. string vs. slug) -- callers pass whatever their
    own adapter's provider_player_id convention already is."""
    stats: dict
    """Opaque, provider-native stats payload -- preserved verbatim, never
    renamed/reshaped/filtered field-by-field. Sport- and provider-
    specific structure lives entirely inside this dict; nothing in this
    persistence layer inspects or depends on its internal shape."""


@dataclass
class PlayerSeasonStatsPersistResult:
    inserted: int = 0
    unchanged: int = 0
    unresolved_players: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _latest_player_season_stats_row(
    client: httpx.AsyncClient, headers: dict, *, player_id: str, season_id: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/player_stats",
        params={
            "player_id": f"eq.{player_id}",
            "season_id": f"eq.{season_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PlayerSeasonStatsPersistenceError(
            f"failed to read latest player_stats for player {player_id}/season {season_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_player_season_stats(
    lines: list[PlayerSeasonStatLine],
    *,
    season_id: str,
    provider_name: str,
) -> PlayerSeasonStatsPersistResult:
    """Writes each PlayerSeasonStatLine as a player_stats row scoped to
    `season_id` (game_id left null), but only when it differs from the
    existing latest row for that (player, season) pair. A line whose
    player can't be resolved via player_provider_ids is skipped and
    reported, never guessed, never auto-created."""
    if not lines:
        return PlayerSeasonStatsPersistResult()

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        player_ids = await resolve_player_ids(
            client, headers, provider_name=provider_name,
            provider_player_ids=sorted({line.player for line in lines}),
        )

        result = PlayerSeasonStatsPersistResult()
        for line in lines:
            player_id = player_ids.get(line.player)
            if player_id is None:
                result.unresolved_players.append(line.player)
                continue

            latest = await _latest_player_season_stats_row(
                client, headers, player_id=player_id, season_id=season_id
            )
            if latest is not None and latest["stats"] == line.stats:
                result.unchanged += 1
                continue

            insert_response = await client.post(
                "/rest/v1/player_stats",
                json={"player_id": player_id, "season_id": season_id, "stats": line.stats},
                headers=headers,
            )
            if insert_response.status_code not in (200, 201):
                raise PlayerSeasonStatsPersistenceError(
                    f"failed to insert player_stats for player {player_id}/season {season_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            result.inserted += 1

        return result
