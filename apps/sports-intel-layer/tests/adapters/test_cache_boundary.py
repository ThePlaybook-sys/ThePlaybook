import pytest

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.models import AdapterResponse, OddsLine
from tests.adapters.fakes import FakeOddsAdapterV1, FakeOddsAdapterV2

ODDS_RESPONSE_MODEL = AdapterResponse[list[OddsLine]]


async def _get_odds(caching_adapter: CachingAdapter):
    """Caller-side code, written once against the interface -- this
    function never changes when the underlying adapter is swapped below.
    That's the actual proof of Phase 3's adapter-pattern acceptance
    criterion, not just an assertion about it."""
    return await caching_adapter.call("fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL)


@pytest.mark.asyncio
async def test_cache_miss_calls_adapter_and_stores_result():
    backend = InMemoryCacheBackend()
    adapter = FakeOddsAdapterV1()
    caching = CachingAdapter(adapter, backend, ttl_seconds=60)

    response = await _get_odds(caching)
    assert response.from_cache is False
    assert response.value[0].sportsbook == "fakebook"
    # Phase 3F acceptance closure: first fetch = miss, one set attempt,
    # backend has no failure mode so no errors.
    assert caching.metrics.misses == 1
    assert caching.metrics.hits == 0
    assert caching.metrics.sets == 1
    assert caching.errors == 0


@pytest.mark.asyncio
async def test_cache_hit_avoids_calling_underlying_adapter():
    backend = InMemoryCacheBackend()
    adapter = FakeOddsAdapterV1()
    caching = CachingAdapter(adapter, backend, ttl_seconds=60)

    first = await _get_odds(caching)
    assert first.from_cache is False

    # Swap in a broken adapter under the *same* provider_name/cache key --
    # if this second call still succeeds and comes from cache, the cache
    # actually served the second request rather than re-fetching.
    broken_adapter = FakeOddsAdapterV1(fail=True)
    broken_adapter.provider_name = adapter.provider_name
    caching_with_broken_adapter = CachingAdapter(broken_adapter, backend, ttl_seconds=60)
    second = await _get_odds(caching_with_broken_adapter)
    assert second.from_cache is True
    assert second.value[0].sportsbook == "fakebook"
    # repeated within TTL = hit -- on the instance that actually served it.
    assert caching_with_broken_adapter.metrics.hits == 1
    assert caching_with_broken_adapter.metrics.misses == 0
    # Metrics are per-CachingAdapter-instance, not shared via the backend --
    # the first instance's own counters are untouched by the second call.
    assert caching.metrics.hits == 0
    assert caching.metrics.misses == 1


@pytest.mark.asyncio
async def test_ttl_expiry_causes_a_fresh_fetch():
    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = FakeClock()
    backend = InMemoryCacheBackend(clock=clock)
    adapter = FakeOddsAdapterV1()
    caching = CachingAdapter(adapter, backend, ttl_seconds=10)

    first = await _get_odds(caching)
    assert first.from_cache is False

    clock.now += 5
    second = await _get_odds(caching)
    assert second.from_cache is True  # still within TTL

    clock.now += 6  # 11s total elapsed, past the 10s TTL
    third = await _get_odds(caching)
    assert third.from_cache is False  # expired, real fetch happened again

    # Cumulative on the one shared instance: miss, hit, miss (expired).
    assert caching.metrics.misses == 2
    assert caching.metrics.hits == 1
    assert caching.metrics.sets == 2
    assert caching.metrics.hit_rate == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_swapping_the_underlying_adapter_requires_no_caller_change():
    """This IS Phase 3's actual acceptance criterion: "switching a provider
    adapter's underlying implementation... requires no changes outside the
    Sports Intelligence Layer itself." `_get_odds` above stands in for
    "calling code outside the Sports Intelligence Layer" -- it is
    byte-for-byte identical in both calls below; only the adapter instance
    passed into CachingAdapter changes."""
    backend = InMemoryCacheBackend()

    caching_v1 = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    result_v1 = await _get_odds(caching_v1)
    assert result_v1.value[0].sportsbook == "fakebook"

    # Different provider_name means this doesn't collide with the v1 cache
    # entry above -- a real vendor swap in production would also get a
    # fresh cache under the new provider's name, not silently reuse stale
    # data cached under the old vendor's key.
    caching_v2 = CachingAdapter(FakeOddsAdapterV2(), backend, ttl_seconds=60)
    result_v2 = await _get_odds(caching_v2)
    assert result_v2.value[0].sportsbook == "anotherbook"


@pytest.mark.asyncio
async def test_metrics_never_change_cache_semantics():
    """Instrumenting hits/misses/sets must not alter what gets cached or
    returned -- same functional behavior as before metrics existed,
    proven by re-running the miss->hit->expiry sequence and checking the
    actual returned values, not just counters."""
    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = FakeClock()
    backend = InMemoryCacheBackend(clock=clock)
    adapter = FakeOddsAdapterV1()
    caching = CachingAdapter(adapter, backend, ttl_seconds=10)

    first = await _get_odds(caching)
    clock.now += 5
    second = await _get_odds(caching)
    clock.now += 6
    third = await _get_odds(caching)

    assert first.value[0].sportsbook == second.value[0].sportsbook == third.value[0].sportsbook == "fakebook"
    assert (first.from_cache, second.from_cache, third.from_cache) == (False, True, False)


@pytest.mark.asyncio
async def test_different_categories_maintain_independent_metrics():
    """Each CachingAdapter instance owns its own CacheMetrics -- the
    architecture already gives one instance per category (every worker
    constructs its own), so independence is inherent, not a special case
    to build. Proven here with two categories sharing one backend."""
    backend = InMemoryCacheBackend()
    odds_caching = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    props_caching = CachingAdapter(FakeOddsAdapterV2(), backend, ttl_seconds=300)

    await odds_caching.call("fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL)
    await odds_caching.call("fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL)
    await props_caching.call("fetch_odds", ["game-2"], response_model=ODDS_RESPONSE_MODEL)

    assert odds_caching.metrics.misses == 1
    assert odds_caching.metrics.hits == 1
    assert props_caching.metrics.misses == 1
    assert props_caching.metrics.hits == 0


def test_hit_rate_is_none_with_no_data_not_a_fabricated_percentage():
    from app.adapters.cache import CacheMetrics

    empty = CacheMetrics()
    assert empty.hit_rate is None  # never a misleading 0.0 or 100% from zero samples

    some_data = CacheMetrics(hits=3, misses=1)
    assert some_data.hit_rate == pytest.approx(0.75)


def test_in_memory_backend_never_reports_errors():
    """InMemoryCacheBackend has no failure mode -- errors stays 0 no
    matter what, unlike RedisCacheBackend (see test_redis_cache_backend.py)."""
    backend = InMemoryCacheBackend()
    assert backend.errors == 0
