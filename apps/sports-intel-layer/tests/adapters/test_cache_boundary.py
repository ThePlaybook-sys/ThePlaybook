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
