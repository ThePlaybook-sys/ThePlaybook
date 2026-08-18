"""Persists normalized PlayerStatLine data into player_stats (Volume 3
§4.0, Phase 3E-8) -- the persistence half of the Postgame Ingestion
Worker's "final player stats" responsibility.

Same idempotent, correction-aware persistence design as
`app.persistence.team_stats` -- see that module's docstring for the full
reasoning (no uniqueness constraint or append-only trigger on
`player_stats` either; insert only when incoming stats differ from the
existing `created_at`-latest row for that (game, player) pair; a DB-level
append-only trigger remains available future hardening, not applied here).

**Player identity resolution only ever uses the existing
`player_provider_ids` mapping -- this module never creates a new player.**
Phase 3E-8's player-identity backfill (`app.persistence.player_backfill`)
covers exactly four real players, confirmed from this project's own
captured fixtures; nothing else. A `PlayerStatLine` whose
`player_external_id` has no `player_provider_ids` mapping is genuinely
unresolved -- reported via `unresolved_players`, never guessed by
name-matching, and never auto-created here. Auto-creating a player
opportunistically from live stats-response data was considered and
rejected for this phase: Mac's instruction was to "build the architecture
and fixture-backed population that can be proven now, then explicitly
report remaining coverage," not to silently expand `players` at ingestion
time from data whose real-world accuracy is DEFERRED PRODUCTION
VERIFICATION (SportsDataIO Free Trial data is confirmed scrambled for
several PlayerStats fields).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.adapters.models import AdapterResponse, PlayerStatLine
from app.persistence.game_identity import resolve_game_ids
from app.persistence.player_identity import resolve_player_ids

_PROVIDER_NAME = "sportsdataio"


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same distinction from ProviderError as every other snapshot-persistence
    module's identical class."""


@dataclass
class PlayerStatsPersistResult:
    inserted: int = 0
    unchanged: int = 0
    unresolved_games: list[str] = field(default_factory=list)
    unresolved_players: list[str] = field(default_factory=list)


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _latest_player_stats_row(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, player_id: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/player_stats",
        params={
            "game_id": f"eq.{game_id}",
            "player_id": f"eq.{player_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PersistenceError(
            f"failed to read latest player_stats for game {game_id}/player {player_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_player_stats(
    response: AdapterResponse[list[PlayerStatLine]],
) -> PlayerStatsPersistResult:
    """Writes each PlayerStatLine as a player_stats row, but only when it
    differs from the existing latest row for that (game, player) pair. A
    line whose game can't be resolved, or whose player has no
    player_provider_ids mapping yet, is skipped and reported -- never
    guessed, never auto-created (see module docstring)."""
    lines = response.value
    if not lines:
        return PlayerStatsPersistResult()

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client, headers, provider_name=_PROVIDER_NAME,
            provider_game_ids=sorted({line.game_external_id for line in lines}),
        )
        player_ids = await resolve_player_ids(
            client, headers, provider_name=_PROVIDER_NAME,
            provider_player_ids=sorted({line.player_external_id for line in lines}),
        )

        result = PlayerStatsPersistResult()
        for line in lines:
            game_id = game_ids.get(line.game_external_id)
            if game_id is None:
                result.unresolved_games.append(line.game_external_id)
                continue
            player_id = player_ids.get(line.player_external_id)
            if player_id is None:
                result.unresolved_players.append(line.player_external_id)
                continue

            latest = await _latest_player_stats_row(client, headers, game_id=game_id, player_id=player_id)
            if latest is not None and latest["stats"] == line.stats:
                result.unchanged += 1
                continue

            insert_response = await client.post(
                "/rest/v1/player_stats",
                json={"game_id": game_id, "player_id": player_id, "stats": line.stats},
                headers=headers,
            )
            if insert_response.status_code not in (200, 201):
                raise PersistenceError(
                    f"failed to insert player_stats for game {game_id}/player {player_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            result.inserted += 1

        return result
