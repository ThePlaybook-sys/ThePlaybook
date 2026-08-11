"""Scenario tests for NewsAPINewsAdapter (Phase 3C-i, approved 2026-08-11).
Stops at the normalized-model/cache boundary per Mac's explicit 3C scope --
no persistence test, since no news persistence target exists yet (deferred
to Milestone F).
"""
from __future__ import annotations

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
from app.adapters.models import AdapterResponse, NewsArticle
from app.adapters.providers.newsapi import NewsAPINewsAdapter
from tests.adapters.fakes import FakeNewsAdapter
from tests.adapters.newsapi_fixtures import load

BASE_URL = "https://newsapi.org"
EVERYTHING_URL = f"{BASE_URL}/v2/everything"
RESPONSE_MODEL = AdapterResponse[list[NewsArticle]]


def _adapter() -> NewsAPINewsAdapter:
    return NewsAPINewsAdapter(client=httpx.AsyncClient(base_url=BASE_URL), api_key="test-key")


@pytest.mark.asyncio
@respx.mock
async def test_multi_source_articles_normalize_correctly():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_normal.json")))
    adapter = _adapter()
    response = await adapter.fetch_news("Chiefs")

    assert isinstance(response, AdapterResponse)
    assert response.source == "newsapi"
    assert len(response.value) == 3

    sources = {a.source for a in response.value}
    assert sources == {"ESPN", "Pro Football Talk", "Bleacher Report"}

    espn_article = next(a for a in response.value if a.source == "ESPN")
    assert espn_article.headline == "Chiefs, Ravens set for statement Week 2 matchup"
    assert espn_article.related_teams == ["Chiefs"]
    assert response.provider_reported_at is not None


@pytest.mark.asyncio
@respx.mock
async def test_null_source_id_and_author_do_not_crash_normalization():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_normal.json")))
    adapter = _adapter()
    response = await adapter.fetch_news()
    # a null source.id and null author are both present in the fixture --
    # normalization must not choke on either.
    assert len(response.value) == 3
    assert all(a.related_teams == [] for a in response.value)  # no team filter this time


@pytest.mark.asyncio
@respx.mock
async def test_empty_results_produce_an_empty_list_not_a_crash():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_empty.json")))
    adapter = _adapter()
    response = await adapter.fetch_news("Jaguars")
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_malformed_article_raises_provider_data_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_malformed.json")))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, text="not json"))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(401))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_400_bad_key_raises_provider_auth_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(400, json=load("error_400_bad_key.json")))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_400_rate_limited_code_raises_provider_rate_limit_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(400, json=load("error_400_rate_limited.json")))
    adapter = _adapter()
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_direct_429_raises_provider_rate_limit_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(429))
    adapter = _adapter()
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_unavailable_error():
    respx.get(EVERYTHING_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_avoids_a_second_http_call():
    route = respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_normal.json")))
    adapter = _adapter()
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=900)

    first = await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)
    second = await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True


@pytest.mark.asyncio
@respx.mock
async def test_cache_expiry_triggers_a_fresh_call():
    route = respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_normal.json")))
    adapter = _adapter()
    clock = {"t": 0.0}
    backend = InMemoryCacheBackend(clock=lambda: clock["t"])
    caching = CachingAdapter(adapter, backend, ttl_seconds=900)

    await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)
    clock["t"] += 901  # News tolerates minutes of staleness (Volume 2 §8), unlike odds
    third = await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)

    assert route.call_count == 2
    assert third.from_cache is False


@pytest.mark.asyncio
@respx.mock
async def test_swapping_fake_for_the_real_fixture_backed_adapter_requires_no_caller_change():
    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(200, json=load("articles_normal.json")))
    backend = InMemoryCacheBackend()

    async def _get_news(caching_adapter: CachingAdapter):
        return await caching_adapter.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)

    caching_fake = CachingAdapter(FakeNewsAdapter(), backend, ttl_seconds=900)
    fake_result = await _get_news(caching_fake)
    assert fake_result.source == "fake_news_provider"

    caching_real = CachingAdapter(_adapter(), backend, ttl_seconds=900)
    real_result = await _get_news(caching_real)
    assert real_result.source == "newsapi"

    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(real_result, AdapterResponse)
