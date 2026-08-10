"""Provenance contract tests, added per Mac's explicit verification request
(2026-08-10): does AdapterResponse actually carry enough standardized
metadata to later reconstruct why a recommendation used the information it
did, without leaking provider-specific fields into normalized models?

These specifically target the one real gap that check surfaced:
provider_reported_at (the provider's own stated timestamp for the
underlying data) was missing and conflated with fetched_at (when we
polled). Each test proves one part of the correction, not just asserts it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.models import AdapterResponse, OddsLine
from tests.adapters.fakes import FakeOddsAdapterV1, FakeOddsAdapterV2

ODDS_RESPONSE_MODEL = AdapterResponse[list[OddsLine]]


@pytest.mark.asyncio
async def test_provider_reported_at_survives_normalization_when_supplied():
    supplied = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    adapter = FakeOddsAdapterV1(provider_reported_at=supplied)

    response = await adapter.fetch_odds(["game-1"])

    assert response.provider_reported_at == supplied


@pytest.mark.asyncio
async def test_provider_reported_at_remains_null_when_not_supplied():
    adapter = FakeOddsAdapterV1()  # no provider_reported_at given

    response = await adapter.fetch_odds(["game-1"])

    assert response.provider_reported_at is None


@pytest.mark.asyncio
async def test_fetched_at_is_independently_generated_from_provider_reported_at():
    # Deliberately far in the past, so a bug that conflated the two fields
    # (e.g. defaulting provider_reported_at to fetched_at) would be obvious
    # rather than accidentally passing due to near-simultaneous timestamps.
    provider_time = datetime.now(timezone.utc) - timedelta(hours=6)
    adapter = FakeOddsAdapterV1(provider_reported_at=provider_time)

    response = await adapter.fetch_odds(["game-1"])

    assert response.provider_reported_at == provider_time
    assert response.fetched_at != provider_time
    # fetched_at should reflect "now" (the actual call), not the supplied
    # provider timestamp -- allow a generous window for test execution time.
    assert abs((response.fetched_at - datetime.now(timezone.utc)).total_seconds()) < 5


@pytest.mark.asyncio
async def test_provider_reported_at_survives_a_cache_round_trip():
    """Both timestamps must survive JSON serialization through the cache
    boundary, not just direct construction -- a cache hit is exactly the
    path where a field could silently get dropped or overwritten."""
    supplied = datetime(2026, 8, 10, 9, 30, 0, tzinfo=timezone.utc)
    backend = InMemoryCacheBackend()
    adapter = FakeOddsAdapterV1(provider_reported_at=supplied)
    caching = CachingAdapter(adapter, backend, ttl_seconds=60)

    first = await caching.call("fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL)
    assert first.from_cache is False
    assert first.provider_reported_at == supplied

    second = await caching.call("fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL)
    assert second.from_cache is True
    assert second.provider_reported_at == supplied
    assert second.fetched_at == first.fetched_at  # original fetch time preserved, not "now"


@pytest.mark.asyncio
async def test_vendor_swap_still_requires_no_caller_change_after_the_correction():
    """Re-proves Phase 3A's core acceptance criterion after the contract
    change above -- adding provider_reported_at must not have reintroduced
    any coupling between caller code and a specific adapter implementation."""

    async def get_odds(caching_adapter: CachingAdapter):
        return await caching_adapter.call(
            "fetch_odds", ["game-1"], response_model=ODDS_RESPONSE_MODEL
        )

    backend = InMemoryCacheBackend()

    result_v1 = await get_odds(CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60))
    assert result_v1.value[0].sportsbook == "fakebook"

    result_v2 = await get_odds(CachingAdapter(FakeOddsAdapterV2(), backend, ttl_seconds=60))
    assert result_v2.value[0].sportsbook == "anotherbook"
