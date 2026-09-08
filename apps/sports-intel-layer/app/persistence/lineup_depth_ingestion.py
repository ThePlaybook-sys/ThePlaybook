"""MySportsFeeds lineup/depth ingestion (Phase 8.2 Lineup/Depth
Activation, 2026-09-08).

**A genuinely separate concept from `roster_ingestion.py`, deliberately
not merged into it.** `roster_ingestion.persist_roster` answers "who is
on this team" (roster membership) and, for SportsDataIO, "what is this
team's current depth-chart rank" from a single combined provider call.
This module answers a narrower, different question MySportsFeeds'
`lineup.json` feed actually provides: "who is expected to play in which
role for this specific game" -- a real, distinct MySportsFeeds concept
(HQ's own Phase 8.2 "keep player identity / roster membership /
lineup-depth role / game participation separate" architecture rule,
applied here). This module never creates a player or a roster
membership -- it only resolves already-known identity (via
`player_identity.resolve_player_ids`/`team_identity.resolve_team_ids`,
both read-only) and writes to the existing, unconstrained
`depth_chart_snapshots.depth_chart_data jsonb` column. No schema change
was needed: that column carries no DB-level shape constraint, so this
module's own enriched object shape (provider name, MySportsFeeds' own
`lastUpdatedOn`, the source game this "expected lineup" was captured
for, and each entry's raw lineup-slot label alongside the player's own
reported position) coexists with `roster_ingestion.py`'s existing bare
array shape without conflict -- both are just different real payloads
for different real providers, each valid JSON, exactly matching this
column's own always-been-unconstrained design.

**Real MySportsFeeds `lineup.json` shape (CONFIRMED from a live capture,
2026-09-03 gap test, game 163541 NE @ SEA):**
```
{
  "lastUpdatedOn": "2026-09-03T19:24:29.492Z",
  "game": {"id": 163541, "week": 1, "startTime": "...", "homeTeam": {...}, "awayTeam": {...}},
  "teamLineups": [
    {
      "team": {"id": 50, "abbreviation": "NE"},
      "expected": {
        "lineupPositions": [
          {"position": "Offense-RB-1", "player": {"id": 31103, "firstName": "Rhamondre", "lastName": "Stevenson", "position": "RB", "jerseyNumber": 38}},
          {"position": "Offense-RB-3", "player": null},
          ...
        ]
      }
    }
  ]
}
```

**Slot label parsing, not invention.** Each `lineupPositions[].position`
string (e.g. `"Offense-RB-1"`, `"Offense-C"`, `"SpecialTeams-K-1"`) is
MySportsFeeds' own compound encoding of side + position group +
(sometimes) a numeric depth rank -- `parse_lineup_slot` splits it back
into those three real, disclosed parts via regex, never guesses a rank
where the label carries none (e.g. `"Offense-C"` has no trailing digit,
so `depth_chart_rank` stays `None` for that slot -- a real, honest
"single-slot position, no explicit rank" signal, not defaulted to 1).

**A real data-quality quirk observed in this exact capture, disclosed
here rather than silently reconciled:** one player (MSF id 168249,
Brock Lampe) has `player.position == "FB"` but appears under the
`"Defense-CB-2"` slot label -- an apparent mismatch between the slot's
own group segment and the player's own reported position. This module
does not attempt to resolve or "fix" that discrepancy: `RosterEntry.
position` is always taken from the player's own real `position` field
(the more directly authoritative source, matching how canonical
identity already stores `primaryPosition`), while the raw slot label is
preserved verbatim (`lineup_slot`) for anyone who needs to see the
original, possibly-inconsistent provider encoding. Neither value is
discarded or silently corrected.

**Unconfirmed slots are dropped, not represented.** A `lineupPositions`
entry with `player: null` (an announced-but-unconfirmed depth slot) is
skipped entirely -- there is no `players.id` to resolve it to, and
representing "this slot exists but nobody is assigned yet" would need a
lineup-template concept this module does not build. Only real, named,
already-identity-resolved players are ever persisted.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx

from app.persistence.player_identity import resolve_player_ids
from app.persistence.team_identity import resolve_team_ids

#: Matches MySportsFeeds' own compound slot-label encoding, e.g.
#: "Offense-RB-1" -> (side="Offense", group="RB", rank="1"),
#: "Offense-C" -> (side="Offense", group="C", rank=None).
_SLOT_LABEL_RE = re.compile(r"^(?P<side>Offense|Defense|SpecialTeams)-(?P<group>[A-Za-z]+)(?:-(?P<rank>\d+))?$")


class LineupDepthIngestionError(Exception):
    """Raised when a depth_chart_snapshots read/write fails on
    Supabase's side -- same boundary distinction as every other
    persistence module's identical class."""


@dataclass
class LineupDepthIngestionResult:
    entries_written: int = 0
    unresolved_players: list[str] = field(default_factory=list)
    unresolved_team: str | None = None
    snapshot_written: bool = False


def parse_lineup_slot(label: str) -> tuple[str | None, str | None, int | None]:
    """Splits a real MySportsFeeds slot label into (side, group, rank).
    Returns (None, None, None) for a label that doesn't match the known
    shape -- never guessed, never partially filled in."""
    match = _SLOT_LABEL_RE.match(label)
    if not match:
        return None, None, None
    side = match.group("side")
    group = match.group("group")
    rank = match.group("rank")
    return side, group, int(rank) if rank is not None else None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _named_lineup_entries(lineup_body: dict, *, team: str) -> list[dict]:
    """Extracts only the real, named (non-null) lineup positions for one
    team from a real `lineup.json` body. Returns `[]` if the team isn't
    present in `teamLineups` at all -- never guessed."""
    for team_lineup in lineup_body.get("teamLineups") or []:
        if (team_lineup.get("team") or {}).get("abbreviation") != team:
            continue
        positions = (team_lineup.get("expected") or {}).get("lineupPositions") or []
        return [p for p in positions if p.get("player") is not None]
    return []


async def persist_lineup_depth_chart(
    lineup_body: dict,
    *,
    team: str,
    provider_name: str,
) -> LineupDepthIngestionResult:
    """Writes ONE `depth_chart_snapshots` row for `team` from a real,
    already-fetched MySportsFeeds `lineup.json` body -- never fetches
    anything itself. Resolves team/player identity read-only (via
    `team_identity.resolve_team_ids`/`player_identity.
    resolve_player_ids`); never creates a player or a roster membership.
    A player whose provider identity isn't already resolvable (no prior
    `player_provider_ids` row) is reported via `unresolved_players` and
    excluded from the written snapshot -- never fabricated."""
    entries = _named_lineup_entries(lineup_body, team=team)
    if not entries:
        return LineupDepthIngestionResult()

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        team_ids = await resolve_team_ids(client, headers, provider_name=provider_name, provider_team_ids=[team])
        team_id = team_ids.get(team)
        if team_id is None:
            return LineupDepthIngestionResult(
                unresolved_team=team,
                unresolved_players=[str(p["player"]["id"]) for p in entries],
            )

        provider_player_ids = [str(p["player"]["id"]) for p in entries]
        resolved = await resolve_player_ids(
            client, headers, provider_name=provider_name, provider_player_ids=provider_player_ids
        )

        depth_entries = []
        unresolved: list[str] = []
        for entry in entries:
            player = entry["player"]
            provider_player_id = str(player["id"])
            player_id = resolved.get(provider_player_id)
            if player_id is None:
                unresolved.append(provider_player_id)
                continue
            side, group, depth_chart_rank = parse_lineup_slot(entry.get("position", ""))
            depth_entries.append(
                {
                    "player_id": player_id,
                    "provider_player_id": provider_player_id,
                    "name": f"{player.get('firstName', '')} {player.get('lastName', '')}".strip(),
                    "position": player.get("position"),
                    "depth_chart_rank": depth_chart_rank,
                    "lineup_slot": entry.get("position"),
                    "side": side,
                }
            )

        result = LineupDepthIngestionResult(unresolved_players=unresolved, unresolved_team=None)
        if not depth_entries:
            return result

        game = lineup_body.get("game") or {}
        depth_chart_data = {
            "provider_name": provider_name,
            "provider_last_updated_on": lineup_body.get("lastUpdatedOn"),
            "source_game_external_id": str(game["id"]) if game.get("id") is not None else None,
            "entries": depth_entries,
        }
        insert_response = await client.post(
            "/rest/v1/depth_chart_snapshots",
            json={"team_id": team_id, "depth_chart_data": depth_chart_data},
            headers=headers,
        )
        if insert_response.status_code not in (200, 201):
            raise LineupDepthIngestionError(
                f"failed to insert depth_chart_snapshots for team {team_id}: "
                f"{insert_response.status_code} {insert_response.text}"
            )
        result.entries_written = len(depth_entries)
        result.snapshot_written = True
        return result
