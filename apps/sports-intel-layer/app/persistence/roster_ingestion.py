"""Durable roster ingestion (Volume 3 §4.0, roster_memberships +
depth_chart_snapshots -- Phase 3F-1, Decisions 1-3).

Turns a `RosterAdapter.fetch_roster` result (one team's current roster,
already merged with DepthCharts rank per 3B/3C) into durable state:
`players`/`player_provider_ids` (via `player_identity.ensure_player`,
unchanged), a `roster_memberships` history row when the observed team
differs from the player's latest known team, and one
`depth_chart_snapshots` row per call for the team.

**No fuzzy matching, no fabricated identity.** A `RosterEntry` is only ever
turned into a player via its own `player_external_id` -- `ensure_player`'s
existing "resolve-or-create through an explicit provider identity" contract
is reused unchanged. The one new failure mode this module introduces is a
roster whose own team abbreviation has no `team_provider_ids` mapping: in
that case none of its players can be safely anchored to a team, so the
whole roster is reported via `unresolved_team`/`unresolved_players` and
nothing is written -- never created with a null/guessed team.

**Roster membership semantics (Decision 1, defined before this migration
was written):**
  - first observed membership -> insert (no prior `roster_memberships` row
    for this player).
  - unchanged membership -> no insert; `players.team_id` already correct.
  - team change -> insert a new row (old row untouched), then sync
    `players.team_id` to the new team.
  - rejoining a prior team -> handled identically to any other team
    change; the comparison only ever looks at the single latest row, so a
    rejoin needs no special-casing.
  - release/free-agent state -> **not representable and not inferred**.
    `RosterEntry` only ever describes a player currently on a roster; this
    module never infers a release from a player's absence in a later
    fetch (that would need full-roster-diffing this phase does not build,
    and risks false positives from provider quirks or injured-but-still-
    rostered players). See the migration's own comment for the same note.

**Depth-chart semantics (Decision 2):** unlike `roster_memberships`, this
writes one `depth_chart_snapshots` row per call, unconditionally -- the
same "strict append-only, every capture is a new row" convention
`odds_snapshots`/`injury_reports`/`weather_snapshots` already use (the
table carries the same DB-level trigger), not `team_stats`/`player_stats`'
different insert-on-change one. The payload is derived from the same
`RosterEntry` list already fetched (player_external_id/name/position/
depth_chart_rank), not a second raw-provider re-fetch -- this project only
ever normalized `DepthOrder` into `RosterEntry.depth_chart_rank`, so that
is the fact recorded here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.adapters.models import AdapterResponse, RosterEntry
from app.persistence.player_identity import ensure_player, resolve_player_ids
from app.persistence.team_identity import resolve_team_ids

_PROVIDER_NAME = "sportsdataio"


class RosterIngestionError(Exception):
    """Raised when a roster_memberships/depth_chart_snapshots/players write
    fails on Supabase's side -- same boundary distinction as every other
    persistence module's identical class."""


@dataclass
class RosterIngestionResult:
    players_created: int = 0
    players_confirmed: int = 0
    memberships_inserted: int = 0
    memberships_unchanged: int = 0
    depth_chart_written: bool = False
    unresolved_team: str | None = None
    unresolved_players: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _latest_membership(client: httpx.AsyncClient, headers: dict, *, player_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/roster_memberships",
        params={
            "player_id": f"eq.{player_id}",
            "select": "team_id",
            "order": "observed_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise RosterIngestionError(
            f"failed to read latest roster_memberships for player {player_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def _sync_membership(client: httpx.AsyncClient, headers: dict, *, player_id: str, team_id: str) -> bool:
    """Returns True if a new membership row was inserted (first observation
    or team change), False if the observed team matches the latest known
    membership (no-op)."""
    latest = await _latest_membership(client, headers, player_id=player_id)
    if latest is not None and latest["team_id"] == team_id:
        return False

    insert_response = await client.post(
        "/rest/v1/roster_memberships",
        json={"player_id": player_id, "team_id": team_id},
        headers=headers,
    )
    if insert_response.status_code not in (200, 201):
        raise RosterIngestionError(
            f"failed to insert roster_memberships for player {player_id}/team {team_id}: "
            f"{insert_response.status_code} {insert_response.text}"
        )

    patch_response = await client.patch(
        "/rest/v1/players",
        params={"id": f"eq.{player_id}"},
        json={"team_id": team_id},
        headers=headers,
    )
    if patch_response.status_code not in (200, 204):
        raise RosterIngestionError(
            f"failed to sync players.team_id for player {player_id}: "
            f"{patch_response.status_code} {patch_response.text}"
        )
    return True


async def persist_roster(response: AdapterResponse[list[RosterEntry]]) -> RosterIngestionResult:
    """Writes one team's roster fetch into durable players/player_provider_ids
    (create-or-confirm, never fuzzy-matched), roster_memberships (insert
    only on first observation or team change), and one unconditional
    depth_chart_snapshots row for the team. Every `RosterEntry` in
    `response.value` is expected to share the same `.team` -- one call
    corresponds to one team's roster, matching `RosterAdapter.fetch_roster`'s
    own per-team contract."""
    entries = response.value
    if not entries:
        return RosterIngestionResult()

    team_abbrev = entries[0].team
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        team_ids = await resolve_team_ids(
            client, headers, provider_name=_PROVIDER_NAME, provider_team_ids=[team_abbrev]
        )
        team_id = team_ids.get(team_abbrev)
        if team_id is None:
            return RosterIngestionResult(
                unresolved_team=team_abbrev,
                unresolved_players=[e.player_external_id for e in entries],
            )

        result = RosterIngestionResult()
        for entry in entries:
            existing = await resolve_player_ids(
                client, headers, provider_name=_PROVIDER_NAME, provider_player_ids=[entry.player_external_id]
            )
            is_new = entry.player_external_id not in existing

            player_id = await ensure_player(
                client,
                headers,
                provider_name=_PROVIDER_NAME,
                provider_player_id=entry.player_external_id,
                name=entry.player_name,
                team_id=team_id,
                position=entry.position,
            )
            if is_new:
                result.players_created += 1
            else:
                result.players_confirmed += 1

            if await _sync_membership(client, headers, player_id=player_id, team_id=team_id):
                result.memberships_inserted += 1
            else:
                result.memberships_unchanged += 1

        depth_chart_data = [
            {
                "player_external_id": e.player_external_id,
                "name": e.player_name,
                "position": e.position,
                "depth_chart_rank": e.depth_chart_rank,
            }
            for e in entries
        ]
        insert_response = await client.post(
            "/rest/v1/depth_chart_snapshots",
            json={"team_id": team_id, "depth_chart_data": depth_chart_data},
            headers=headers,
        )
        if insert_response.status_code not in (200, 201):
            raise RosterIngestionError(
                f"failed to insert depth_chart_snapshots for team {team_id}: "
                f"{insert_response.status_code} {insert_response.text}"
            )
        result.depth_chart_written = True

        return result
