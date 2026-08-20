"""Odds Worker orchestration (Phase 3E-4D).

Volume 2 §8's own cadence row for Odds Worker: "Adaptive, game-aware...
Polling frequency ramps up as a game's kickoff approaches... Mirrors the
Player Props Worker's cadence shape below." Implemented entirely through
the single shared `app.workers.windows.classify_window` policy (3E-4F) --
this module computes no cadence numbers of its own, and Player Props
Worker (3E-4E) uses the exact same policy rather than a second copy of it.

**Master Refresh boundary (Decision 1, still in force, Phase 3E-2/3E-4D):**
this worker never calls Master Refresh, and Master Refresh never calls
this worker -- Master Refresh makes zero Odds provider calls, exactly as
its own ownership-boundary documentation states. This worker only *reads*
`games` (via `app.persistence.games.list_games_in_window`, the same
read-only helper Master Refresh itself uses) to determine its candidate
set; it never creates or updates a `games` row.

**Discovery + persistence flow, one bulk call per run:**
1. Query candidate games (see `_CANDIDATE_WINDOW_DAYS` below).
2. Classify each by kickoff proximity; skip anything STOPPED (already
   kicked off) or not yet due per its window's poll interval.
3. If nothing is due, skip the provider call entirely (Mac's "avoid
   duplicate provider calls where caching already satisfies freshness" --
   applied here as "don't even ask if nothing needs it").
4. Otherwise, one discovery-mode `fetch_odds([])` call (Phase 3E-4B/C) --
   the bulk endpoint always returns the full slate regardless of filter,
   so one call covers every due game at once. Wrapped in `CachingAdapter`
   with a dynamic TTL (Phase 3E-4F): the shortest (most urgent) TTL among
   this run's due games' windows, since one bulk response can span games
   in different windows and the cache must never treat a soon-kickoff
   game's data as fresher than its own window says it can be.
5. Link any not-yet-known event to its internal `games.id`
   (`app.persistence.odds_game_linking`, Phase 3E-4C) -- isolated
   per-event, never aborting the run.
6. Persist odds lines only for events that resolved to a game in this
   run's due set (`app.persistence.odds_snapshots`, append-only).

**Failure isolation:** a single game's linking/resolution failure never
blocks another game's -- `odds_game_linking`'s own batch function already
isolates per-event. A persistence failure is collected, not raised,
matching Mac's "provider failure does not crash unrelated game
processing" requirement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.base import OddsAdapter
from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, OddsLine
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from app.persistence.game_identity import GameIdentityError, resolve_game_ids
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.odds_game_linking import ProviderEventIdentity, resolve_and_link_odds_events
from app.persistence.odds_snapshots import PersistenceError, persist_odds_lines
from app.workers.windows import Window, classify_window, should_poll, ttl_seconds

_PROVIDER_NAME = "the_odds_api"

#: How many days out this worker considers a game a polling candidate at
#: all -- an independent, worker-level scoping decision, NOT a
#: reinterpretation of Master Refresh's own canonical
#: `[today, today + 7 days)` operating horizon (Volume 2 §8 v4.4, which
#: explicitly governs Master Refresh's game-identity/assembly work only
#: and states its own horizon "does not change any specialized worker's
#: cadence"). The same numeric value is used here for the practical
#: reason that Master Refresh itself only creates/maintains games this
#: far out -- there is nothing for this worker to poll beyond it -- not
#: because the two concepts are the same statement.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class OddsWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    games_due: int = 0
    games_skipped_not_due: int = 0
    lines_persisted: int = 0
    newly_linked: int = 0
    unresolved_events: list[str] = field(default_factory=list)
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


async def run_odds_worker(
    *,
    supabase_client: httpx.AsyncClient,
    the_odds_api_client: httpx.AsyncClient,
    the_odds_api_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: dict[str, datetime] | None = None,
    target_game_ids: list[str] | None = None,
    odds_adapter: OddsAdapter | None = None,
) -> OddsWorkerResult:
    """Runs one Odds Worker cycle. Always returns an `OddsWorkerResult`,
    never raises -- same finite-job shape as `run_master_refresh`.

    `odds_adapter` (dependency-injection seam, not Demo-specific): when
    supplied, this exact adapter instance is used instead of constructing
    `TheOddsApiOddsAdapter` -- e.g. Demo Mode's `DemoOddsAdapter`, or any
    other `OddsAdapter` implementation. `None` (the default) preserves
    today's real-provider construction and behavior unchanged for every
    existing caller.

    `last_polled_at` (game_id -> last successful poll time) is injected
    rather than read from any persisted state, since this phase does not
    build worker-run history storage (out of 3E-4's scope) -- a real
    scheduling mechanism (Railway Cron or otherwise, explicitly NOT
    decided in this phase per the stop condition) would be the thing that
    tracks and passes this in. Passing `None` (the default) means "treat
    every due game as never-polled," which is always safe -- it can only
    cause an extra poll, never a missed one.

    `target_game_ids` (Phase 3E-8, Decision 3): when provided, restricts
    this run to exactly these candidate games, treated as due
    unconditionally -- bypassing `classify_window`/`should_poll` entirely
    for them. This is Pregame Worker's own coordination hook: it forces
    this existing worker's own fetch/persistence path for one game right
    at T-minus-5-minutes, rather than duplicating any of this worker's
    logic. `None` (the default) preserves this worker's normal
    cadence-driven behavior unchanged for every other caller.
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
        return OddsWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return OddsWorkerResult(status="success", games_considered=0)

    target_set = set(target_game_ids) if target_game_ids is not None else None
    due_games: list[dict] = []
    skipped = 0
    for game in games:
        if target_set is not None:
            if game["id"] in target_set:
                due_games.append(game)
            else:
                skipped += 1
            continue
        kickoff = _parse_datetime(game["scheduled_start"])
        window = classify_window(now=now, kickoff=kickoff)
        if window is Window.STOPPED:
            continue  # already kicked off -- this worker generation never polls post-kickoff
        if should_poll(now=now, kickoff=kickoff, last_polled_at=last_polled_at.get(game["id"])):
            due_games.append(game)
        else:
            skipped += 1

    if not due_games:
        return OddsWorkerResult(status="success", games_considered=len(games), games_skipped_not_due=skipped)

    # Dynamic TTL (Phase 3E-4F): the shortest (most urgent) TTL among this
    # run's due games -- one bulk response can span games in different
    # windows, and the cache must never treat a soon-kickoff game's data
    # as fresher than its own window allows.
    due_windows = [classify_window(now=now, kickoff=_parse_datetime(g["scheduled_start"])) for g in due_games]
    dynamic_ttl = min(ttl_seconds(w) for w in due_windows)

    odds_adapter = odds_adapter or TheOddsApiOddsAdapter(client=the_odds_api_client, api_key=the_odds_api_key)
    caching = CachingAdapter(odds_adapter, cache_backend, ttl_seconds=dynamic_ttl)
    try:
        response: AdapterResponse[list[OddsLine]] = await caching.call(
            "fetch_odds", [], response_model=AdapterResponse[list[OddsLine]]
        )
    except ProviderError as exc:
        return OddsWorkerResult(
            status="failed", games_considered=len(games), games_due=len(due_games), error=f"Odds fetch failed: {exc}"
        )

    events_by_provider_id: dict[str, OddsLine] = {}
    for line in response.value:
        events_by_provider_id.setdefault(line.game_external_id, line)

    try:
        already_linked = await resolve_game_ids(
            supabase_client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=list(events_by_provider_id.keys()),
        )
    except GameIdentityError as exc:
        return OddsWorkerResult(
            status="failed",
            games_considered=len(games),
            games_due=len(due_games),
            error=f"game identity lookup failed: {exc}",
        )

    to_link = [
        ProviderEventIdentity(
            provider_game_id=provider_id,
            home_team=line.home_team,
            away_team=line.away_team,
            commence_time=line.commence_time,
        )
        for provider_id, line in events_by_provider_id.items()
        if provider_id not in already_linked
    ]

    unresolved: list[str] = []
    newly_linked = 0
    if to_link:
        linking_result = await resolve_and_link_odds_events(supabase_client, headers, to_link)
        newly_linked = len(linking_result.linked)
        unresolved = [f"{e.provider_game_id}: {e.reason}" for e in linking_result.unresolved]
        for linked in linking_result.linked:
            already_linked[linked.provider_game_id] = linked.game_id

    due_game_ids = {g["id"] for g in due_games}
    lines_to_persist = [line for line in response.value if already_linked.get(line.game_external_id) in due_game_ids]

    persisted = 0
    failures: list[str] = []
    if lines_to_persist:
        try:
            persisted = await persist_odds_lines(AdapterResponse(value=lines_to_persist, source=response.source))
        except PersistenceError as exc:
            failures.append(f"persistence failed: {exc}")

    status = "partial" if (failures or unresolved) else "success"

    return OddsWorkerResult(
        status=status,
        games_considered=len(games),
        games_due=len(due_games),
        games_skipped_not_due=skipped,
        lines_persisted=persisted,
        newly_linked=newly_linked,
        unresolved_events=unresolved,
        failures=failures,
    )
