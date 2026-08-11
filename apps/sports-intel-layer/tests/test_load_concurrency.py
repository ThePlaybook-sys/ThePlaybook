"""Sunday-slate internal pipeline load/concurrency test (Phase 3B, approved
2026-08-11). Proves OUR pipeline's throughput/concurrency/cache behavior
under Sunday-slate volume using fixture-backed traffic -- explicitly NOT a
test of the real provider's throughput or rate-limit behavior under that
volume (that stays on the DEFERRED — FINANCIAL/EXTERNAL DEPENDENCY
checklist, see PROGRESS.md). This is the split Mac's approved plan
requires: internal pipeline load = testable now, real provider behavior
under that load = deferred.

~13 concurrent NFL games, each running its own independent pregame polling
cycle (18 calls/game, the adaptive cadence approved 2026-08-10) concurrently
with the other 12 games -- modeling how the Player Props Worker actually
runs in production, not one artificial burst against a single key.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.models import AdapterResponse, OddsLine, PlayerProp
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter, TheOddsApiPlayerPropsAdapter
from tests.adapters.the_odds_api_fixtures import load

PROPS_RESPONSE_MODEL = AdapterResponse[list[PlayerProp]]
BASE_URL = "https://api.the-odds-api.com"

GAME_COUNT = 13  # a representative peak Sunday slate (2026-08-10 credit projection, PROGRESS.md)
CALLS_PER_GAME = 18  # the approved adaptive pregame monitoring cycle (PROGRESS.md, 2026-08-10)


def _game_ids() -> list[str]:
    return [f"{i:032x}" for i in range(1, GAME_COUNT + 1)]


@pytest.mark.asyncio
@respx.mock
async def test_sunday_slate_concurrent_games_complete_without_error():
    for game_id in _game_ids():
        respx.get(f"{BASE_URL}/v4/sports/americanfootball_nfl/events/{game_id}/odds").mock(
            return_value=httpx.Response(200, json=load("player_props_event.json"))
        )

    adapter = TheOddsApiPlayerPropsAdapter(
        client=httpx.AsyncClient(base_url=BASE_URL), api_key="test-key"
    )
    backend = InMemoryCacheBackend()
    caching = CachingAdapter(adapter, backend, ttl_seconds=60)

    async def _poll_one_game(game_id: str):
        # Each game's own worker loop advances through its cadence steps
        # sequentially, but all 13 games run concurrently with each other --
        # the realistic shape of Sunday-slate load, not one simultaneous
        # burst against a single key.
        results = []
        for _ in range(CALLS_PER_GAME):
            results.append(
                await caching.call(
                    "fetch_player_props", [game_id], response_model=PROPS_RESPONSE_MODEL
                )
            )
        return results

    start = time.monotonic()
    all_results = await asyncio.gather(*(_poll_one_game(gid) for gid in _game_ids()))
    elapsed = time.monotonic() - start

    assert len(all_results) == GAME_COUNT
    for per_game_results in all_results:
        assert len(per_game_results) == CALLS_PER_GAME
        assert all(isinstance(r, AdapterResponse) for r in per_game_results)

    # Cache boundary should collapse each game's 18 identical sequential
    # calls down to 1 real vendor call per game -- proving cache hit rate
    # matches expected TTL behavior under realistic cadence volume (Phase
    # 3's own AC), not just under a single isolated call.
    assert respx.calls.call_count == GAME_COUNT
    hits = sum(r.from_cache for per_game_results in all_results for r in per_game_results)
    misses = sum(not r.from_cache for per_game_results in all_results for r in per_game_results)
    assert misses == GAME_COUNT
    assert hits == GAME_COUNT * (CALLS_PER_GAME - 1)

    # Not a hard perf assertion against real infra (that's deferred) -- a
    # sanity bound that our own pipeline doesn't pathologically stall under
    # this volume.
    assert elapsed < 5.0


@pytest.mark.asyncio
@respx.mock
async def test_concurrent_identical_requests_before_first_completes():
    """A real finding surfaced by this load test, not swept under the rug:
    `CachingAdapter` (built in 3A, already closed/signed off) uses a plain
    cache-aside strategy with no in-flight-request coalescing. Truly
    simultaneous first-requests for the same key (e.g. the Odds Worker and
    Pregame Worker both waking at the same instant for the same game) each
    independently miss and each independently call the underlying adapter,
    rather than the second waiting on the first's in-flight result. This
    test documents the actual current behavior rather than asserting an
    aspirational one -- flagged in the evidence report as a real gap for
    Milestone 3D (Redis, where single-flight/locking is the natural fix),
    not silently fixed here since it's outside 3B's scope."""
    call_count = {"n": 0}
    route = respx.get(f"{BASE_URL}/v4/sports/americanfootball_nfl/odds")

    async def _slow_response(request):
        call_count["n"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=load("bulk_odds_multi_game.json"))

    route.mock(side_effect=_slow_response)

    adapter = TheOddsApiOddsAdapter(client=httpx.AsyncClient(base_url=BASE_URL), api_key="test-key")
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=30)

    async def _call():
        return await caching.call(
            "fetch_odds",
            ["e912304de2b25f2879b0293fd6a48ef4"],
            response_model=AdapterResponse[list[OddsLine]],
        )

    results = await asyncio.gather(*(_call() for _ in range(5)))

    assert call_count["n"] == 5  # documents current (3A) behavior: no coalescing
    assert all(not r.from_cache for r in results)
