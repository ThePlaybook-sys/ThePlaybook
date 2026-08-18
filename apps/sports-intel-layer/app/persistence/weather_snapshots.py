"""Persists normalized WeatherConditions data into weather_snapshots
(Volume 3 §4, Phase 3E-6) -- the append-only historical record
`daily_game_intelligence`'s `weather` field already reads from
(`app.persistence.snapshots.latest_weather_snapshot`, built in 3E-2 ahead
of this worker existing).

**Deliberately does NOT go through `app.persistence.game_identity.
resolve_game_ids`, unlike `odds_snapshots.py`/`injury_reports.py` --
checked before writing this, not assumed symmetric with those.**
WeatherAPI has no native "game" or "event" concept of its own at all (it
is a pure location/forecast API); `game_provider_ids.provider_name`'s own
check constraint only permits `'the_odds_api'`/`'sportsdataio'` --
providers with a real, foreign id namespace requiring translation.
`WeatherConditions.game_external_id` (per `WeatherAPIWeatherAdapter`'s own
docstring: its `location_for_game` resolver is "backed by `games.stadium`"
in production) is therefore already this project's own internal
`games.id`, supplied by the worker at call time -- not a second id needing
resolution. Writing it directly as `weather_snapshots.game_id` is correct,
not a shortcut.

Otherwise mirrors `app.persistence.injury_reports`/`odds_snapshots`:
pure-append, no update, no upsert, no de-duplication -- matching every
other snapshot table's "every poll is a new row" convention and
`weather_snapshots`' own append-only DB trigger from the Phase 1
migration, exercised by real writes for the first time here.
"""
from __future__ import annotations

import os

import httpx

from app.adapters.models import AdapterResponse, WeatherConditions


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same distinction from ProviderError as the sibling snapshot-persistence
    modules' identical class."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def persist_weather_snapshots(response: AdapterResponse[list[WeatherConditions]]) -> int:
    """Writes every WeatherConditions in `response` as a new
    weather_snapshots row, keyed directly by `reading.game_external_id`
    (already this project's own internal `games.id` -- see module
    docstring for why no identity-resolution hop is needed here).
    """
    readings = response.value
    if not readings:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    rows = [
        {
            "game_id": reading.game_external_id,
            "weather_data": {
                "temperature_f": reading.temperature_f,
                "wind_mph": reading.wind_mph,
                "precipitation_pct": reading.precipitation_pct,
                "conditions": reading.conditions,
                "is_dome": reading.is_dome,
            },
        }
        for reading in readings
    ]

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        insert_response = await client.post("/rest/v1/weather_snapshots", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert weather_snapshots: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)
