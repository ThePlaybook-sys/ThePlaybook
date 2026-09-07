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

**Provider provenance/observation timestamp (Phase 8.0.5 Weather
Activation, 2026-09-07): a real, disclosed gap closed, not a schema
change.** `AdapterResponse.source`/`.provider_reported_at` were computed
by `WeatherAPIWeatherAdapter` all along but silently dropped before this
function ever saw them (the worker's own per-game loop discarded each
individual response after copying only `WeatherConditions` out of it).
Since `weather_snapshots.weather_data` is already an unconstrained jsonb
payload (matching `odds_snapshots.line_data`/`injury_reports.report_data`'s
own established shape), both values are now embedded INTO that existing
column -- `source` (the provider name) and `observed_at` (the real
vendor-reported forecast/observation timestamp, distinct from
`captured_at`, which is only ever "when we polled"). No migration, no new
column: the smallest fix that makes both genuinely verifiable from
persisted data instead of only from transient in-process logs.
"""
from __future__ import annotations

import os
from datetime import datetime

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


async def persist_weather_snapshots(
    response: AdapterResponse[list[WeatherConditions]],
    *,
    observed_at_by_game: dict[str, datetime | None] | None = None,
) -> int:
    """Writes every WeatherConditions in `response` as a new
    weather_snapshots row, keyed directly by `reading.game_external_id`
    (already this project's own internal `games.id` -- see module
    docstring for why no identity-resolution hop is needed here).

    `observed_at_by_game` (optional, keyed by the same `game_external_id`):
    each game's own real `provider_reported_at`, captured by the caller
    before it would otherwise be discarded (see module docstring). `None`
    (the default) omits `observed_at` from the payload entirely -- safe
    for any caller that hasn't captured it, never a fabricated value.
    """
    readings = response.value
    if not readings:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()
    observed_at_by_game = observed_at_by_game or {}

    rows = []
    for reading in readings:
        observed_at = observed_at_by_game.get(reading.game_external_id)
        rows.append(
            {
                "game_id": reading.game_external_id,
                "weather_data": {
                    "temperature_f": reading.temperature_f,
                    "wind_mph": reading.wind_mph,
                    "precipitation_pct": reading.precipitation_pct,
                    "conditions": reading.conditions,
                    "is_dome": reading.is_dome,
                    "source": response.source,
                    "observed_at": observed_at.isoformat() if observed_at is not None else None,
                },
            }
        )

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        insert_response = await client.post("/rest/v1/weather_snapshots", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert weather_snapshots: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)


async def read_last_polled_at() -> dict[str, datetime]:
    """Derives `run_weather_worker`'s `last_polled_at` argument from
    already-persisted `weather_snapshots` history, keyed by internal
    `game_id` -- exactly the same derivation
    `app.persistence.odds_snapshots.read_last_polled_at` already
    established for Odds Worker's identical real-invocation-path problem
    (a stateless HTTP-triggered caller has no run-history of its own; `run_
    weather_worker`'s own `last_polled_at=None` default safely means
    "treat every candidate as never-polled," which is correct for a single
    call but would defeat the worker's own cadence gate for a repeatedly
    invoked cron caller). No new state storage: `weather_snapshots` is
    already append-only with a real `captured_at` on every real poll
    (unlike `news_article_history`'s insert-once-on-new-content shape,
    which could NOT serve this same role for News Worker -- a materially
    different table, not an inconsistency).

    A game with zero prior rows is simply absent from the returned dict --
    `last_polled_at.get(game_id)` then returns `None`, which `_should_poll`
    already correctly treats as "never polled, always due"."""
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        response = await client.get(
            "/rest/v1/weather_snapshots",
            params={
                "select": "game_id,captured_at",
                "order": "captured_at.desc",
                # Generous bound, not correctness-critical -- see
                # odds_snapshots.read_last_polled_at's identical reasoning.
                "limit": "5000",
            },
            headers=headers,
        )
        if response.status_code != 200:
            raise PersistenceError(
                f"failed to read weather_snapshots for last_polled_at: {response.status_code} {response.text}"
            )

        result: dict[str, datetime] = {}
        for row in response.json():
            game_id = row["game_id"]
            if game_id not in result:
                result[game_id] = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
        return result
