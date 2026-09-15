"""Tests for Master Refresh V2 (2026-09-15, HQ-authorized "CANONICAL SCHEDULE +
FINALIZATION HARDENING", Part 2): full-season persistence, the rolling 7-day
coverage assertion, and the schedule/roster split.

The three changes share one root cause. Pre-V2, `filter_slate_window` ran
BEFORE `persist_schedule_entries`, so a run fetched the full season and then
discarded everything outside `[today, today + 7)` before it could be written --
which is exactly how Week 2 came to be missing from the canonical schedule while
the provider had been returning it all along.

No real network is used; the SportsDataIO base URL is respx-intercepted, and any
unmocked request raises rather than passing silently.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.models import ScheduleEntry
from app.master_refresh.coverage import assert_rolling_coverage
from app.master_refresh.run import run_roster_refresh, run_schedule_refresh

SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"
TODAY = date(2026, 9, 15)


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("MASTER_REFRESH_ENABLED", "true")


def _entry(external_id: str, *, start: str, home="SEA", away="NE") -> ScheduleEntry:
    return ScheduleEntry(
        game_external_id=external_id,
        home_team=home,
        away_team=away,
        scheduled_start=start,
        stadium="Lumen Field",
        status="scheduled",
        season_type="regular",
        week=2,
        venue_lat=None,
        venue_long=None,
        venue_type=None,
    )


def _canonical(game_id: str, *, start: str, home="SEA", away="NE") -> dict:
    return {"id": game_id, "home_team": home, "away_team": away, "scheduled_start": start}


# --------------------------------------------------------------------------
# The coverage assertion itself (pure, no I/O).
# --------------------------------------------------------------------------


def test_complete_coverage_reports_no_gaps():
    entries = [_entry("g1", start="2026-09-17T00:20:00+00:00")]
    canonical = [_canonical("db-1", start="2026-09-17T00:20:00+00:00")]
    result = assert_rolling_coverage(entries, canonical, today=TODAY)

    assert result.days_asserted == 7
    assert result.expected_games == 1
    assert result.canonical_games == 1
    assert result.complete is True
    assert result.gaps == []


def test_a_missing_canonical_game_is_reported_as_a_gap():
    """The Week 2 condition, expressed as an assertion: the provider has the
    game, the database does not."""
    entries = [_entry("g1", start="2026-09-17T00:20:00+00:00")]
    result = assert_rolling_coverage(entries, [], today=TODAY)

    assert result.complete is False
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.day == "2026-09-17"
    assert (gap.expected, gap.canonical) == (1, 0)
    assert "provider has 1" in gap.describe() and "canonical has 0" in gap.describe()


def test_a_genuinely_empty_nfl_day_is_not_a_gap():
    """An NFL Tuesday legitimately has zero games. Asserting "every day has at
    least one game" would be a false-alarm generator; this asserts
    reconciliation instead."""
    result = assert_rolling_coverage([], [], today=TODAY)
    assert result.days_asserted == 7
    assert result.complete is True


def test_extra_canonical_games_are_never_reported_as_a_gap():
    """More canonical rows than the provider currently lists (e.g. a manually
    seeded game) is not a coverage shortfall."""
    canonical = [
        _canonical("db-1", start="2026-09-17T00:20:00+00:00"),
        _canonical("db-2", start="2026-09-17T23:00:00+00:00"),
    ]
    result = assert_rolling_coverage([_entry("g1", start="2026-09-17T00:20:00+00:00")], canonical, today=TODAY)
    assert result.complete is True


def test_games_outside_the_window_are_ignored_by_the_assertion():
    """Persisted, but not asserted -- the window is a completeness claim about
    the next seven days, not about the whole season."""
    entries = [
        _entry("in", start="2026-09-17T00:20:00+00:00"),
        _entry("out", start="2026-10-20T00:20:00+00:00"),
    ]
    result = assert_rolling_coverage(entries, [_canonical("db-1", start="2026-09-17T00:20:00+00:00")], today=TODAY)

    assert result.expected_games == 1  # the October game is not expected here
    assert result.complete is True


def test_an_unparseable_canonical_timestamp_is_not_silently_counted():
    """A row whose `scheduled_start` can't be read must not be credited toward
    coverage -- that would turn a data problem into a false pass."""
    entries = [_entry("g1", start="2026-09-17T00:20:00+00:00")]
    canonical = [{"id": "db-1", "home_team": "SEA", "away_team": "NE", "scheduled_start": "not-a-date"}]
    result = assert_rolling_coverage(entries, canonical, today=TODAY)

    assert result.complete is False


def test_the_window_rolls_with_today():
    entries = [_entry("g1", start="2026-09-23T00:20:00+00:00")]
    # Sep 23 is outside [Sep 15, Sep 22) ...
    assert assert_rolling_coverage(entries, [], today=TODAY).expected_games == 0
    # ... and inside [Sep 20, Sep 27).
    assert assert_rolling_coverage(entries, [], today=TODAY + timedelta(days=5)).expected_games == 1


# --------------------------------------------------------------------------
# Full-season persistence + the split, end to end through run_schedule_refresh.
# --------------------------------------------------------------------------


def _game_row(game_key, home, away, dt, week=2):
    return {
        "GameKey": game_key,
        "SeasonType": 1,
        "Season": 2026,
        "Week": week,
        "HomeTeam": home,
        "AwayTeam": away,
        "Date": dt,
        "DateTimeUTC": dt,
        "StadiumDetails": {"Name": "Lumen Field", "GeoLat": None, "GeoLong": None, "Type": None},
        "Status": "Scheduled",
    }


def _mock_season():
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-nfl"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200, json=[{"year": 2026, "start_date": "2026-01-01", "end_date": "2027-01-01"}]
        )
    )


def _mock_runs():
    respx.post(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(201, json=[{"id": "mrr-1"}])
    )
    respx.patch(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(204))


def _mock_persistence(canonical_readback: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))
    created = iter(f"db-{i}" for i in range(1, 500))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created)}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=canonical_readback)
    )
    return insert_route


@pytest.mark.asyncio
@respx.mock
async def test_schedule_refresh_persists_the_whole_season_not_just_the_window(monkeypatch):
    """The Week 2 fix, proven directly: a game five weeks out is written rather
    than filtered away. Pre-V2 only the in-window game reached the database."""
    _env(monkeypatch)
    _mock_season()
    _mock_runs()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                _game_row("in-window", "SEA", "NE", "2026-09-17T00:20:00"),
                _game_row("far-future", "KC", "BUF", "2026-10-20T00:20:00", week=7),
            ],
        )
    )
    insert_route = _mock_persistence([_canonical("db-1", start="2026-09-17T00:20:00+00:00")])

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_schedule_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.schedule_entries_persisted == 2  # both, not just the slate
    assert result.games_created == 2
    assert insert_route.call_count == 2
    assert result.games_in_slate == 1  # the window still means the window


@pytest.mark.asyncio
@respx.mock
async def test_schedule_refresh_costs_exactly_one_provider_call_and_no_roster_calls(monkeypatch):
    """The whole point of the split: the daily path is 1 call, not up to 33.
    Any roster request would be unmocked here and would raise."""
    _env(monkeypatch)
    _mock_season()
    _mock_runs()
    schedule_route = respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-17T00:20:00")])
    )
    _mock_persistence([_canonical("db-1", start="2026-09-17T00:20:00+00:00")])

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_schedule_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "success"
    assert schedule_route.call_count == 1
    provider_calls = [c for c in respx.calls if c.request.url.host == "api.sportsdata.io"]
    assert len(provider_calls) == 1


@pytest.mark.asyncio
@respx.mock
async def test_a_coverage_gap_makes_the_run_partial_rather_than_silently_successful(monkeypatch):
    _env(monkeypatch)
    _mock_season()
    _mock_runs()
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=[_game_row("g1", "SEA", "NE", "2026-09-17T00:20:00")])
    )
    _mock_persistence([])  # persisted, but the read-back finds nothing

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_schedule_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "partial"
    assert result.coverage is not None and result.coverage.complete is False
    assert any("2026-09-17" in gap for gap in result.coverage_gaps)
    # Reported, never repaired: no game was invented to close the gap.
    assert result.games_created == 1


@pytest.mark.asyncio
@respx.mock
async def test_roster_refresh_makes_no_schedule_call_at_all(monkeypatch):
    """It reads the canonical slate back instead of re-fetching it, so running
    the expensive path never re-spends the schedule call."""
    _env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_roster_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "success"
    assert result.games_in_slate == 0
    assert not [c for c in respx.calls if c.request.url.host == "api.sportsdata.io"]


@pytest.mark.asyncio
@respx.mock
async def test_roster_refresh_fails_loudly_when_the_slate_cannot_be_read(monkeypatch):
    """Without a slate there is nothing to fetch rosters FOR, and proceeding
    would mean guessing which teams are playing."""
    _env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(500, text="db down"))

    async with (
        httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client,
        httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as sdio_client,
    ):
        result = await run_roster_refresh(
            supabase_client=supabase_client,
            sportsdataio_client=sdio_client,
            sportsdataio_api_key="test-key",
            today=TODAY,
        )

    assert result.status == "failed"
    assert "canonical slate" in (result.error or "")
