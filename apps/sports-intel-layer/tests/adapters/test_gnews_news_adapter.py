"""Scenario tests for GNewsNewsAdapter (Phase 8.0.5, Data Activation Pass 1,
2026-09-07). Mirrors `test_newsapi_news_adapter.py`'s exact coverage shape --
same interface, same error taxonomy, a different real vendor behind it.
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
from app.adapters.providers.gnews import GNewsNewsAdapter

BASE_URL = "https://gnews.io"
SEARCH_URL = f"{BASE_URL}/api/v4/search"
RESPONSE_MODEL = AdapterResponse[list[NewsArticle]]

_ARTICLES_NORMAL = {
    "totalArticles": 2,
    "articles": [
        {
            "id": "a1",
            "title": "Chiefs sign veteran receiver ahead of Week 2",
            "description": "The Chiefs added depth at receiver.",
            "content": "Full article body...",
            "url": "https://example.com/a1",
            "image": "https://example.com/a1.jpg",
            "publishedAt": "2026-09-07T12:00:00Z",
            "lang": "en",
            "source": {"id": "espn", "name": "ESPN", "url": "https://espn.com", "country": "us"},
        },
        {
            "id": "a2",
            "title": "Chiefs injury report ahead of matchup",
            "description": "Two starters listed as questionable.",
            "content": None,
            "url": "https://example.com/a2",
            "image": None,
            "publishedAt": "2026-09-07T09:30:00Z",
            "lang": "en",
            "source": {"id": None, "name": "Local Sports Wire", "url": "https://example.com", "country": "us"},
        },
    ],
}

_ARTICLES_EMPTY = {"totalArticles": 0, "articles": []}

_ARTICLES_MALFORMED = {"totalArticles": 1, "articles": [{"title": "Missing url and publishedAt"}]}


def _adapter() -> GNewsNewsAdapter:
    return GNewsNewsAdapter(client=httpx.AsyncClient(base_url=BASE_URL), api_key="test-key")


@pytest.mark.asyncio
@respx.mock
async def test_multi_source_articles_normalize_correctly():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_ARTICLES_NORMAL))
    adapter = _adapter()
    response = await adapter.fetch_news("Chiefs")

    assert isinstance(response, AdapterResponse)
    assert response.source == "gnews"
    assert len(response.value) == 2

    sources = {a.source for a in response.value}
    assert sources == {"ESPN", "Local Sports Wire"}

    espn_article = next(a for a in response.value if a.source == "ESPN")
    assert espn_article.headline == "Chiefs sign veteran receiver ahead of Week 2"
    assert espn_article.related_teams == ["Chiefs"]
    assert response.provider_reported_at is not None


@pytest.mark.asyncio
@respx.mock
async def test_null_source_id_and_content_do_not_crash_normalization():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_ARTICLES_NORMAL))
    adapter = _adapter()
    response = await adapter.fetch_news()
    assert len(response.value) == 2
    assert all(a.related_teams == [] for a in response.value)  # no team filter this time


@pytest.mark.asyncio
@respx.mock
async def test_empty_results_produce_an_empty_list_not_a_crash():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_ARTICLES_EMPTY))
    adapter = _adapter()
    response = await adapter.fetch_news("Jaguars")
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_malformed_article_raises_provider_data_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_ARTICLES_MALFORMED))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, text="not json"))
    adapter = _adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(401))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_403_raises_provider_auth_error():
    # GNews's own documented behavior for an invalid/exhausted key on some
    # plans -- ASSUMED, not independently re-verified live this pass.
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(403))
    adapter = _adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(429))
    adapter = _adapter()
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_unavailable_error():
    respx.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    adapter = _adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_news()


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_avoids_a_second_http_call():
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_ARTICLES_NORMAL))
    adapter = _adapter()
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=900)

    first = await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)
    second = await caching.call("fetch_news", "Chiefs", response_model=RESPONSE_MODEL)

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True
