"""Tests for app.persistence.news_article_history (2026 Data
Preservation Readiness Plan, pre-9/9 minimum implementation).

Covers the one property this module exists to prove: a re-sighted
article does not produce a duplicate row -- proven both at the call-shape
level (the correct on_conflict/Prefer headers are sent) and, via a
stateful fake table, at the actual insert-once-per-(provider_name,
article_url) semantic level, mirroring test_odds_cadence_persistence.py's
own stateful-mock convention for proving a real DB-level property from a
Python-level test.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, NewsArticle
from app.persistence.news_article_history import PersistenceError, write_news_article_history

SUPABASE_URL = "https://test-project.supabase.co"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _article(url: str, headline: str = "Some Headline") -> NewsArticle:
    return NewsArticle(
        headline=headline,
        url=url,
        source="Heavy.",
        published_at=datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
        summary="A summary.",
        related_teams=["Kansas City Chiefs"],
    )


@pytest.mark.asyncio
@respx.mock
async def test_writes_correct_on_conflict_and_ignore_duplicates_headers(monkeypatch):
    _headers_env(monkeypatch)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(
        return_value=httpx.Response(201, json=[{"id": "row-1"}])
    )

    response = AdapterResponse(value=[_article("https://heavy.com/a")], source="newsapi")
    count = await write_news_article_history(response, team_id="team-kc")

    assert count == 1
    call = route.calls[0]
    assert call.request.url.params.get("on_conflict") == "provider_name,article_url"
    assert call.request.headers["prefer"] == "resolution=ignore-duplicates,return=representation"


@pytest.mark.asyncio
@respx.mock
async def test_empty_articles_writes_nothing(monkeypatch):
    _headers_env(monkeypatch)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(201, json=[]))

    count = await write_news_article_history(AdapterResponse(value=[], source="newsapi"), team_id="team-kc")

    assert count == 0
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_second_sighting_of_the_same_article_does_not_duplicate(monkeypatch):
    """Stateful fake table: enforces the real (provider_name, article_url)
    uniqueness constraint in Python, proving the actual dedup property a
    plain respx return-value mock can't demonstrate on its own."""
    _headers_env(monkeypatch)
    seen: set[tuple[str, str]] = set()

    def _respond(request: httpx.Request) -> httpx.Response:
        import json

        rows = json.loads(request.content)
        inserted = []
        for row in rows:
            key = (row["provider_name"], row["article_url"])
            if key in seen:
                continue  # ignore-duplicates: silently skipped, not an error
            seen.add(key)
            inserted.append(row)
        return httpx.Response(201, json=inserted)

    respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(side_effect=_respond)

    article = _article("https://heavy.com/same-article")
    response = AdapterResponse(value=[article], source="newsapi")

    first_count = await write_news_article_history(response, team_id="team-kc")
    second_count = await write_news_article_history(response, team_id="team-kc")  # re-sighted next cycle

    assert first_count == 1
    assert second_count == 0  # no duplicate row -- ingested_at of the original is never touched
    assert len(seen) == 1


@pytest.mark.asyncio
@respx.mock
async def test_related_team_ids_scoped_to_the_fetching_team(monkeypatch):
    _headers_env(monkeypatch)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(
        return_value=httpx.Response(201, json=[{"id": "row-1"}])
    )

    response = AdapterResponse(value=[_article("https://heavy.com/a")], source="gnews")
    await write_news_article_history(response, team_id="team-eagles")

    import json as _json

    row = _json.loads(route.calls[0].request.content)[0]
    assert row["related_team_ids"] == ["team-eagles"]
    assert row["related_player_ids"] is None  # NewsArticle has no player field today -- not fabricated
    assert row["provider_name"] == "gnews"
    assert row["source_name"] == "Heavy."


@pytest.mark.asyncio
@respx.mock
async def test_insert_failure_raises_persistence_error(monkeypatch):
    _headers_env(monkeypatch)
    respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(PersistenceError):
        await write_news_article_history(
            AdapterResponse(value=[_article("https://heavy.com/a")], source="newsapi"), team_id="team-kc"
        )
