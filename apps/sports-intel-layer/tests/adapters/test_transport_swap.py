"""Extends 3A's vendor-swap acceptance test
(test_cache_boundary.py::test_swapping_the_underlying_adapter_requires_no_caller_change)
to cover the real thing, not just two fakes: swapping between a fake
adapter and the real, fixture-backed `TheOddsApiOddsAdapter` requires zero
change to caller-side code. This is the concrete version of "no downstream
caller can tell whether the adapter was backed by the fixture transport or
the future real HTTP transport" -- the only thing that ever differs below
is which adapter instance gets constructed, never `_get_odds` itself.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.models import AdapterResponse, OddsLine
from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from tests.adapters.fakes import FakeOddsAdapterV1
from tests.adapters.the_odds_api_fixtures import load

ODDS_RESPONSE_MODEL = AdapterResponse[list[OddsLine]]
ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"


async def _get_odds(caching_adapter: CachingAdapter, game_external_id: str):
    """Caller-side code, written once against the interface -- identical
    regardless of which vendor (fake or real) sits behind the adapter."""
    return await caching_adapter.call(
        "fetch_odds", [game_external_id], response_model=ODDS_RESPONSE_MODEL
    )


@pytest.mark.asyncio
@respx.mock
async def test_swapping_fake_for_the_real_fixture_backed_adapter_requires_no_caller_change():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    backend = InMemoryCacheBackend()

    caching_fake = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    fake_result = await _get_odds(caching_fake, "game-1")
    assert fake_result.source == "fake_provider_v1"
    assert fake_result.value[0].sportsbook == "fakebook"

    real_adapter = TheOddsApiOddsAdapter(
        client=httpx.AsyncClient(base_url="https://api.the-odds-api.com"),
        api_key="test-key",
    )
    caching_real = CachingAdapter(real_adapter, backend, ttl_seconds=60)
    real_result = await _get_odds(caching_real, GAME_CHIEFS_RAVENS)
    assert real_result.source == "the_odds_api"
    assert real_result.value[0].sportsbook in {"draftkings", "fanduel"}

    # Same call site, same response envelope type, same downstream shape --
    # the only diff between the two blocks above is which adapter instance
    # was constructed.
    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(real_result, AdapterResponse)
