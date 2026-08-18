"""Scenario tests for WeatherAPIWeatherAdapter (Phase 3C-i, approved
2026-08-11). Same fixture-first discipline as Phase 3B: multi-scenario
fixtures, real ProviderError translation, cache boundary re-exercised
against the real adapter, vendor/transport swap proof. No persistence
test -- Mac's explicit 3C scope boundary stops at the normalized-model/
cache boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, WeatherConditions
from app.adapters.providers.weatherapi import WeatherAPIWeatherAdapter
from tests.adapters.fakes import FakeWeatherAdapter
from tests.adapters.weatherapi_fixtures import load

BASE_URL = "https://api.weatherapi.com"
FORECAST_URL = f"{BASE_URL}/v1/forecast.json"
GAME_ID = "e912304de2b25f2879b0293fd6a48ef4"
KICKOFF = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)  # between the 12:00/13:00 fixture hours


def _adapter(location: str = "Arrowhead Stadium") -> WeatherAPIWeatherAdapter:
    return WeatherAPIWeatherAdapter(
        client=httpx.AsyncClient(base_url=BASE_URL),
        api_key="test-key",
        location_for_game=lambda _game_id: location,
    )


@pytest.mark.asyncio
@respx.mock
async def test_picks_the_forecast_hour_closest_to_kickoff():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))
    adapter = _adapter()
    response = await adapter.fetch_weather(GAME_ID, KICKOFF)

    assert isinstance(response, AdapterResponse)
    assert response.source == "weatherapi"
    assert response.value.game_external_id == GAME_ID
    # 12:30 kickoff is exactly between 12:00 (72.0F) and 13:00 (73.5F) --
    # 12:00 comes first in the fixture and both are equidistant, so the
    # first-seen minimum wins (documents actual tie-breaking behavior).
    assert response.value.temperature_f == 72.0
    assert response.value.is_dome is None  # no vendor knows this -- see adapter docstring (Phase 3E-6)
    assert response.provider_reported_at is not None


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_current_when_kickoff_outside_forecast_window():
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200, json=load("forecast_outside_window_falls_back_to_current.json")
        )
    )
    adapter = _adapter()
    far_future_kickoff = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)
    response = await adapter.fetch_weather(GAME_ID, far_future_kickoff)

    assert response.value.temperature_f == 68.0
    assert response.value.conditions == "Light rain"


@pytest.mark.asyncio
@respx.mock
async def test_malformed_forecast_raises_provider_data_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=load("forecast_malformed.json")))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, text="not json"))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(401, json={"error": {"code": 1002, "message": "no key"}}))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_400_with_auth_error_code_raises_provider_auth_error():
    """WeatherAPI's documented quirk (ASSUMED): auth problems can surface
    as HTTP 400 with an error.code, not a clean 401 -- this is the whole
    reason the adapter inspects the body on a 400."""
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(400, json=load("error_400_bad_key.json")))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_400_without_auth_error_code_raises_provider_data_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(400, json=load("error_400_bad_location.json")))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(429))
    adapter = _adapter()
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_timeout_raises_provider_unavailable_error():
    respx.get(FORECAST_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_weather(GAME_ID, KICKOFF)


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_avoids_a_second_http_call():
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))
    adapter = _adapter()
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=900)

    first = await caching.call(
        "fetch_weather", GAME_ID, KICKOFF, response_model=AdapterResponse[WeatherConditions]
    )
    second = await caching.call(
        "fetch_weather", GAME_ID, KICKOFF, response_model=AdapterResponse[WeatherConditions]
    )

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True


@pytest.mark.asyncio
@respx.mock
async def test_swapping_fake_for_the_real_fixture_backed_adapter_requires_no_caller_change():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=load("forecast_normal.json")))
    backend = InMemoryCacheBackend()

    async def _get_weather(caching_adapter: CachingAdapter):
        return await caching_adapter.call(
            "fetch_weather", GAME_ID, KICKOFF, response_model=AdapterResponse[WeatherConditions]
        )

    caching_fake = CachingAdapter(FakeWeatherAdapter(), backend, ttl_seconds=900)
    fake_result = await _get_weather(caching_fake)
    assert fake_result.source == "fake_weather_provider"

    caching_real = CachingAdapter(_adapter(), backend, ttl_seconds=900)
    real_result = await _get_weather(caching_real)
    assert real_result.source == "weatherapi"

    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(real_result, AdapterResponse)
