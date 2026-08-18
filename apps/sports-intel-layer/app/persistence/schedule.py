"""Persists normalized ScheduleEntry data from a Schedule adapter (Volume 3
§4.0/§4.1, Phase 3E-1) -- the ingestion path that creates and maintains
games rows and their game_provider_ids mapping for the schedule's provider.

Deliberately narrow: this is the FOUNDATION path only (3E-1's own scope).
For each ScheduleEntry it:
  - looks up an existing game_provider_ids mapping for
    (response.source, entry.game_external_id);
  - if found, updates that games row's mutable fields (status, stadium,
    scheduled_start, season_type, week, venue_lat, venue_long, venue_type);
  - if not found, creates a new games row and links it via
    game_provider_ids -- this is how a provider's Schedule call establishes
    a game's existence in the first place.

What this deliberately does NOT do: reconcile two different providers
independently discovering the same real-world game (e.g. The Odds API and
SportsDataIO both eventually knowing about the same Sunday matchup).
Decision 2 (2026-08-13) explicitly rules out team/date fuzzy matching as
that mechanism, and no worker exists yet with the authority to perform
that reconciliation -- it remains an open item, reported as such rather
than silently solved here (see PROGRESS.md / the 3E-1 completion report).
"""
from __future__ import annotations

import os

import httpx

from app.adapters.models import AdapterResponse, ScheduleEntry
from app.persistence.game_identity import link_provider_id, resolve_game_ids


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same boundary distinction as odds_snapshots.PersistenceError: a
    failure here is on our side of the adapter boundary, not the
    vendor's."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def persist_schedule_entries(
    response: AdapterResponse[list[ScheduleEntry]],
) -> tuple[int, int]:
    """Upserts every ScheduleEntry in `response` into games, resolving/
    creating each row through game_provider_ids keyed by
    (response.source, entry.game_external_id). Returns (created, updated)
    counts so a caller can distinguish a first-time ingest from a routine
    refresh instead of a single ambiguous total.
    """
    entries = response.value
    if not entries:
        return (0, 0)

    provider_name = response.source
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()
    created = 0
    updated = 0

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        existing = await resolve_game_ids(
            client,
            headers,
            provider_name=provider_name,
            provider_game_ids=[entry.game_external_id for entry in entries],
        )

        for entry in entries:
            mutable_fields = {
                "home_team": entry.home_team,
                "away_team": entry.away_team,
                "scheduled_start": entry.scheduled_start.isoformat(),
                "stadium": entry.stadium,
                "status": entry.status,
                "season_type": entry.season_type,
                "week": entry.week,
                # Phase 3E-6, Option A: refreshed on every Schedule ingestion,
                # same as every other mutable field above -- never fabricated
                # when the entry itself carries None.
                "venue_lat": entry.venue_lat,
                "venue_long": entry.venue_long,
                "venue_type": entry.venue_type,
            }

            game_id = existing.get(entry.game_external_id)
            if game_id is not None:
                patch_response = await client.patch(
                    "/rest/v1/games",
                    params={"id": f"eq.{game_id}"},
                    json=mutable_fields,
                    headers=headers,
                )
                if patch_response.status_code not in (200, 204):
                    raise PersistenceError(
                        f"failed to update game {game_id}: "
                        f"{patch_response.status_code} {patch_response.text}"
                    )
                updated += 1
                continue

            insert_response = await client.post(
                "/rest/v1/games",
                json={**mutable_fields, "sport": "nfl"},
                headers={**headers, "Prefer": "return=representation"},
            )
            if insert_response.status_code not in (200, 201):
                raise PersistenceError(
                    f"failed to create game for {provider_name}:{entry.game_external_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            new_rows = insert_response.json()
            new_game_id = new_rows[0]["id"]
            await link_provider_id(
                client,
                headers,
                game_id=new_game_id,
                provider_name=provider_name,
                provider_game_id=entry.game_external_id,
            )
            created += 1

    return (created, updated)
