"""Persists normalized TeamStatLine data into team_stats (Volume 3 §4.0,
Phase 3E-8) -- the persistence half of the Postgame Ingestion Worker's
"final team stats" responsibility.

**Idempotent, correction-aware persistence -- a real design decision, not
inherited unchanged from odds_snapshots/injury_reports/weather_snapshots.**
Those three tables are strict append-only: every poll writes a new row,
even if nothing changed, enforced by a DB-level trigger
(`block_*_updates`). `team_stats` has neither a uniqueness constraint nor
that trigger (confirmed by direct inspection of the Phase 1 migration
before writing this) -- Volume 3 §6's own text already flags this as an
unclosed gap ("Rule 4 is a real, unclosed gap... no append-only/versioning
pattern"). Blindly reusing the append-on-every-poll convention here would
mean Postgame Worker's bounded reconciliation checks (Decision 5, up to 6
checks per game) insert up to 6x duplicate rows per game/team even when
nothing corrected.

**Decision made here, flagged in the 3E-8 completion report rather than
silently invented: insert a new row only when the incoming stats differ
from the existing latest row for that (game, team) pair.** "Latest" is
determined the same way `app.persistence.snapshots._latest_row` already
determines it everywhere else in this codebase -- `order by created_at
desc limit 1` -- reusing an already-established read pattern, not
inventing a new one. This gives exactly the three properties requested:
the first fetch always inserts (no prior row); a reconciliation check that
finds no change inserts nothing (no uncontrolled duplicates); a
reconciliation check that finds a real correction inserts a new row,
preserving the previous one untouched (historical correction capability,
reconstructible via `created_at` ordering). No new columns, no migration.

**Available future hardening, explicitly not applied now:** a DB-level
append-only trigger (reusing the *already-existing* `block_snapshot_updates()`
function odds_snapshots/injury_reports/weather_snapshots already use) would
make "no UPDATE, only INSERT" authoritative at the database level instead
of application convention alone. That is a real schema change, covered by
Mac's explicit "STOP before migrating" instruction -- not applied here,
flagged as follow-up work requiring his sign-off, not decided silently.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.adapters.models import AdapterResponse, TeamStatLine
from app.persistence.game_identity import resolve_game_ids
from app.persistence.team_identity import resolve_team_ids

#: The only provider this module ever persists team stats for -- not
#: derived from AdapterResponse.source, same defensive convention as
#: odds_snapshots.py's identical constant.
_PROVIDER_NAME = "sportsdataio"


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same distinction from ProviderError as every other snapshot-persistence
    module's identical class."""


@dataclass
class TeamStatsPersistResult:
    inserted: int = 0
    unchanged: int = 0
    unresolved_games: list[str] = field(default_factory=list)
    unresolved_teams: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _latest_team_stats_row(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, team_id: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/team_stats",
        params={
            "game_id": f"eq.{game_id}",
            "team_id": f"eq.{team_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PersistenceError(
            f"failed to read latest team_stats for game {game_id}/team {team_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_team_stats(
    response: AdapterResponse[list[TeamStatLine]],
) -> TeamStatsPersistResult:
    """Writes each TeamStatLine as a team_stats row, but only when it
    differs from the existing latest row for that (game, team) pair -- see
    module docstring. A line whose game/team can't be resolved is skipped
    and reported, never guessed (no fuzzy matching, matching every other
    persistence module in this codebase)."""
    lines = response.value
    if not lines:
        return TeamStatsPersistResult()

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client, headers, provider_name=_PROVIDER_NAME,
            provider_game_ids=sorted({line.game_external_id for line in lines}),
        )
        team_ids = await resolve_team_ids(
            client, headers, provider_name=_PROVIDER_NAME,
            provider_team_ids=sorted({line.team for line in lines}),
        )

        result = TeamStatsPersistResult()
        for line in lines:
            game_id = game_ids.get(line.game_external_id)
            if game_id is None:
                result.unresolved_games.append(line.game_external_id)
                continue
            team_id = team_ids.get(line.team)
            if team_id is None:
                result.unresolved_teams.append(line.team)
                continue

            latest = await _latest_team_stats_row(client, headers, game_id=game_id, team_id=team_id)
            if latest is not None and latest["stats"] == line.stats:
                result.unchanged += 1
                continue

            insert_response = await client.post(
                "/rest/v1/team_stats",
                json={"game_id": game_id, "team_id": team_id, "stats": line.stats},
                headers=headers,
            )
            if insert_response.status_code not in (200, 201):
                raise PersistenceError(
                    f"failed to insert team_stats for game {game_id}/team {team_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            result.inserted += 1

        return result
