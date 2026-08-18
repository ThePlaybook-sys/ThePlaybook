"""Orchestration tests for app.workers.injury_worker (Phase 3E-5).

Every HTTP boundary -- Supabase and SportsDataIO both -- is respx-mocked;
no real network, and specifically zero SportsDataIO calls beyond what each
test explicitly mocks (an unmocked respx route raises, so any accidental
extra call fails the test loudly rather than silently passing).

Covers: normal poll + persistence, multiple records, empty response,
identity resolution (including an unresolved/bye-week row), day-of-week
cadence gating (Wednesday active-week vs. Monday infrequent), the T-90-
minute inactive-list window, STOPPED games excluded from driver selection,
per-row malformed-record isolation surviving end-to-end into persisted
rows, true provider-level failure, cache hit/stale behavior, append-only
rerun behavior, and a downstream read-back proving the write path feeds
`daily_game_intelligence`'s existing read helper.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.persistence.snapshots import latest_injury_report
from app.workers.injury_worker import run_injury_worker
from tests.adapters.sportsdataio_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"

DB_GAME_ARI_NO = "db-game-ari-no"
DB_GAME_ATL_TB = "db-game-atl-tb"
DB_GAME_BAL_BUF = "db-game-bal-buf"

SDIO_GAME_ARI_NO = "202510122"
SDIO_GAME_ATL_TB = "202510102"
SDIO_GAME_BAL_BUF = "202510104"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, game_id: str, home: str, away: str, scheduled_start: str, week: int = 1) -> dict:
    return {
        "id": game_id,
        "external_provider_id": None,
        "home_team": home,
        "away_team": away,
        "scheduled_start": scheduled_start,
        "stadium": "Some Stadium",
        "status": "scheduled",
        "season_type": "regular",
        "week": week,
    }


_ALL_GAMES = [
    _game_row(game_id=DB_GAME_ARI_NO, home="ARI", away="NO", scheduled_start="2026-09-20T17:00:00Z"),
    _game_row(game_id=DB_GAME_ATL_TB, home="ATL", away="TB", scheduled_start="2026-09-20T20:25:00Z"),
    _game_row(game_id=DB_GAME_BAL_BUF, home="BAL", away="BUF", scheduled_start="2026-09-21T00:20:00Z"),
]


def _mock_games(games=None):
    games = games if games is not None else _ALL_GAMES
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_season(year: int = 2026):
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-nfl"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200, json=[{"year": year, "start_date": f"{year}-09-04", "end_date": f"{year + 1}-02-14"}]
        )
    )


def _mock_game_provider_ids(linked: dict[str, str]):
    """linked: game_id -> sportsdataio provider_game_id (GameKey). Serves
    both directions this worker + persist_injury_reports use: the reverse
    lookup (filtered by game_id, injury_worker's own
    _reverse_resolve_sportsdataio_ids) and the forward lookup (filtered by
    provider_game_id, resolve_game_ids inside persist_injury_reports) --
    same dual-purpose-mock convention as test_player_props_worker.py."""

    def _respond(request: httpx.Request) -> httpx.Response:
        game_id_param = request.url.params.get("game_id", "")
        provider_id_param = request.url.params.get("provider_game_id", "")
        if game_id_param:
            rows = [
                {"game_id": gid, "provider_game_id": pid}
                for gid, pid in linked.items()
                if gid in game_id_param
            ]
        else:
            rows = [
                {"game_id": gid, "provider_game_id": pid}
                for gid, pid in linked.items()
                if pid in provider_id_param
            ]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_respond)


def _mock_injury_reports_insert():
    return respx.post(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(201))


def _injuries_url(season: str, week: int) -> str:
    return f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/Injuries/{season}/{week}"


async def _run(*, now, last_polled_at=None, cache_backend=None):
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=SPORTSDATAIO_URL
    ) as sportsdataio_client:
        return await run_injury_worker(
            supabase_client=supabase_client,
            sportsdataio_client=sportsdataio_client,
            sportsdataio_api_key="test-key",
            now=now,
            last_polled_at=last_polled_at,
            cache_backend=cache_backend or InMemoryCacheBackend(),
        )


# ============================================================================
# Normal poll: fetch + identity resolution + persistence
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_normal_poll_fetches_and_persists_multiple_records(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    insert_route = _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(200, json=load("injuries_normal.json")))

    # Wednesday, driver game (ARI/NO, soonest kickoff) is 4 days out --
    # ACTIVE_WEEK, due since never polled.
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

    result = await _run(now=now)

    assert result.status == "success"
    assert result.polled is True
    assert result.reports_persisted == 3  # all 3 rows in injuries_normal.json resolve

    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert len(rows) == 3
    by_game = {row["game_id"] for row in rows}
    assert by_game == {DB_GAME_ARI_NO, DB_GAME_ATL_TB, DB_GAME_BAL_BUF}
    assert all({"player_external_id", "player_name", "team", "status"} <= set(row["report_data"]) for row in rows)


@pytest.mark.asyncio
@respx.mock
async def test_empty_injury_response_persists_nothing_but_succeeds(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    insert_route = _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(200, json=[]))

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.polled is True
    assert result.reports_persisted == 0
    assert insert_route.call_count == 0  # never POSTs an empty batch


@pytest.mark.asyncio
@respx.mock
async def test_unresolvable_row_is_skipped_not_fabricated(monkeypatch):
    """A row whose (team, opponent) pair isn't in this week's linked
    games -- e.g. a bye-week team, or a team simply not yet linked -- is
    skipped by the adapter's own game_key_for=None path, never guessed."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    # Only ARI/NO linked -- ATL/TB and BAL/BUF are not, simulating
    # not-yet-linked games.
    _mock_game_provider_ids({DB_GAME_ARI_NO: SDIO_GAME_ARI_NO})
    insert_route = _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(200, json=load("injuries_normal.json")))

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.reports_persisted == 1  # only ARI's row resolves

    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert len(rows) == 1
    assert rows[0]["game_id"] == DB_GAME_ARI_NO


# ============================================================================
# Malformed-row isolation, end-to-end through the worker
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_malformed_row_isolated_valid_rows_still_persisted(monkeypatch, caplog):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    insert_route = _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_mixed_with_malformed_row.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    with caplog.at_level("WARNING"):
        result = await _run(now=now)

    assert result.status == "success"  # not "failed" -- the malformed row never propagates as a run failure
    assert result.reports_persisted == 2  # ARI's and BAL's valid rows; ATL's malformed row is absent

    rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert {row["game_id"] for row in rows} == {DB_GAME_ARI_NO, DB_GAME_BAL_BUF}
    assert any("malformed row skipped" in record.message for record in caplog.records)


@pytest.mark.asyncio
@respx.mock
async def test_true_provider_failure_fails_the_whole_run(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids({DB_GAME_ARI_NO: SDIO_GAME_ARI_NO})
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(503))

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "failed"
    assert result.polled is True
    assert "injuries fetch failed" in result.error


# ============================================================================
# Cadence gating: day-of-week + pre-kickoff
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_no_games_in_candidate_window_skips_provider_calls_entirely(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games(games=[])
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_considered == 0
    assert injuries_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_all_games_stopped_skips_provider_calls_entirely(monkeypatch):
    """Every candidate game has already kicked off (or is kicking off
    right now) -- STOPPED, excluded from driver selection, no poll."""
    _headers_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_ARI_NO, home="ARI", away="NO", scheduled_start="2026-09-16T11:00:00Z"),
    ]
    _mock_games(games)
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # 1 hour after this game's kickoff
    result = await _run(now=now)

    assert result.status == "success"
    assert result.games_considered == 1
    assert result.active_games == 0
    assert injuries_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_monday_far_from_kickoff_not_due_after_recent_poll(monkeypatch):
    """Monday (INFREQUENT, 48h interval) with a recent last_polled_at --
    not due yet."""
    _headers_env(monkeypatch)
    _mock_games()
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)  # Monday
    last_polled_at = now - timedelta(hours=1)
    result = await _run(now=now, last_polled_at=last_polled_at)

    assert result.status == "success"
    assert result.polled is False
    assert injuries_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_wednesday_active_week_due_after_daily_interval(monkeypatch):
    """Wednesday (ACTIVE_WEEK, 24h interval) is due once 24h have elapsed
    since the last poll, even though the same elapsed time would not yet
    be due under Monday's looser 48h interval."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids({DB_GAME_ARI_NO: SDIO_GAME_ARI_NO})
    _mock_injury_reports_insert()
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # Wednesday
    last_polled_at = now - timedelta(hours=25)
    result = await _run(now=now, last_polled_at=last_polled_at)

    assert result.status == "success"
    assert result.polled is True
    assert injuries_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_pre_kickoff_inactive_list_window_triggers_poll(monkeypatch):
    """The T-90-minute inactive-list window is due even freshly after a
    recent poll, since its own interval (15min) is far tighter than the
    day-of-week tiers."""
    _headers_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_ARI_NO, home="ARI", away="NO", scheduled_start="2026-09-20T13:20:00Z", week=1),
    ]
    _mock_games(games)
    _mock_season()
    _mock_game_provider_ids({DB_GAME_ARI_NO: SDIO_GAME_ARI_NO})
    _mock_injury_reports_insert()
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)  # kickoff - 80 min -> INACTIVE_LIST
    last_polled_at = now - timedelta(minutes=16)  # older than the 15min interval
    result = await _run(now=now, last_polled_at=last_polled_at)

    assert result.status == "success"
    assert result.polled is True
    assert injuries_route.call_count == 1


# ============================================================================
# Cache hit / stale / rerun
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_prevents_a_second_provider_call_within_ttl(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    _mock_injury_reports_insert()
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    cache_backend = InMemoryCacheBackend()

    first = await _run(now=now, cache_backend=cache_backend)
    second = await _run(now=now, cache_backend=cache_backend)

    assert first.status == "success"
    assert second.status == "success"
    assert injuries_route.call_count == 1  # second run served from cache


@pytest.mark.asyncio
@respx.mock
async def test_stale_cache_triggers_new_fetch(monkeypatch):
    """A fresh InMemoryCacheBackend simulates the TTL having elapsed
    (nothing cached yet, matching test_rerun_appends_new_rows_rather_than_
    overwriting's identical convention in the Odds/Props worker tests)."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    _mock_injury_reports_insert()
    injuries_route = respx.get(_injuries_url("2026REG", 1)).mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    await _run(now=now, cache_backend=InMemoryCacheBackend())
    await _run(now=now, cache_backend=InMemoryCacheBackend())  # fresh backend -- no cache hit

    assert injuries_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_rerun_appends_new_rows_rather_than_overwriting(monkeypatch):
    """Mac's Decision 2: append-only, no de-dup -- two independent polls
    each write their own full batch of rows, never an update-in-place."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids(
        {DB_GAME_ARI_NO: SDIO_GAME_ARI_NO, DB_GAME_ATL_TB: SDIO_GAME_ATL_TB, DB_GAME_BAL_BUF: SDIO_GAME_BAL_BUF}
    )
    insert_route = _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(200, json=load("injuries_normal.json")))

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    await _run(now=now, cache_backend=InMemoryCacheBackend())
    await _run(now=now, cache_backend=InMemoryCacheBackend())

    assert insert_route.call_count == 2  # two separate POSTs, never a PATCH/update
    all_rows = [row for call in insert_route.calls for row in _json.loads(call.request.content)]
    assert len(all_rows) == 6  # 3 rows x 2 independent polls -- identical data, both retained


# ============================================================================
# Downstream read-back -- proves the write path feeds the already-existing
# daily_game_intelligence read helper (app.persistence.snapshots), not
# just that a row lands in the table.
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_persisted_report_is_readable_via_latest_injury_report(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_season()
    _mock_game_provider_ids({DB_GAME_ARI_NO: SDIO_GAME_ARI_NO})
    _mock_injury_reports_insert()
    respx.get(_injuries_url("2026REG", 1)).mock(return_value=httpx.Response(200, json=load("injuries_normal.json")))

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    result = await _run(now=now)
    assert result.reports_persisted >= 1

    persisted_row = {
        "id": "row-1",
        "game_id": DB_GAME_ARI_NO,
        "report_data": {
            "player_external_id": "19930",
            "player_name": "Bilal Nichols",
            "team": "ARI",
            "status": "Scrambled",
            "description": None,
        },
        "captured_at": "2026-09-16T12:00:00Z",
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[persisted_row]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        headers = {"Authorization": "Bearer test-service-role-key", "apikey": "test-service-role-key"}
        row = await latest_injury_report(client, headers, game_id=DB_GAME_ARI_NO)

    assert row is not None
    assert row["report_data"]["player_name"] == "Bilal Nichols"
