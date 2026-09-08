"""Persists season-aggregate TeamSeasonStatLine data into team_stats
(Volume 3 §4.0), keyed by (team_id, season_id) instead of (team_id,
game_id) -- Phase 8.3A (2026-09-08, MANSA HQ-authorized).

**Why a new function instead of extending `persist_team_stats`.** The one
confirmed-real MySportsFeeds stats source (team_stats_totals/standings) is
season-aggregate, not per-game (2026-09-08 Player/Team Performance Data
Audit). `team_stats.game_id` was widened nullable and a nullable
`season_id` added (`20260908160000_team_player_stats_season_scope.sql`)
specifically so this data can be persisted honestly, without fabricating a
game_id. A season-scoped row needs a different "latest row" lookup, keyed
by (team_id, season_id) rather than game_id -- the existing
`_latest_team_stats_row` in `team_stats.py` is game_id-keyed and stays
untouched, matching this arc's established "new function, don't overload
an existing one" pattern (`lineup_depth_ingestion.py` was kept separate
from `roster_ingestion.py` for the identical reason). Same idempotent,
correction-aware insert-only-if-different behavior as `persist_team_stats`
-- see that module's docstring for the full reasoning; `team_stats` is
DB-level append-only as of `20260818080000_team_stats_player_stats_append_
only.sql` (UPDATE blocked, INSERT unrestricted), so this function, like
its game-scoped sibling, only ever INSERTs.

`provider_name` is a required keyword, not a hardcoded module constant --
this function has no sportsdataio-era default to preserve (it is new),
so it does not repeat the hardcoded-provider gap flagged in
`team_stats.py`/`player_stats.py`'s own docstrings.

`season_id` is resolved by the caller, not this module -- with exactly two
real seasons in play for this activation pass (2025, 2026), a full
(league, year) -> season_id resolution helper would be unused generality;
kept out per this pass's "smallest execution" instruction. Add one if/when
a second real caller needs it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.persistence.team_identity import resolve_team_ids


class TeamSeasonStatsPersistenceError(Exception):
    """Raised when a normalized season stat line can't be written to
    Supabase -- same PersistenceError/ProviderError boundary distinction
    as every other persistence module in this codebase."""


@dataclass
class TeamSeasonStatLine:
    team: str
    """Provider-native team identifier (e.g. MySportsFeeds abbreviation
    'BUF'), resolved against team_provider_ids the same way every other
    persistence module in this codebase resolves provider identifiers."""
    stats: dict


@dataclass
class TeamSeasonStatsPersistResult:
    inserted: int = 0
    unchanged: int = 0
    unresolved_teams: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _latest_team_season_stats_row(
    client: httpx.AsyncClient, headers: dict, *, team_id: str, season_id: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/team_stats",
        params={
            "team_id": f"eq.{team_id}",
            "season_id": f"eq.{season_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise TeamSeasonStatsPersistenceError(
            f"failed to read latest team_stats for team {team_id}/season {season_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_team_season_stats(
    lines: list[TeamSeasonStatLine],
    *,
    season_id: str,
    provider_name: str,
) -> TeamSeasonStatsPersistResult:
    """Writes each TeamSeasonStatLine as a team_stats row scoped to
    `season_id` (game_id left null), but only when it differs from the
    existing latest row for that (team, season) pair. A line whose team
    can't be resolved via team_provider_ids is skipped and reported, never
    guessed."""
    if not lines:
        return TeamSeasonStatsPersistResult()

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        team_ids = await resolve_team_ids(
            client, headers, provider_name=provider_name,
            provider_team_ids=sorted({line.team for line in lines}),
        )

        result = TeamSeasonStatsPersistResult()
        for line in lines:
            team_id = team_ids.get(line.team)
            if team_id is None:
                result.unresolved_teams.append(line.team)
                continue

            latest = await _latest_team_season_stats_row(client, headers, team_id=team_id, season_id=season_id)
            if latest is not None and latest["stats"] == line.stats:
                result.unchanged += 1
                continue

            insert_response = await client.post(
                "/rest/v1/team_stats",
                json={"team_id": team_id, "season_id": season_id, "stats": line.stats},
                headers=headers,
            )
            if insert_response.status_code not in (200, 201):
                raise TeamSeasonStatsPersistenceError(
                    f"failed to insert team_stats for team {team_id}/season {season_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            result.inserted += 1

        return result
