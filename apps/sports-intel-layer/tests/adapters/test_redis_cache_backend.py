"""Tests for RedisCacheBackend (Phase 3D). Uses fakeredis -- an in-process
Redis-protocol emulator -- so the full implementation is proven without a
real Redis server. No hosted Redis exists yet (deferred to Phase 3E, see
PROGRESS.md); this file is the evidence that the *code* is complete and
correct independent of that deferral.

Every existing CachingAdapter-compatibility test elsewhere in this suite
(Odds/Weather/News/SportsDataIO) already runs against InMemoryCacheBackend
-- rather than duplicate every one of those scenarios, this file proves
RedisCacheBackend is a drop-in replacement by re-running one representative
scenario per adapter category through RedisCacheBackend specifically,
plus RedisCacheBackend's own unit-level behavior (which InMemoryCacheBackend
doesn't need, since it can't fail: connection errors, byte decoding,
malformed-value passthrough).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import fakeredis.aioredis
import httpx
import pytest
import respx
from redis.exceptions import ConnectionError as RedisConnectionError

from app.adapters.cache import (
    CATEGORY_TTL_SECONDS,
    CachingAdapter,
    RedisCacheBackend,
    cache_key,
)
from app.adapters.models import AdapterResponse, NewsArticle, OddsLine, TeamStatLine, WeatherConditions
from app.adapters.providers.newsapi import NewsAPINewsAdapter
from app.adapters.providers.sportsdataio import SportsDataIOTeamStatsAdapter
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from app.adapters.providers.weatherapi import WeatherAPIWeatherAdapter
from tests.adapters.fakes import FakeOddsAdapterV1
from tests.adapters.newsapi_fixtures import load as load_news
from tests.adapters.sportsdataio_fixtures import load as load_sdio
from tests.adapters.the_odds_api_fixtures import load as load_odds
from tests.adapters.weatherapi_fixtures import load as load_weather


def _fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


# ============================================================
# RedisCacheBackend -- direct unit-level behavior
# ============================================================

@pytest.mark.asyncio
async def test_set_then_get_returns_the_value():
    backend = RedisCacheBackend(_fake_redis())
    await backend.set("k1", "hello", 60)
    assert await backend.get("k1") == "hello"


@pytest.mark.asyncio
async def test_get_on_missing_key_returns_none():
    backend = RedisCacheBackend(_fake_redis())
    assert await backend.get("never-set") is None


@pytest.mark.asyncio
async def test_ttl_expiry_causes_a_miss():
    backend = RedisCacheBackend(_fake_redis())
    await backend.set("short-lived", "value", 1)
    assert await backend.get("short-lived") == "value"
    await asyncio.sleep(1.2)
    assert await backend.get("short-lived") is None


@pytest.mark.asyncio
async def test_serialization_round_trip_preserves_json_content():
    """CachingAdapter stores AdapterResponse.model_dump_json() -- prove a
    real JSON payload survives the bytes-in/str-out round trip exactly,
    not just a plain short string."""
    backend = RedisCacheBackend(_fake_redis())
    response = AdapterResponse(value=[OddsLine(
        game_external_id="g1", home_team="Fake Home", away_team="Fake Away",
        commence_time=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        sportsbook="fakebook", market_type="moneyline",
        line_data={"home": -110, "away": -110, "nested": {"a": [1, 2, 3]}},
    )], source="the_odds_api")
    payload = response.model_dump_json()
    await backend.set("k", payload, 60)
    round_tripped = await backend.get("k")
    assert round_tripped == payload
    restored = AdapterResponse[list[OddsLine]].model_validate_json(round_tripped)
    assert restored.value[0].line_data["nested"]["a"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_malformed_cached_value_is_returned_as_is_not_swallowed():
    """RedisCacheBackend is a pure string store -- it must not attempt to
    validate/interpret content. A corrupted value is returned faithfully;
    it's CachingAdapter's/the response model's job to reject it, not this
    backend's."""
    backend = RedisCacheBackend(_fake_redis())
    await backend.set("corrupt", "{not valid json", 60)
    assert await backend.get("corrupt") == "{not valid json"


@pytest.mark.asyncio
async def test_corrupted_cache_value_surfaces_as_a_validation_error_via_caching_adapter():
    """Proves the two layers compose correctly: RedisCacheBackend faithfully
    returns a corrupted value, and CachingAdapter (unchanged) fails loudly
    trying to parse it -- exactly like it would with any other backend."""
    backend = RedisCacheBackend(_fake_redis())
    key = cache_key("fake_provider_v1", "fetch_odds", ["game-1"])
    await backend.set(key, "{not valid json", 60)
    caching = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    with pytest.raises(Exception):  # pydantic ValidationError
        await caching.call("fetch_odds", ["game-1"], response_model=AdapterResponse[list[OddsLine]])


@pytest.mark.asyncio
async def test_connection_failure_on_get_is_treated_as_a_cache_miss_not_raised():
    """Fail-open: a broken Redis must not crash the caller. Simulated via
    a client stub whose get() raises the library's own ConnectionError."""
    class _BrokenClient:
        async def get(self, key):
            raise RedisConnectionError("simulated connection failure")

        async def set(self, key, value, ex=None):
            raise RedisConnectionError("simulated connection failure")

    backend = RedisCacheBackend(_BrokenClient())
    assert await backend.get("anything") is None  # no exception raised


@pytest.mark.asyncio
async def test_connection_failure_on_set_is_swallowed_not_raised():
    class _BrokenClient:
        async def get(self, key):
            raise RedisConnectionError("simulated connection failure")

        async def set(self, key, value, ex=None):
            raise RedisConnectionError("simulated connection failure")

    backend = RedisCacheBackend(_BrokenClient())
    await backend.set("k", "v", 60)  # must not raise


@pytest.mark.asyncio
async def test_caching_adapter_falls_through_to_real_call_when_redis_is_down():
    """End-to-end proof of graceful degradation at the CachingAdapter
    boundary specifically: with a broken Redis, every call is a miss, so
    the wrapped adapter is called directly every time -- degraded
    (uncached) but functioning, not crashed."""
    class _BrokenClient:
        async def get(self, key):
            raise RedisConnectionError("down")

        async def set(self, key, value, ex=None):
            raise RedisConnectionError("down")

    backend = RedisCacheBackend(_BrokenClient())
    caching = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    response = await caching.call("fetch_odds", ["game-1"], response_model=AdapterResponse[list[OddsLine]])
    assert response.from_cache is False
    assert response.value[0].sportsbook == "fakebook"


# ============================================================
# Category-specific TTL behavior
# ============================================================

def test_category_ttl_mapping_has_distinct_values_not_one_global_default():
    assert CATEGORY_TTL_SECONDS["odds"] != CATEGORY_TTL_SECONDS["weather"]
    assert CATEGORY_TTL_SECONDS["weather"] == CATEGORY_TTL_SECONDS["news"] == 900
    assert len(set(CATEGORY_TTL_SECONDS.values())) > 1  # not one flat number for everything


@pytest.mark.asyncio
async def test_two_categories_through_the_same_backend_expire_independently():
    """Proves RedisCacheBackend actually honors a different ttl_seconds
    per call, not a fixed value baked into the class -- the real
    mechanism category-appropriate TTLs depend on."""
    backend = RedisCacheBackend(_fake_redis())
    await backend.set("short", "value-a", 1)
    await backend.set("long", "value-b", 60)

    await asyncio.sleep(1.2)
    assert await backend.get("short") is None  # short TTL expired
    assert await backend.get("long") == "value-b"  # long TTL still alive


# ============================================================
# CachingAdapter compatibility -- drop-in proof per adapter category
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_odds_adapter_cache_compatible_with_redis_backend():
    respx.get("https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds").mock(
        return_value=httpx.Response(200, json=load_odds("bulk_odds_multi_game.json"))
    )
    adapter = TheOddsApiOddsAdapter(
        client=httpx.AsyncClient(base_url="https://api.the-odds-api.com"), api_key="test-key"
    )
    caching = CachingAdapter(adapter, RedisCacheBackend(_fake_redis()), ttl_seconds=CATEGORY_TTL_SECONDS["odds"])
    response_model = AdapterResponse[list[OddsLine]]

    first = await caching.call("fetch_odds", ["e912304de2b25f2879b0293fd6a48ef4"], response_model=response_model)
    second = await caching.call("fetch_odds", ["e912304de2b25f2879b0293fd6a48ef4"], response_model=response_model)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.value[0].sportsbook == first.value[0].sportsbook


@pytest.mark.asyncio
@respx.mock
async def test_weather_adapter_cache_compatible_with_redis_backend():
    respx.get("https://api.weatherapi.com/v1/forecast.json").mock(
        return_value=httpx.Response(200, json=load_weather("forecast_normal.json"))
    )
    adapter = WeatherAPIWeatherAdapter(
        client=httpx.AsyncClient(base_url="https://api.weatherapi.com"),
        api_key="test-key",
        location_for_game=lambda _game_id: "Arrowhead Stadium",
    )
    caching = CachingAdapter(adapter, RedisCacheBackend(_fake_redis()), ttl_seconds=CATEGORY_TTL_SECONDS["weather"])
    response_model = AdapterResponse[WeatherConditions]
    from datetime import datetime, timezone
    kickoff = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)

    first = await caching.call("fetch_weather", "game-1", kickoff, response_model=response_model)
    second = await caching.call("fetch_weather", "game-1", kickoff, response_model=response_model)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.value.temperature_f == first.value.temperature_f


@pytest.mark.asyncio
@respx.mock
async def test_news_adapter_cache_compatible_with_redis_backend():
    respx.get("https://newsapi.org/v2/everything").mock(
        return_value=httpx.Response(200, json=load_news("articles_normal.json"))
    )
    adapter = NewsAPINewsAdapter(
        client=httpx.AsyncClient(base_url="https://newsapi.org"), api_key="test-key"
    )
    caching = CachingAdapter(adapter, RedisCacheBackend(_fake_redis()), ttl_seconds=CATEGORY_TTL_SECONDS["news"])
    response_model = AdapterResponse[list[NewsArticle]]

    first = await caching.call("fetch_news", None, response_model=response_model)
    second = await caching.call("fetch_news", None, response_model=response_model)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.value[0].headline == first.value[0].headline


@pytest.mark.asyncio
@respx.mock
async def test_sportsdataio_weekly_bulk_reuse_survives_redis_backend():
    """The specific behavior 3D exists to eventually make real
    cross-process: a second game from an already-cached week must not
    trigger a second provider call, proven here through RedisCacheBackend
    exactly as it was already proven through the adapter's own internal
    bulk cache (which also already accepts any CacheBackend)."""
    route = respx.get("https://api.sportsdata.io/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load_sdio("team_stats_week_bulk_normal.json"))
    )
    shared_backend = RedisCacheBackend(_fake_redis())
    adapter = SportsDataIOTeamStatsAdapter(
        client=httpx.AsyncClient(base_url="https://api.sportsdata.io"),
        api_key="test-key",
        season_week_for_game=lambda gid: {"202510122": ("2025REG", 1), "202510102": ("2025REG", 1)}[gid],
        cache_backend=shared_backend,  # the adapter's own internal week-bulk cache
    )
    first = await adapter.fetch_team_stats("202510122")
    second = await adapter.fetch_team_stats("202510102")

    assert route.call_count == 1  # one provider call served both games' weeks
    assert {line.team for line in first.value} == {"ARI", "NO"}
    assert {line.team for line in second.value} == {"ATL", "TB"}

    # And the outer per-call CachingAdapter layer works on top of it too.
    outer = CachingAdapter(adapter, shared_backend, ttl_seconds=CATEGORY_TTL_SECONDS["team_stats"])
    response_model = AdapterResponse[list[TeamStatLine]]
    outer_first = await outer.call("fetch_team_stats", "202510122", response_model=response_model)
    outer_second = await outer.call("fetch_team_stats", "202510122", response_model=response_model)
    assert outer_first.from_cache is False
    assert outer_second.from_cache is True


@pytest.mark.asyncio
async def test_swapping_inmemory_for_redis_backend_requires_no_caller_change():
    """The actual 3D acceptance proof: identical caller code
    (_get_odds-equivalent), only the backend instance changes."""
    from app.adapters.cache import InMemoryCacheBackend

    async def _get(caching_adapter: CachingAdapter):
        return await caching_adapter.call(
            "fetch_odds", ["game-1"], response_model=AdapterResponse[list[OddsLine]]
        )

    caching_inmemory = CachingAdapter(FakeOddsAdapterV1(), InMemoryCacheBackend(), ttl_seconds=60)
    inmemory_result = await _get(caching_inmemory)
    assert inmemory_result.from_cache is False

    caching_redis = CachingAdapter(FakeOddsAdapterV1(), RedisCacheBackend(_fake_redis()), ttl_seconds=60)
    redis_first = await _get(caching_redis)
    redis_second = await _get(caching_redis)
    assert redis_first.from_cache is False
    assert redis_second.from_cache is True
    assert redis_second.value[0].sportsbook == inmemory_result.value[0].sportsbook
