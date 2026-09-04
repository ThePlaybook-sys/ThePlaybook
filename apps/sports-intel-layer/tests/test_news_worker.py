"""Orchestration tests for app.workers.news_worker (Phase 3E-7).

Every HTTP boundary -- Supabase and NewsAPI both -- is respx-mocked; no
real network, zero SportsDataIO/WeatherAPI calls (structurally impossible:
`run_news_worker`'s signature only ever accepts a supabase_client and a
newsapi_client).

Covers: normal team-scoped refresh, multiple articles, genuinely-no-news
(empty-but-fresh), provider failure preserving last-known-good, malformed
provider response isolation, two-teams-one-game combination + dedup,
unresolved team identity (no team_provider_ids mapping), a response
article failing the related_teams self-consistency check, the
never-calls-unscoped-query guarantee (no league-wide/unassigned path),
player-level news being structurally unsupported, cadence boundaries (due/
not-due/first-run), cache hit/stale, upsert-not-accumulate rerun
semantics, the exact daily_game_intelligence write shape (game_id + news
only), and timezone-aware publication timestamps surviving persistence.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.adapters.models import NewsArticle
from app.workers.news_worker import run_news_worker
from tests.adapters.newsapi_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
NEWSAPI_URL = "https://newsapi.org"
EVERYTHING_URL = f"{NEWSAPI_URL}/v2/everything"

TEAM_KC = "team-kc"
TEAM_BAL = "team-bal"
TEAM_SEA = "team-sea"

NAME_KC = "Kansas City Chiefs"
NAME_BAL = "Baltimore Ravens"
NAME_SEA = "Seattle Seahawks"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, game_id: str, home_team: str, away_team: str, scheduled_start: str) -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": home_team,
        "away_team": away_team,
        "scheduled_start": scheduled_start,
        "stadium": "Arrowhead Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 2,
        "venue_lat": 39.0489,
        "venue_long": -94.4839,
        "venue_type": "outdoor",
    }


def _mock_games(games: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_team_provider_ids(mapping: dict[str, str]):
    """mapping: abbreviation -> team_id, only for abbreviations WITH a mapping."""
    rows = [{"provider_team_id": abbrev, "team_id": team_id} for abbrev, team_id in mapping.items()]
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=rows))


def _mock_teams(mapping: dict[str, str]):
    """mapping: team_id -> canonical name."""
    rows = [{"id": team_id, "name": name} for team_id, name in mapping.items()]
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=rows))


def _mock_dgi_upsert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))


def _news_route():
    return respx.get(EVERYTHING_URL)


def _by_team_response(responses: dict[str, dict]):
    """respx side_effect: dispatches on the `q` query param's team-name prefix."""

    def _respond(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "")
        for team_name, body in responses.items():
            if q.startswith(team_name):
                return httpx.Response(200, json=body)
        return httpx.Response(200, json={"status": "ok", "totalResults": 0, "articles": []})

    return _respond


def _mock_news_article_history_insert():
    """2026 Data Preservation Readiness Plan (2026-09-04): every
    successful team fetch now also writes to news_article_history
    (app.persistence.news_article_history), alongside the existing
    daily_game_intelligence write -- mocked here, in the one shared
    execution helper every test in this file goes through, rather than
    in each test individually. `return_value=[]` (an empty PostgREST
    `ignore-duplicates` response body) is a safe default for tests that
    don't specifically assert on this route's own call count."""
    return respx.post(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(
        return_value=httpx.Response(201, json=[])
    )


async def _run(*, now, last_polled_at=None, cache_backend=None):
    _mock_news_article_history_insert()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=NEWSAPI_URL
    ) as newsapi_client:
        return await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=newsapi_client,
            newsapi_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend or InMemoryCacheBackend(),
        )


def _standard_setup(*, game_id="game-1", scheduled_start="2026-09-14T17:00:00Z"):
    _mock_games([_game_row(game_id=game_id, home_team="KC", away_team="BAL", scheduled_start=scheduled_start)])
    _mock_team_provider_ids({"KC": TEAM_KC, "BAL": TEAM_BAL})
    _mock_teams({TEAM_KC: NAME_KC, TEAM_BAL: NAME_BAL})


NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


# ============================================================================
# Normal refresh, multiple articles
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_normal_refresh_writes_news_for_both_teams(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(side_effect=_by_team_response({NAME_KC: load("articles_normal.json")}))

    result = await _run(now=NOW)

    assert result.status == "success"
    assert result.teams_due == 2
    assert result.teams_fetched == 2
    assert result.games_updated == 1

    payloads = [_json.loads(call.request.content) for call in insert_route.calls]
    assert len(payloads) == 1
    assert payloads[0]["game_id"] == "game-1"
    assert len(payloads[0]["news"]["value"]) == 3  # KC's 3 articles; BAL's empty-fallback contributes 0
    assert payloads[0]["news"]["status"] == "fresh"
    assert payloads[0]["news"]["source"] == "newsapi"


@pytest.mark.asyncio
@respx.mock
async def test_multiple_news_items_all_persisted(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(side_effect=_by_team_response({NAME_KC: load("articles_normal.json")}))

    await _run(now=NOW)

    payload = _json.loads(insert_route.calls[-1].request.content)
    urls = {article["url"] for article in payload["news"]["value"]}
    assert len(urls) == 3


# ============================================================================
# No relevant news -- a real, positive "checked, nothing" result
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_no_relevant_news_writes_fresh_empty_value(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    result = await _run(now=NOW)

    assert result.status == "success"
    assert result.games_updated == 1
    payload = _json.loads(insert_route.calls[-1].request.content)
    assert payload["news"]["value"] == []
    assert payload["news"]["status"] == "fresh"  # distinguishes "checked, empty" from "not checked"


# ============================================================================
# Provider failure -- never erases previously-usable news
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_provider_failure_preserves_last_known_good(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_normal.json")))

    first = await _run(now=NOW)
    assert first.status == "success"
    assert insert_route.call_count == 1  # one successful write for game-1

    respx.get(EVERYTHING_URL).mock(return_value=httpx.Response(503))
    second = await _run(now=NOW)

    assert second.status == "partial"
    assert second.games_updated == 0
    assert len(second.failures) == 2  # both KC and BAL fail independently
    # No new write happened -- prior write_news call is still the only one.
    assert insert_route.call_count == 1


# ============================================================================
# Malformed provider response -- isolated like any other ProviderError
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_malformed_provider_response_isolated(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_malformed.json")))

    result = await _run(now=NOW)

    assert result.status == "partial"
    assert len(result.failures) == 2
    assert result.games_updated == 0
    assert insert_route.call_count == 0


# ============================================================================
# Team-level / game-level combination + dedup across two teams
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_two_teams_articles_combined_and_deduped_by_url(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()

    kc_body = load("articles_normal.json")  # 3 articles
    shared_url = kc_body["articles"][0]["url"]
    bal_body = {
        "status": "ok",
        "totalResults": 1,
        "articles": [
            {
                "source": {"id": "espn", "name": "ESPN"},
                "author": "Adam Schefter",
                "title": "Chiefs, Ravens set for statement Week 2 matchup",
                "description": "Same article, surfaced by both team queries.",
                "url": shared_url,  # duplicate across both team fetches
                "urlToImage": None,
                "publishedAt": "2026-09-12T14:00:00Z",
                "content": None,
            }
        ],
    }
    _news_route().mock(side_effect=_by_team_response({NAME_KC: kc_body, NAME_BAL: bal_body}))

    await _run(now=NOW)

    payload = _json.loads(insert_route.calls[-1].request.content)
    urls = [article["url"] for article in payload["news"]["value"]]
    assert urls.count(shared_url) == 1  # deduped, not double-counted
    assert len(urls) == 3  # KC's 3 (one shared with BAL's single duplicate)


# ============================================================================
# Unresolved identity -- no fuzzy matching, no guessed team/game relationship
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_unmapped_abbreviation_is_unresolved_not_guessed(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id="game-2", home_team="SEA", away_team="ZZZ", scheduled_start="2026-09-14T20:00:00Z")])
    _mock_team_provider_ids({"SEA": TEAM_SEA})  # "ZZZ" deliberately has no mapping
    _mock_teams({TEAM_SEA: NAME_SEA})
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_normal.json")))

    result = await _run(now=NOW)

    assert result.teams_unresolved == ["ZZZ"]
    assert result.games_updated == 1  # SEA's side still resolves and writes
    payload = _json.loads(insert_route.calls[-1].request.content)
    assert payload["game_id"] == "game-2"


@pytest.mark.asyncio
@respx.mock
async def test_both_sides_unresolved_skips_the_game_entirely(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id="game-3", home_team="ZZZ", away_team="YYY", scheduled_start="2026-09-14T20:00:00Z")])
    _mock_team_provider_ids({})  # neither abbreviation maps to anything
    _mock_teams({})
    insert_route = _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_normal.json")))

    result = await _run(now=NOW)

    assert sorted(result.teams_unresolved) == ["YYY", "ZZZ"]
    assert result.games_skipped_no_data == 1
    assert result.games_updated == 0
    assert insert_route.call_count == 0
    assert news_route.call_count == 0  # nothing to fetch -- both sides unresolved


def test_validate_articles_drops_articles_with_mismatched_related_teams():
    """Unit-tested directly (not through the full HTTP pipeline):
    NewsAPINewsAdapter's own contract always sets related_teams=[team] for
    a team-scoped call, so a real mismatch can never occur through that
    adapter -- this proves the worker's defensive check itself works
    correctly, independent of whether the one adapter that exists today
    happens to always satisfy it. Guards against a future/different
    NewsAdapter implementation that doesn't."""
    from app.workers.news_worker import _validate_articles

    published = datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc)
    matching = NewsArticle(
        headline="Chiefs preview", url="https://example.com/1", source="ESPN",
        published_at=published, related_teams=[NAME_KC],
    )
    mismatched = NewsArticle(
        headline="Unrelated story", url="https://example.com/2", source="ESPN",
        published_at=published, related_teams=[NAME_BAL],  # queried for KC, tagged for BAL
    )

    validated, dropped = _validate_articles(NAME_KC, [matching, mismatched])

    assert validated == [matching]
    assert dropped == 1


@pytest.mark.asyncio
@respx.mock
async def test_real_adapter_articles_pass_validation_end_to_end(monkeypatch):
    """Confirms the real NewsAPINewsAdapter's related_teams=[team]
    guarantee actually holds end-to-end through the full worker pipeline
    -- articles_dropped_unresolved stays 0 for a well-behaved adapter."""
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(side_effect=_by_team_response({NAME_KC: load("articles_normal.json")}))

    result = await _run(now=NOW)

    assert result.articles_dropped_unresolved == 0
    payload = _json.loads(insert_route.calls[-1].request.content)
    assert len(payload["news"]["value"]) == 3


# ============================================================================
# Never calls the unscoped/league-wide query
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_never_calls_unscoped_news_query(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    await _run(now=NOW)

    for call in news_route.calls:
        q = call.request.url.params.get("q", "")
        assert q != "NFL"  # the bare, unscoped query -- never issued by this worker
        assert q.endswith(" NFL")  # always team-qualified


# ============================================================================
# Player-level news -- structurally unsupported, not silently dropped
# ============================================================================


def test_news_article_model_has_no_player_field():
    fields = set(NewsArticle.model_fields)
    assert "player" not in fields
    assert "player_id" not in fields
    assert fields == {"headline", "url", "source", "published_at", "summary", "related_teams"}


# ============================================================================
# Cadence: candidate window, first-run/not-due/due boundary
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_no_games_in_candidate_window_skips_everything(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([])
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    result = await _run(now=NOW)

    assert result.status == "success"
    assert result.games_considered == 0
    assert news_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_not_due_yet_before_15_minute_interval(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    last_polled_at = {TEAM_KC: NOW - timedelta(minutes=10), TEAM_BAL: NOW - timedelta(minutes=10)}
    result = await _run(now=NOW, last_polled_at=last_polled_at)

    assert result.teams_due == 0
    assert result.teams_skipped_not_due == 2
    assert news_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_due_once_15_minute_interval_has_elapsed(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    last_polled_at = {TEAM_KC: NOW - timedelta(minutes=16), TEAM_BAL: NOW - timedelta(minutes=16)}
    result = await _run(now=NOW, last_polled_at=last_polled_at)

    assert result.teams_due == 2
    assert news_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_first_run_with_no_last_polled_at_is_always_due(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    result = await _run(now=NOW, last_polled_at=None)

    assert result.teams_due == 2
    assert news_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_news_worker_never_stops_at_kickoff(monkeypatch):
    """Deliberate departure from Weather/Odds/Player Props: a game already
    past kickoff must still have its teams polled for news, since news
    relevance doesn't expire at kickoff the way pregame markets/conditions
    do."""
    _headers_env(monkeypatch)
    _mock_games(
        [_game_row(game_id="game-1", home_team="KC", away_team="BAL", scheduled_start="2026-09-10T11:00:00Z")]
    )
    _mock_team_provider_ids({"KC": TEAM_KC, "BAL": TEAM_BAL})
    _mock_teams({TEAM_KC: NAME_KC, TEAM_BAL: NAME_BAL})
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)  # 1 hour after this game's kickoff
    result = await _run(now=now)

    assert result.teams_due == 2  # NOT stopped, unlike Weather's Window.STOPPED behavior
    assert news_route.call_count == 2


# ============================================================================
# Cache hit / stale
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_prevents_a_second_provider_call_within_ttl(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    cache_backend = InMemoryCacheBackend()
    first = await _run(now=NOW, cache_backend=cache_backend)
    second = await _run(now=NOW, cache_backend=cache_backend)

    assert first.status == "success"
    assert second.status == "success"
    assert news_route.call_count == 2  # one per team, not re-fetched on the second run


@pytest.mark.asyncio
@respx.mock
async def test_stale_cache_triggers_new_fetch(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    _mock_dgi_upsert()
    news_route = _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    await _run(now=NOW, cache_backend=InMemoryCacheBackend())
    await _run(now=NOW, cache_backend=InMemoryCacheBackend())  # fresh backend -- no cache hit

    assert news_route.call_count == 4  # 2 teams x 2 independent (uncached) runs


# ============================================================================
# Rerun / idempotency -- upsert, not accumulation (unlike Weather's append-only)
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_rerun_upserts_rather_than_accumulating(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    await _run(now=NOW, cache_backend=InMemoryCacheBackend())
    await _run(now=NOW, cache_backend=InMemoryCacheBackend())

    assert insert_route.call_count == 2
    for call in insert_route.calls:
        assert call.request.url.params.get("on_conflict") == "game_id"
        assert call.request.headers.get("Prefer") == "resolution=merge-duplicates"


# ============================================================================
# daily_game_intelligence integration -- exact write shape
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_write_touches_only_game_id_and_news_columns(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    _news_route().mock(return_value=httpx.Response(200, json=load("articles_empty.json")))

    await _run(now=NOW)

    payload = _json.loads(insert_route.calls[-1].request.content)
    assert set(payload.keys()) == {"game_id", "news"}
    assert set(payload["news"].keys()) == {"value", "source", "last_updated", "status"}


# ============================================================================
# Timezone handling -- publication timestamps
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_non_utc_published_at_survives_persistence(monkeypatch):
    _headers_env(monkeypatch)
    _standard_setup()
    insert_route = _mock_dgi_upsert()
    body = {
        "status": "ok",
        "totalResults": 1,
        "articles": [
            {
                "source": {"id": "espn", "name": "ESPN"},
                "author": None,
                "title": "Evening kickoff preview",
                "description": None,
                "url": "https://example.com/evening-preview",
                "urlToImage": None,
                "publishedAt": "2026-09-12T09:00:00-05:00",  # non-UTC offset, not "Z"
                "content": None,
            }
        ],
    }
    _news_route().mock(side_effect=_by_team_response({NAME_KC: body}))

    await _run(now=NOW)

    payload = _json.loads(insert_route.calls[-1].request.content)
    article = next(a for a in payload["news"]["value"] if a["url"] == "https://example.com/evening-preview")
    parsed = datetime.fromisoformat(article["published_at"])
    assert parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc) == datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc)


# ============================================================================
# No unauthorized provider calls -- structural guarantee
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_worker_signature_has_no_sportsdataio_or_weatherapi_client(monkeypatch):
    import inspect

    from app.workers.news_worker import run_news_worker as fn

    params = set(inspect.signature(fn).parameters)
    assert "sportsdataio_client" not in params
    assert "weatherapi_client" not in params
    assert params == {
        "supabase_client",
        "newsapi_client",
        "newsapi_key",
        "cache_backend",
        "now",
        "last_polled_at",
        "news_adapter",
    }
