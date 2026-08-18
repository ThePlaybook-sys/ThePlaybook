"""Player Props Worker orchestration (Phase 3E-4E).

**Cadence, read directly from Volume 2 §8 (not assumed identical to Odds
Worker without checking):** Player Props Worker's own row is the
*primary, numbered* source: "Refresh prop markets specifically --
highest volatility, highest user interest. Per-game pregame monitoring
cycle: 1 morning snapshot, then ramping frequency through
2h/60min/15min/5min windows before kickoff, stopping at kickoff." Odds
Worker's row is the one that borrows from *this* one ("Mirrors the Player
Props Worker's cadence shape below"), not the reverse -- so using the same
`app.workers.windows.classify_window` policy for both is not an
unverified assumption of identical cadence, it is what direct inspection
of both rows actually shows: Player Props defines the numbers, Odds
explicitly mirrors them. Both workers importing the one shared policy
module is Decision 4's "one authoritative window-classification policy"
requirement, applied correctly to two independently-cadenced-in-principle
workers that the Blueprint itself states share the same real numbers.

**Structural difference from the Odds Worker that this module's own
architecture makes unavoidable, not a design preference:** The Odds
Worker can self-discover unlinked games because The Odds API's bulk
`/odds` endpoint always returns every event regardless of filter (Phase
3E-4B/C's discovery mode). Player Props has no equivalent -- The Odds
API's player-props data only exists behind the event-*specific*
`/events/{id}/odds` endpoint (CONFIRMED per-game cost model, `the_odds_
api.py`'s own docstring), which requires already knowing the event id.
**This worker therefore never performs its own team-based game linking.**
A due game with no existing `game_provider_ids` mapping for
`the_odds_api` is skipped this cycle (collected, not a failure) --
resolved on a later cycle once the Odds Worker (or any other process that
shares `app.persistence.odds_game_linking`) has linked it. This is a
real, deliberate architecture decision, flagged in the 3E-4 completion
report as an assumption Mac should confirm: Player Props Worker depends
on game linkage established elsewhere, to avoid duplicating a
cost-relevant provider discovery call between two independently-cadenced
workers.

**Persistence (Phase 3E-4E):** writes to `odds_snapshots` with
`market_type='prop'` via `app.persistence.odds_snapshots.
persist_player_props` -- confirmed against Volume 3 §4's own schema
comment before implementing (see that function's docstring); no
conflict found, no new column or table needed.

**Master Refresh boundary:** identical to the Odds Worker's -- this
module is never called by Master Refresh and never calls it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from app.adapters.cache import CacheBackend, CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderError
from app.adapters.models import AdapterResponse, PlayerProp
from app.adapters.providers.the_odds_api import TheOddsApiPlayerPropsAdapter
from app.persistence.game_identity import GameIdentityError
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.odds_snapshots import PersistenceError, persist_player_props
from app.workers.windows import Window, classify_window, should_poll, ttl_seconds

_PROVIDER_NAME = "the_odds_api"

#: See app.workers.odds_worker's identical constant/comment -- an
#: independent worker-level scoping decision, not a reinterpretation of
#: Master Refresh's own canonical operating horizon.
_CANDIDATE_WINDOW_DAYS = 7


@dataclass
class PlayerPropsWorkerResult:
    status: str  # "success" | "partial" | "failed"
    games_considered: int = 0
    games_due: int = 0
    games_skipped_not_due: int = 0
    games_skipped_unlinked: list[str] = field(default_factory=list)
    props_persisted: int = 0
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


async def run_player_props_worker(
    *,
    supabase_client: httpx.AsyncClient,
    the_odds_api_client: httpx.AsyncClient,
    the_odds_api_key: str,
    cache_backend: CacheBackend | None = None,
    now: datetime | None = None,
    last_polled_at: dict[str, datetime] | None = None,
    target_game_ids: list[str] | None = None,
) -> PlayerPropsWorkerResult:
    """Runs one Player Props Worker cycle. Always returns a
    `PlayerPropsWorkerResult`, never raises -- same finite-job shape as
    `run_master_refresh`/`run_odds_worker`. See this module's own
    docstring for `last_polled_at`'s meaning (identical to the Odds
    Worker's). `target_game_ids` (Phase 3E-8, Decision 3) is also
    identical to `run_odds_worker`'s -- see that function's docstring.
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
        return PlayerPropsWorkerResult(status="failed", error=f"failed to list candidate games: {exc}")

    if not games:
        return PlayerPropsWorkerResult(status="success", games_considered=0)

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
            continue
        if should_poll(now=now, kickoff=kickoff, last_polled_at=last_polled_at.get(game["id"])):
            due_games.append(game)
        else:
            skipped += 1

    if not due_games:
        return PlayerPropsWorkerResult(
            status="success", games_considered=len(games), games_skipped_not_due=skipped
        )

    # Player Props cannot self-discover event ids (see module docstring)
    # -- only due games that already have a the_odds_api link are
    # fetchable this cycle. game_provider_ids has no "list all mappings
    # for these game_ids" query today, so this resolves each due game's
    # provider id via the same table from the other direction: read
    # every the_odds_api mapping and keep the ones whose game_id is due.
    try:
        provider_ids_by_game_id = await _reverse_resolve_the_odds_api_ids(
            supabase_client, headers, game_ids=[g["id"] for g in due_games]
        )
    except GameIdentityError as exc:
        return PlayerPropsWorkerResult(
            status="failed",
            games_considered=len(games),
            games_due=len(due_games),
            error=f"game identity lookup failed: {exc}",
        )

    linked_due_games = [g for g in due_games if g["id"] in provider_ids_by_game_id]
    unlinked_due_game_ids = [g["id"] for g in due_games if g["id"] not in provider_ids_by_game_id]

    if not linked_due_games:
        return PlayerPropsWorkerResult(
            status="partial" if unlinked_due_game_ids else "success",
            games_considered=len(games),
            games_due=len(due_games),
            games_skipped_not_due=skipped,
            games_skipped_unlinked=unlinked_due_game_ids,
        )

    # One fetch call per game, not one batched call for the whole due set
    # (Phase 3E-4E isolation requirement -- "provider failure does not
    # crash unrelated game processing"). The event-specific endpoint's own
    # adapter loop (`TheOddsApiPlayerPropsAdapter.fetch_player_props`)
    # raises immediately on the first failing game and discards whatever
    # it had already parsed for earlier games in the same call; calling it
    # once per game means one game's failure can never take another's
    # already-fetched props down with it. It also lets each game's cache
    # entry expire on its own window's TTL, rather than every due game
    # sharing one batch-wide minimum TTL.
    props_adapter = TheOddsApiPlayerPropsAdapter(client=the_odds_api_client, api_key=the_odds_api_key)

    all_props: list[PlayerProp] = []
    provider_source = _PROVIDER_NAME
    failures: list[str] = []
    for game in linked_due_games:
        provider_id = provider_ids_by_game_id[game["id"]]
        window = classify_window(now=now, kickoff=_parse_datetime(game["scheduled_start"]))
        caching = CachingAdapter(props_adapter, cache_backend, ttl_seconds=ttl_seconds(window))
        try:
            response: AdapterResponse[list[PlayerProp]] = await caching.call(
                "fetch_player_props", [provider_id], response_model=AdapterResponse[list[PlayerProp]]
            )
        except ProviderError as exc:
            failures.append(f"{game['id']}: Player Props fetch failed: {exc}")
            continue
        provider_source = response.source
        all_props.extend(response.value)

    persisted = 0
    if all_props:
        try:
            persisted = await persist_player_props(AdapterResponse(value=all_props, source=provider_source))
        except PersistenceError as exc:
            failures.append(f"persistence failed: {exc}")

    # Per-game failures are isolated and collected, never a hard stop for
    # the whole run (matching Master Refresh's own NON-BLOCKING/isolated
    # pattern for per-game work) -- "failed" is reserved for the earlier,
    # whole-run-blocking error paths (candidate-game lookup, game-identity
    # lookup) above.
    status = "partial" if (failures or unlinked_due_game_ids) else "success"

    return PlayerPropsWorkerResult(
        status=status,
        games_considered=len(games),
        games_due=len(due_games),
        games_skipped_not_due=skipped,
        games_skipped_unlinked=unlinked_due_game_ids,
        props_persisted=persisted,
        failures=failures,
    )


async def _reverse_resolve_the_odds_api_ids(
    client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]
) -> dict[str, str]:
    """Maps games.id -> the_odds_api provider_game_id, for the given
    game_ids -- the reverse direction of
    `app.persistence.game_identity.resolve_game_ids` (which goes
    provider_game_id -> games.id). A game with no the_odds_api mapping is
    simply absent from the result, exactly like the forward direction.
    """
    if not game_ids:
        return {}
    response = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "game_id": f"in.({','.join(game_ids)})",
            "select": "game_id,provider_game_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise GameIdentityError(
            f"failed to reverse-resolve the_odds_api ids: {response.status_code} {response.text}"
        )
    return {row["game_id"]: row["provider_game_id"] for row in response.json()}
