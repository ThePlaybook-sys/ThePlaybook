"""Weather Worker orchestration (Phase 3E-6).

**Cadence -- flat, no ramp tiers, per Mac's explicit instruction.**
Volume 2 §8 states only "Every 15 minutes" for Weather Worker, with no
stated start/stop boundary -- unlike Injury's day-of-week language or
Odds/Player Props' explicit ramp-boundary numbers. Two boundaries are
DERIVED from existing, already-established worker conventions rather than
invented fresh: the 7-day candidate window (the same scoping every other
worker independently adopted -- `_CANDIDATE_WINDOW_DAYS`, documented
identically in `odds_worker.py`/`player_props_worker.py`/
`injury_worker.py`) and stop-at-kickoff (reusing `app.workers.windows.
classify_window`'s existing `Window.STOPPED` classification directly --
*not* its ramp tiers, which this module never touches). The flat interval
itself, `_POLL_INTERVAL_SECONDS = 900`, is the one CONFIRMED number
(Volume 2 §8's literal "Every 15 minutes"), and already matches
`app.adapters.cache.CATEGORY_TTL_SECONDS["weather"]` exactly -- verified
by direct inspection before reusing it, not assumed.

**Dome/indoor optimization (Phase 3E-6, Option A, Mac's explicit
approval).** `games.venue_type` (populated from SportsDataIO's
`StadiumDetails.Type` during Schedule ingestion -- see
`app.adapters.providers.sportsdataio._VENUE_TYPE_MAP`) drives `venue_is_dome`
below:
  - `'dome'` -> `True` -- WeatherAPI is never called for this game; outdoor
    weather is structurally irrelevant to a fixed roof.
  - `'outdoor'` -> `False` -- polled normally.
  - `'retractable_dome'` or missing -> `None` -- genuinely unknown (a
    retractable roof's actual state on game day isn't something the
    Schedule endpoint reports at all). Per Mac's explicit instruction,
    `None` still permits polling *if* coordinates are available (real
    regional weather is still useful context even when roof state is
    unknown), but the persisted `WeatherConditions.is_dome` stays `None`
    -- never silently coerced to `False` (outdoor) just because polling
    happened.

**Location resolution.** `games.venue_lat`/`.venue_long` (same migration)
are used directly as WeatherAPI's `q` parameter (`"{lat},{long}"`, a
documented-supported WeatherAPI query form) -- no geocoding vendor, no
hardcoded stadium list. A game missing either coordinate is skipped
(`games_skipped_unresolved_location`), never guessed.

**Identity -- no `game_provider_ids` hop, unlike Odds/Player Props/
Injury.** Checked before writing this: WeatherAPI has no native
game/event concept of its own (`game_provider_ids.provider_name`'s check
constraint doesn't even permit `'weatherapi'`) -- `WeatherConditions.
game_external_id` is this project's own internal `games.id`, passed
straight through by this worker, not a foreign id needing resolution. See
`app.persistence.weather_snapshots`'s own module docstring for the same
finding on the persistence side.

**Per-game isolation, mirroring `player_props_worker.py`'s exact
reasoning:** one fetch call per game, not a single batched call for every
due game, so one game's provider failure can never take another's
already-fetched weather down with it, and each game's own cache entry
expires on the shared flat TTL independently.

**Master Refresh boundary:** identical to every other specialized worker's
-- this module is never called by Master Refresh and never calls it.
`daily_game_intelligence`'s `weather` field already reads from
`weather_snapshots` via `app.persistence.snapshots.latest_weather_snapshot`
(built in 3E-2, ahead of this worker existing) -- nothing here changes
that integration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import WeatherAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, WeatherConditions
from app.adapters.providers.weatherapi import WeatherAPIWeatherAdapter
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.weather_snapshots import PersistenceError, persist_weather_snapshots
from app.workers.windows import Window, classify_window

#: Same candidate-window convention as every other specialized worker --
#: an independent worker-level scoping decision, not a reinterpretation of
#: Master Refresh's own canonical 7-day operating horizon.
_CANDIDATE_WINDOW_DAYS = 7

#: CONFIRMED FROM VOLUME 2 §8 -- flat 15-minute cadence. No ramp tiers:
#: Mac's explicit instruction not to invent adaptive Weather timing.
_POLL_INTERVAL_SECONDS = 900


@dataclass
class WeatherWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    games_due: int = 0
    games_skipped_not_due: int = 0
    games_skipped_dome: list[str] = field(default_factory=list)
    games_skipped_unresolved_location: list[str] = field(default_factory=list)
    snapshots_persisted: int = 0
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def venue_is_dome(venue_type: str | None) -> bool | None:
    """True = definitively indoor/dome, False = definitively outdoor,
    None = unknown. See module docstring's "Dome/indoor optimization"
    section for the full reasoning -- never treats unknown as False."""
    if venue_type == "dome":
        return True
    if venue_type == "outdoor":
        return False
    return None  # 'retractable_dome' or missing entirely


def _location_for_game(game: dict) -> str | None:
    lat = game.get("venue_lat")
    long = game.get("venue_long")
    if lat is None or long is None:
        return None
    return f"{lat},{long}"


def _should_poll(*, now: datetime, kickoff: datetime, last_polled_at: datetime | None) -> bool:
    """Flat interval, reusing only `classify_window`'s STOPPED
    classification (DERIVED) -- never its ramp-tier intervals."""
    if classify_window(now=now, kickoff=kickoff) is Window.STOPPED:
        return False
    if last_polled_at is None:
        return True
    elapsed = now.astimezone(timezone.utc) - last_polled_at.astimezone(timezone.utc)
    return elapsed >= timedelta(seconds=_POLL_INTERVAL_SECONDS)


async def run_weather_worker(
    *,
    supabase_client: httpx.AsyncClient,
    weatherapi_client: httpx.AsyncClient,
    weatherapi_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: dict[str, datetime] | None = None,
    target_game_ids: list[str] | None = None,
    weather_adapter: WeatherAdapter | None = None,
) -> WeatherWorkerResult:
    """Runs one Weather Worker cycle. Always returns a `WeatherWorkerResult`,
    never raises -- same finite-job shape as every other specialized
    worker. `last_polled_at` is per-game (matching Odds/Player Props, since
    WeatherAPI's endpoint is per-game like theirs, not bulk like Injury's).

    `weather_adapter` (dependency-injection seam, not Demo-specific): when
    supplied, used instead of constructing `WeatherAPIWeatherAdapter`.
    `None` (the default) preserves today's real-provider construction and
    behavior unchanged.

    `target_game_ids` (Phase 3E-8, Decision 3): when provided, restricts
    this run to exactly these candidate games, treated as due
    unconditionally (bypassing `_should_poll`'s own cadence/STOPPED gating)
    -- Pregame Worker's coordination hook, identical in spirit to
    `run_odds_worker`'s parameter of the same name. `None` (the default)
    preserves normal behavior unchanged.
    """
    headers = _auth_headers()
    cache_backend = cache_backend or InMemoryCacheBackend()
    now = now or datetime.now(timezone.utc)
    last_polled_at = last_polled_at or {}

    today: date = now.date()
    try:
        games = await list_games_in_window(
            supabase_client, headers, start=today, end=today + timedelta(days=_CANDIDATE_WINDOW_DAYS)
        )
    except GamesQueryError as exc:
        return WeatherWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return WeatherWorkerResult(status="success", games_considered=0)

    target_set = set(target_game_ids) if target_game_ids is not None else None
    due_games: list[dict] = []
    skipped_not_due = 0
    for game in games:
        if target_set is not None:
            if game["id"] in target_set:
                due_games.append(game)
            else:
                skipped_not_due += 1
            continue
        kickoff = _parse_datetime(game["scheduled_start"])
        if _should_poll(now=now, kickoff=kickoff, last_polled_at=last_polled_at.get(game["id"])):
            due_games.append(game)
        else:
            skipped_not_due += 1

    if not due_games:
        return WeatherWorkerResult(
            status="success", games_considered=len(games), games_skipped_not_due=skipped_not_due
        )

    skipped_dome: list[str] = []
    skipped_unresolved_location: list[str] = []
    pollable_games: list[dict] = []
    location_by_game_id: dict[str, str] = {}

    for game in due_games:
        is_dome = venue_is_dome(game.get("venue_type"))
        if is_dome is True:
            skipped_dome.append(game["id"])
            continue
        location = _location_for_game(game)
        if location is None:
            skipped_unresolved_location.append(game["id"])
            continue
        pollable_games.append(game)
        location_by_game_id[game["id"]] = location

    if not pollable_games:
        status = "partial" if skipped_unresolved_location else "success"
        return WeatherWorkerResult(
            status=status,
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped_not_due,
            games_skipped_dome=skipped_dome,
            games_skipped_unresolved_location=skipped_unresolved_location,
        )

    weather_adapter = weather_adapter or WeatherAPIWeatherAdapter(
        client=weatherapi_client,
        api_key=weatherapi_key,
        location_for_game=lambda game_id: location_by_game_id[game_id],
    )

    all_conditions: list[WeatherConditions] = []
    provider_source = "weatherapi"
    failures: list[str] = []

    for game in pollable_games:
        kickoff = _parse_datetime(game["scheduled_start"])
        caching = CachingAdapter(weather_adapter, cache_backend, ttl_seconds=_POLL_INTERVAL_SECONDS)
        try:
            response: AdapterResponse[WeatherConditions] = await caching.call(
                "fetch_weather", game["id"], kickoff, response_model=AdapterResponse[WeatherConditions]
            )
        except ProviderError as exc:
            failures.append(f"{game['id']}: weather fetch failed: {exc}")
            continue
        provider_source = response.source
        # The adapter itself always returns is_dome=None (no vendor knows
        # this) -- overlay our own venue-derived value before persisting.
        # False and None are both legitimate here (True/dome was already
        # filtered out above, before ever reaching the adapter).
        known_is_dome = venue_is_dome(game.get("venue_type"))
        all_conditions.append(response.value.model_copy(update={"is_dome": known_is_dome}))

    persisted = 0
    if all_conditions:
        try:
            persisted = await persist_weather_snapshots(
                AdapterResponse(value=all_conditions, source=provider_source)
            )
        except PersistenceError as exc:
            failures.append(f"persistence failed: {exc}")

    status = "partial" if (failures or skipped_unresolved_location) else "success"
    return WeatherWorkerResult(
        status=status,
        games_considered=len(games),
        games_due=len(due_games),
        games_skipped_not_due=skipped_not_due,
        games_skipped_dome=skipped_dome,
        games_skipped_unresolved_location=skipped_unresolved_location,
        snapshots_persisted=persisted,
        failures=failures,
    )
