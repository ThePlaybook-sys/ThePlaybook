"""Orchestration tests for app.workers.player_props_worker (Phase 3E-4E).

Every HTTP boundary is respx-mocked; no real network. Covers: correct
adaptive cadence, Player Props' own-cadence-not-assumed-identical check
(same numbers as Odds, confirmed by reading the Blueprint, not by
assertion alone), the linked-vs-unlinked game split unique to this worker,
market_type='prop' persistence, per-game failure isolation, cache hit
prevents redundant fetch, and rerun/append-only behavior.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.workers.player_props_worker import run_player_props_worker
from tests.adapters.the_odds_api_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"

GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"  # kickoff 2026-09-14T17:00:00Z
GAME_49ERS_BILLS = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"  # kickoff 2026-09-14T20:25:00Z

DB_GAME_KC_BAL = "db-game-kc-bal"
DB_GAME_SF_BUF = "db-game-sf-buf"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, game_id: str, home: str, away: str, scheduled_start: str) -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": home,
        "away_team": away,
        "scheduled_start": scheduled_start,
        "stadium": "Some Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": 2,
    }


_ALL_GAMES = [
    _game_row(game_id=DB_GAME_KC_BAL, home="KC", away="BAL", scheduled_start="2026-09-14T17:00:00Z"),
    _game_row(game_id=DB_GAME_SF_BUF, home="SF", away="BUF", scheduled_start="2026-09-14T20:25:00Z"),
]


def _mock_games(games=None):
    games = games if games is not None else _ALL_GAMES
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_game_provider_ids_reverse(linked: dict[str, str]):
    """linked: game_id -> the_odds_api provider_game_id. Serves both query
    directions this worker's own module and persist_player_props each
    use: the reverse lookup (filtered by `game_id`, used by
    `_reverse_resolve_the_odds_api_ids`) and the forward lookup (filtered
    by `provider_game_id`, used by `resolve_game_ids` inside
    `persist_player_props`) -- distinguished by inspecting which param is
    actually present, same pattern as test_master_refresh.py's own
    multi-purpose route mock."""

    def _respond(request: httpx.Request) -> httpx.Response:
        game_id_param = request.url.params.get("game_id", "")
        provider_id_param = request.url.params.get("provider_game_id", "")
        if game_id_param:
            rows = [
                {"game_id": game_id, "provider_game_id": provider_id}
                for game_id, provider_id in linked.items()
                if game_id in game_id_param
            ]
        else:
            rows = [
                {"game_id": game_id, "provider_game_id": provider_id}
                for game_id, provider_id in linked.items()
                if provider_id in provider_id_param
            ]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_respond)


def _mock_odds_snapshots_insert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))


def _event_url(game_external_id: str) -> str:
    return f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/events/{game_external_id}/odds"


@pytest.mark.asyncio
@respx.mock
async def test_linked_due_game_fetches_and_persists_props_with_market_type_prop(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_reverse({DB_GAME_KC_BAL: GAME_CHIEFS_RAVENS})
    insert_route = _mock_odds_snapshots_insert()
    respx.get(_event_url(GAME_CHIEFS_RAVENS)).mock(
        return_value=httpx.Response(200, json=load("player_props_event.json"))
    )

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)  # 30 min before KC/BAL kickoff -- RAMP_60M
    last_polled_at = {DB_GAME_SF_BUF: now - timedelta(minutes=1)}  # keep the other game not-due

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
        )

    assert result.status == "success"
    assert result.games_due == 1
    assert result.props_persisted > 0
    assert result.games_skipped_unlinked == []

    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert all(row["market_type"] == "prop" for row in rows)
    assert all(row["game_id"] == DB_GAME_KC_BAL for row in rows)
    assert all({"player_external_id", "player_name", "prop_type", "line"} <= set(row["line_data"]) for row in rows)


@pytest.mark.asyncio
@respx.mock
async def test_unlinked_due_game_is_skipped_not_a_hard_failure(monkeypatch):
    """Player Props Worker cannot self-discover event ids (structural
    difference from the Odds Worker) -- a due game with no existing
    the_odds_api link is collected as skipped, and the run still succeeds
    for whatever else is due."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_reverse({})  # nothing linked yet
    _mock_odds_snapshots_insert()

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    last_polled_at = {DB_GAME_SF_BUF: now - timedelta(minutes=1)}

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
        )

    assert result.status == "partial"
    assert result.games_due == 1
    assert result.games_skipped_unlinked == [DB_GAME_KC_BAL]
    assert result.props_persisted == 0


@pytest.mark.asyncio
@respx.mock
async def test_no_games_due_skips_provider_calls_entirely(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)  # 4 days out -- FAR
    last_polled_at = {g["id"]: now - timedelta(minutes=1) for g in _ALL_GAMES}
    event_route = respx.get(_event_url(GAME_CHIEFS_RAVENS)).mock(
        return_value=httpx.Response(200, json=load("player_props_event.json"))
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
        )

    assert result.status == "success"
    assert result.games_due == 0
    assert event_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_one_games_provider_failure_does_not_block_the_other(monkeypatch):
    _headers_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_KC_BAL, home="KC", away="BAL", scheduled_start="2026-09-14T17:00:00Z"),
        _game_row(game_id=DB_GAME_SF_BUF, home="SF", away="BUF", scheduled_start="2026-09-14T17:05:00Z"),
    ]
    _mock_games(games)
    _mock_game_provider_ids_reverse({DB_GAME_KC_BAL: GAME_CHIEFS_RAVENS, DB_GAME_SF_BUF: GAME_49ERS_BILLS})
    insert_route = _mock_odds_snapshots_insert()

    respx.get(_event_url(GAME_CHIEFS_RAVENS)).mock(return_value=httpx.Response(503))  # simulated outage
    respx.get(_event_url(GAME_49ERS_BILLS)).mock(
        return_value=httpx.Response(200, json=load("player_props_missing_market.json"))
    )

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
        )

    assert result.status == "partial"
    assert result.games_due == 2
    assert len(result.failures) == 1
    assert DB_GAME_KC_BAL in result.failures[0]


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_prevents_a_second_provider_call_within_ttl(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_reverse({DB_GAME_KC_BAL: GAME_CHIEFS_RAVENS})
    _mock_odds_snapshots_insert()
    event_route = respx.get(_event_url(GAME_CHIEFS_RAVENS)).mock(
        return_value=httpx.Response(200, json=load("player_props_event.json"))
    )

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    last_polled_at = {DB_GAME_SF_BUF: now - timedelta(minutes=1)}
    cache_backend = InMemoryCacheBackend()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        first = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend,
        )
        second = await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend,
        )

    assert first.status == "success"
    assert second.status == "success"
    assert event_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_rerun_appends_new_rows_rather_than_overwriting(monkeypatch):
    """Two independent runs (fresh cache each time, simulating the TTL
    having elapsed) must each append their own odds_snapshots rows --
    append-only history, never an update-in-place."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_game_provider_ids_reverse({DB_GAME_KC_BAL: GAME_CHIEFS_RAVENS})
    insert_route = _mock_odds_snapshots_insert()
    respx.get(_event_url(GAME_CHIEFS_RAVENS)).mock(
        return_value=httpx.Response(200, json=load("player_props_event.json"))
    )

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    last_polled_at = {DB_GAME_SF_BUF: now - timedelta(minutes=1)}

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=InMemoryCacheBackend(),  # fresh backend each run -- no cache hit
        )
        await run_player_props_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=InMemoryCacheBackend(),
        )

    # Two separate insert POSTs -- never a PATCH/update, and never merged
    # into a single call.
    assert insert_route.call_count == 2
