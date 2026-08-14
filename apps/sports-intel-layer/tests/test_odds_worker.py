"""Orchestration tests for app.workers.odds_worker (Phase 3E-4D).

Every HTTP boundary -- Supabase and The Odds API both -- is respx-mocked;
no real network is used anywhere in this file. Covers Mac's 3E-4 testing
list as it applies to the Odds Worker specifically: correct adaptive
cadence by kickoff proximity, cache hit prevents redundant fetch, provider
failure does not crash unrelated game processing, persistence remains
append-only, rerun behavior does not corrupt history, multi-game Sunday
slate, and the "Master Refresh still makes zero Odds calls" boundary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.workers.odds_worker import run_odds_worker
from tests.adapters.the_odds_api_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"

GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"  # KC (home) v BAL, kickoff 2026-09-14T17:00:00Z
GAME_COWBOYS_EAGLES = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # DAL (home) v PHI, kickoff 2026-09-14T20:25:00Z
GAME_49ERS_BILLS = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"  # SF (home) v BUF, kickoff 2026-09-14T20:25:00Z

DB_GAME_KC_BAL = "db-game-kc-bal"
DB_GAME_DAL_PHI = "db-game-dal-phi"
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
    _game_row(game_id=DB_GAME_DAL_PHI, home="DAL", away="PHI", scheduled_start="2026-09-14T20:25:00Z"),
    _game_row(game_id=DB_GAME_SF_BUF, home="SF", away="BUF", scheduled_start="2026-09-14T20:25:00Z"),
]

_TEAM_PROVIDER_ROWS = {
    "eq.the_odds_api": [
        {"team_id": "t-kc", "provider_team_id": "Kansas City Chiefs"},
        {"team_id": "t-bal", "provider_team_id": "Baltimore Ravens"},
        {"team_id": "t-dal", "provider_team_id": "Dallas Cowboys"},
        {"team_id": "t-phi", "provider_team_id": "Philadelphia Eagles"},
        {"team_id": "t-sf", "provider_team_id": "San Francisco 49ers"},
        {"team_id": "t-buf", "provider_team_id": "Buffalo Bills"},
    ],
    "eq.sportsdataio": [
        {"team_id": "t-kc", "provider_team_id": "KC"},
        {"team_id": "t-bal", "provider_team_id": "BAL"},
        {"team_id": "t-dal", "provider_team_id": "DAL"},
        {"team_id": "t-phi", "provider_team_id": "PHI"},
        {"team_id": "t-sf", "provider_team_id": "SF"},
        {"team_id": "t-buf", "provider_team_id": "BUF"},
    ],
}


def _mock_games(games=None):
    games = games if games is not None else _ALL_GAMES
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_team_provider_ids():
    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        ids_param = request.url.params["provider_team_id"]
        rows = [r for r in _TEAM_PROVIDER_ROWS.get(provider_name, []) if r["provider_team_id"] in ids_param]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_respond)


def _mock_game_provider_ids(existing: dict | None = None):
    """Stateful mock: a POST (a new link established by the linking
    module) updates the same dict the GET reads from, mirroring how a
    real Supabase upsert-then-read round trip behaves. Without this, a
    game linked mid-run would never be visible to a later read in the
    same run (e.g. odds_snapshots persistence's own internal
    resolve_game_ids call) -- a test-mock gap, not a real one."""
    state = dict(existing or {})

    def _get_respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_game_id", "")
        rows = [
            {"game_id": game_id, "provider_game_id": provider_id}
            for provider_id, game_id in state.items()
            if provider_id in ids_param
        ]
        return httpx.Response(200, json=rows)

    def _post_respond(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        state[body["provider_game_id"]] = body["game_id"]
        return httpx.Response(201)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_get_respond)
    return respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_post_respond)


def _mock_odds_snapshots_insert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))


def _odds_response():
    return httpx.Response(200, json=load("bulk_odds_multi_game.json"))


# ---------------------------------------------------------------------------
# Adaptive cadence by kickoff proximity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_no_games_due_skips_the_provider_call_entirely(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    # now is 4 days before every kickoff -- FAR window (24h poll interval).
    # Every game was "just polled" a minute ago, so none has had its
    # interval elapse yet -- nothing due. (Without an explicit
    # last_polled_at, every non-STOPPED window is due on its very first
    # check, by design -- see run_odds_worker's own docstring -- so this
    # test must supply one to actually exercise "not due yet.")
    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    last_polled_at = {g["id"]: now - timedelta(minutes=1) for g in _ALL_GAMES}
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
        )

    assert result.status == "success"
    assert result.games_due == 0
    assert result.games_skipped_not_due == 3
    assert odds_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_single_due_game_fetches_and_persists_only_that_games_lines(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    insert_route = _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    # 30 minutes before Chiefs-Ravens kickoff (17:00) -- RAMP_60M (900s
    # interval), never polled before -- due. Cowboys-Eagles/49ers-Bills
    # kick off at 20:25 -- ~3h55m out, FAR (86400s interval), but each was
    # "just polled" a minute ago -- not due yet.
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    last_polled_at = {
        DB_GAME_DAL_PHI: now - timedelta(minutes=1),
        DB_GAME_SF_BUF: now - timedelta(minutes=1),
    }

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
        )

    assert result.status == "success"
    assert result.games_due == 1
    assert result.games_skipped_not_due == 2
    assert result.lines_persisted > 0

    # every persisted row must belong to the one due game
    for call in insert_route.calls:
        for row in _rows_from(call):
            assert row["game_id"] == DB_GAME_KC_BAL


@pytest.mark.asyncio
@respx.mock
async def test_multi_game_sunday_slate_both_due_games_persisted(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    insert_route = _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    # 30 minutes before the 20:25 kickoffs -- Cowboys-Eagles AND 49ers-Bills
    # both due (RAMP_60M); Chiefs-Ravens already kicked off (17:00) -- STOPPED.
    now = datetime(2026, 9, 14, 19, 55, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
        )

    assert result.status == "success"
    assert result.games_due == 2

    persisted_game_ids = set()
    for call in insert_route.calls:
        for row in _rows_from(call):
            persisted_game_ids.add(row["game_id"])
    assert persisted_game_ids == {DB_GAME_DAL_PHI, DB_GAME_SF_BUF}


# ---------------------------------------------------------------------------
# Cache hit prevents redundant fetch (Phase 3E-4F dynamic TTL, applied)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_prevents_a_second_provider_call_within_ttl(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    cache_backend = InMemoryCacheBackend()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        first = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            cache_backend=cache_backend,
        )
        second = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,  # identical "now" -- well within RAMP_60M's 900s TTL
            cache_backend=cache_backend,
        )

    assert first.status == "success"
    assert second.status == "success"
    assert odds_route.call_count == 1  # second run served entirely from cache


# ---------------------------------------------------------------------------
# Provider failure isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_provider_failure_returns_failed_status_not_a_crash(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    respx.get(ODDS_URL).mock(return_value=httpx.Response(503))

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
        )

    assert result.status == "failed"
    assert result.error is not None


# ---------------------------------------------------------------------------
# Newly-discovered game gets linked, not just already-linked ones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_unlinked_due_game_gets_deterministically_linked_and_persisted(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    # Nothing pre-linked -- every event must be resolved via team identity.
    link_post = _mock_game_provider_ids(existing={})
    insert_route = _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
        )

    assert result.status == "success"
    assert result.newly_linked >= 1
    assert link_post.called
    assert result.lines_persisted > 0


# ---------------------------------------------------------------------------
# Rerun / append-only behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_rerun_with_fresh_cache_appends_rather_than_overwrites(monkeypatch):
    """Two independent runs (fresh cache each time, simulating the TTL
    having elapsed) must each append their own odds_snapshots rows --
    the append-only design, never an update-in-place -- and never corrupt
    already-persisted history."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    insert_route = _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    last_polled_at = {
        DB_GAME_DAL_PHI: now - timedelta(minutes=1),
        DB_GAME_SF_BUF: now - timedelta(minutes=1),
    }

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=InMemoryCacheBackend(),
        )
        await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=InMemoryCacheBackend(),
        )

    assert insert_route.call_count == 2  # two independent inserts, never a PATCH


# ---------------------------------------------------------------------------
# Dynamic TTL selection (Phase 3E-4F, Decision 4) -- end-to-end, not just
# the windows.py unit-level proof
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_ttl_actually_used_by_the_caching_adapter_tracks_the_due_windows_shortest_ttl(monkeypatch):
    """A game 90 minutes out classifies as RAMP_2H (3600s TTL); confirm the
    worker actually constructs its CachingAdapter with that number by
    proving a cache write recorded that exact TTL -- not just that
    windows.ttl_seconds computes the right number in isolation."""
    from app.workers.windows import Window, classify_window, ttl_seconds

    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    # 90 minutes before Chiefs-Ravens kickoff -- RAMP_2H.
    now = datetime(2026, 9, 14, 15, 30, tzinfo=timezone.utc)
    kickoff = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)
    assert classify_window(now=now, kickoff=kickoff) == Window.RAMP_2H
    expected_ttl = ttl_seconds(Window.RAMP_2H)

    last_polled_at = {
        DB_GAME_DAL_PHI: now - timedelta(minutes=1),
        DB_GAME_SF_BUF: now - timedelta(minutes=1),
    }

    class _RecordingCacheBackend(InMemoryCacheBackend):
        def __init__(self):
            super().__init__()
            self.recorded_ttls: list[int] = []

        async def set(self, key, value, ttl_seconds):  # noqa: A002 -- matches base signature
            self.recorded_ttls.append(ttl_seconds)
            await super().set(key, value, ttl_seconds)

    cache_backend = _RecordingCacheBackend()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend,
        )

    assert cache_backend.recorded_ttls == [expected_ttl]


# ---------------------------------------------------------------------------
# Master Refresh boundary -- structural proof, not just a claim
# ---------------------------------------------------------------------------


def test_master_refresh_module_never_imports_the_odds_api_adapter():
    import app.master_refresh.run as master_refresh_run

    source = master_refresh_run.__file__
    with open(source) as f:
        contents = f.read()
    assert "the_odds_api" not in contents
    assert "TheOddsApiOddsAdapter" not in contents
    assert "player_props" not in contents.lower()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rows_from(call) -> list[dict]:
    import json

    body = json.loads(call.request.content)
    return body if isinstance(body, list) else [body]
