"""Odds Worker cost + failure hardening (2026-09-16, HQ directive "ODDS
WORKER COST + FAILURE HARDENING").

Proves the five behaviours the directive names, entirely through respx-mocked
boundaries -- **no provider call of any kind is made by this file**, which is
the point: the whole defect being fixed was discovered only by watching real
credits drain, and the fix must be testable without spending any.

  A. an unresolved game records an attempt, is NOT due again on the next
     */15 tick, retries on the backoff schedule, and recovers naturally once
     its identity is repaired;
  B. a successful FAR game keeps its ordinary 24h throttle;
  C. one bulk request services every due game on a mixed slate;
  D. an exhausted daily budget makes no provider call and returns an
     explicit, non-crashing budget-paused result;
  E. a success resets the failure/backoff state.

The regression these guard against, stated plainly: between 13:16 and 16:01
UTC on 2026-09-16, ten unresolvable games kept the due set non-empty on every
single cron tick. Twelve consecutive ticks each spent a real bulk call --
36 credits -- and persisted zero rows, because `last_polled_at` was derived
from `odds_snapshots.captured_at` and an unresolved poll writes no snapshot.
Attempt and success were the same signal and only success was recorded.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.persistence.odds_worker_poll_state import PollState
from app.workers.odds_backoff import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_MAX_SECONDS,
    OUTCOME_PROVIDER_FAILURE,
    OUTCOME_SUCCESS,
    OUTCOME_UNRESOLVED,
    backoff_elapsed,
    backoff_seconds,
    next_failure_count,
)
from app.workers.odds_worker import run_odds_worker
from app.workers.windows import Window, effective_poll_interval_seconds
from tests.adapters.the_odds_api_fixtures import load
from tests.conftest import (
    DAILY_BUDGET_GET,
    DAILY_BUDGET_INCREMENT,
    POLL_STATE_POST,
    release_default_route,
)

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"

GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"  # kickoff 2026-09-14T17:00:00Z
GAME_COWBOYS_EAGLES = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # kickoff 2026-09-14T20:25:00Z
GAME_49ERS_BILLS = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"  # kickoff 2026-09-14T20:25:00Z

DB_GAME_KC_BAL = "db-game-kc-bal"
DB_GAME_DAL_PHI = "db-game-dal-phi"
DB_GAME_SF_BUF = "db-game-sf-buf"

#: One cron tick. The interval the real `cron-odds-worker` fires on, and
#: therefore the unit every "is it due on the NEXT tick?" assertion below is
#: expressed in.
CRON_TICK = timedelta(minutes=15)


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

#: The FULL mapping set -- every team The Odds API names in the fixture
#: resolves. This is the "identity repaired" state.
_TEAM_PROVIDER_ROWS_COMPLETE = {
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

#: The BROKEN state that caused the real incident: the canonical games exist
#: and the provider returns their events, but no `the_odds_api` team mapping
#: does, so nothing can link and nothing can persist.
_TEAM_PROVIDER_ROWS_MISSING_ODDS_IDENTITY = {
    "eq.the_odds_api": [],
    "eq.sportsdataio": _TEAM_PROVIDER_ROWS_COMPLETE["eq.sportsdataio"],
}


def _mock_games(games=None):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=games if games is not None else _ALL_GAMES)
    )


def _mock_team_provider_ids(rows):
    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        ids_param = request.url.params["provider_team_id"]
        matched = [r for r in rows.get(provider_name, []) if r["provider_team_id"] in ids_param]
        return httpx.Response(200, json=matched)

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_respond)


def _mock_game_provider_ids(existing: dict | None = None):
    state = dict(existing or {})

    def _get_respond(request: httpx.Request) -> httpx.Response:
        ids_param = request.url.params.get("provider_game_id", "")
        return httpx.Response(
            200,
            json=[
                {"game_id": gid, "provider_game_id": pid}
                for pid, gid in state.items()
                if pid in ids_param
            ],
        )

    def _post_respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state[body["provider_game_id"]] = body["game_id"]
        return httpx.Response(201)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_get_respond)
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_post_respond)


def _mock_credit_ledger():
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(201, json=[{"credits_used_this_period": 3}])
    )


def _mock_odds_snapshots_insert():
    _mock_credit_ledger()
    return respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))


def _capture_poll_state_writes():
    """Records every attempt row the worker writes, so a test can assert on
    what was persisted rather than only on the returned result."""
    release_default_route(POLL_STATE_POST)
    written: list[dict] = []

    def _respond(request: httpx.Request) -> httpx.Response:
        written.append(json.loads(request.content))
        return httpx.Response(201)

    respx.post(f"{SUPABASE_URL}/rest/v1/odds_worker_poll_state").mock(side_effect=_respond)
    return written


def _mock_daily_budget(*, calls_used: int):
    release_default_route(DAILY_BUDGET_GET, DAILY_BUDGET_INCREMENT)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_daily_call_budget").mock(
        return_value=httpx.Response(200, json=[{"calls_used": calls_used}])
    )
    return respx.post(f"{SUPABASE_URL}/rest/v1/rpc/increment_odds_api_daily_calls").mock(
        return_value=httpx.Response(200, json=calls_used + 1)
    )


def _odds_response():
    return httpx.Response(200, json=load("bulk_odds_multi_game.json"))


async def _run(**kwargs):
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        return await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            **kwargs,
        )


# ===========================================================================
# Backoff policy -- pure unit tests, no I/O at all
# ===========================================================================


def test_backoff_schedule_is_deterministic_and_doubles_to_a_cap():
    assert backoff_seconds(0) == 0
    assert backoff_seconds(1) == BACKOFF_BASE_SECONDS  # 15m -- exactly one cron tick
    assert backoff_seconds(2) == 1800  # 30m
    assert backoff_seconds(3) == 3600  # 1h
    assert backoff_seconds(4) == 7200  # 2h
    assert backoff_seconds(5) == 14400  # 4h
    assert backoff_seconds(6) == BACKOFF_MAX_SECONDS  # 6h cap


def test_the_first_backoff_step_is_never_shorter_than_one_cron_tick():
    """A backoff shorter than the cron period cannot change behaviour -- the
    worker simply would not run during it. 15m is the smallest value that
    actually suppresses a tick."""
    assert BACKOFF_BASE_SECONDS == int(CRON_TICK.total_seconds())


def test_backoff_is_capped_so_a_broken_game_still_retries_four_times_a_day():
    """No permanent quarantine: even a game broken for weeks keeps retrying,
    so a repair lands within hours without anyone re-running anything."""
    for absurd in (10, 50, 10_000):
        assert backoff_seconds(absurd) == BACKOFF_MAX_SECONDS
    assert 24 * 3600 / BACKOFF_MAX_SECONDS == 4


def test_a_success_resets_the_counter_and_anything_else_increments_it():
    assert next_failure_count(current=7, outcome=OUTCOME_SUCCESS) == 0
    assert next_failure_count(current=0, outcome=OUTCOME_UNRESOLVED) == 1
    assert next_failure_count(current=3, outcome=OUTCOME_UNRESOLVED) == 4
    assert next_failure_count(current=3, outcome=OUTCOME_PROVIDER_FAILURE) == 4


def test_backoff_never_suppresses_a_game_that_has_no_failures():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    assert backoff_elapsed(now=now, last_attempt_at=now, consecutive_failure_count=0) is True
    assert backoff_elapsed(now=now, last_attempt_at=None, consecutive_failure_count=0) is True


def test_backoff_window_is_measured_from_the_last_attempt():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    # One failure -> 15m. At 14m it is still suppressed; at 15m it is not.
    assert not backoff_elapsed(
        now=now, last_attempt_at=now - timedelta(minutes=14), consecutive_failure_count=1
    )
    assert backoff_elapsed(
        now=now, last_attempt_at=now - timedelta(minutes=15), consecutive_failure_count=1
    )


# ===========================================================================
# Cadence reality -- the */15 cron floor, made explicit
# ===========================================================================


def test_three_cadence_tiers_are_floored_by_the_cron_period():
    """RAMP_60M, RAMP_15M and RAMP_5M are operationally indistinguishable
    under a */15 cron. The tier values are NOT rewritten -- this asserts the
    gap is reported honestly rather than left invisible."""
    assert effective_poll_interval_seconds(Window.FAR) == 86400
    assert effective_poll_interval_seconds(Window.RAMP_2H) == 3600
    assert effective_poll_interval_seconds(Window.RAMP_60M) == 900
    assert effective_poll_interval_seconds(Window.RAMP_15M) == 900  # specified 300
    assert effective_poll_interval_seconds(Window.RAMP_5M) == 900  # specified 120
    assert effective_poll_interval_seconds(Window.STOPPED) is None


def test_a_faster_cron_would_honour_more_tiers():
    """The floor is a deployment property, not a code one -- proving it moves
    with the cron period shows the helper reports reality rather than
    hardcoding today's."""
    assert effective_poll_interval_seconds(Window.RAMP_5M, cron_period_seconds=60) == 120
    assert effective_poll_interval_seconds(Window.RAMP_15M, cron_period_seconds=60) == 300


# ===========================================================================
# A. Unresolved game: attempt recorded, backs off, recovers after repair
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_A1_unresolved_game_records_an_attempt_not_a_success(monkeypatch):
    """The exact 2026-09-16 shape: the provider answers, but no team mapping
    exists, so nothing links and nothing persists. The attempt must still be
    recorded -- and must NOT advance `last_success_at`."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_MISSING_ODDS_IDENTITY)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    written = _capture_poll_state_writes()

    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)  # FAR, never polled
    result = await _run(now=now)

    assert result.games_due == 3
    assert result.lines_persisted == 0
    assert result.unresolved_events  # the provider's events could not resolve

    # One attempt row per due game, every one a non-success.
    assert len(written) == 3
    for row in written:
        assert row["last_attempt_outcome"] == OUTCOME_UNRESOLVED
        assert row["consecutive_failure_count"] == 1
        assert row["last_attempt_at"] is not None
        assert row["last_failure_reason"]  # never silently dropped
        # THE CRUCIAL ASSERTION: an unresolved attempt must never be able to
        # masquerade as fresh odds data to the kickoff-proximity cadence.
        assert "last_success_at" not in row


@pytest.mark.asyncio
@respx.mock
async def test_A2_an_unresolved_game_is_not_due_again_on_the_next_cron_tick(monkeypatch):
    """The regression test for the leak itself. Before this pass the same
    game came due on every single tick forever; one failure now costs it
    exactly one skipped tick."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_MISSING_ODDS_IDENTITY)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    first_attempt = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    next_tick = first_attempt + CRON_TICK - timedelta(seconds=1)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=first_attempt,
            last_attempt_outcome=OUTCOME_UNRESOLVED,
            last_success_at=None,
            consecutive_failure_count=1,
        )
        for g in _ALL_GAMES
    }

    result = await _run(now=next_tick, poll_state=state)

    assert result.games_due == 0
    assert result.games_skipped_backoff == 3
    # The whole economic point: nothing due means no bulk call at all.
    assert odds_route.call_count == 0
    assert result.credits_used_this_period is None


@pytest.mark.asyncio
@respx.mock
async def test_A3_it_retries_once_the_backoff_window_has_actually_elapsed(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_MISSING_ODDS_IDENTITY)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    written = _capture_poll_state_writes()

    first_attempt = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    now = first_attempt + timedelta(seconds=BACKOFF_BASE_SECONDS)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=first_attempt,
            last_attempt_outcome=OUTCOME_UNRESOLVED,
            last_success_at=None,
            consecutive_failure_count=1,
        )
        for g in _ALL_GAMES
    }

    result = await _run(now=now, poll_state=state)

    assert result.games_due == 3
    assert result.games_skipped_backoff == 0
    assert odds_route.call_count == 1  # retried, exactly once
    # Still failing -> the counter escalates, so the next wait is 30m.
    assert {row["consecutive_failure_count"] for row in written} == {2}
    assert backoff_seconds(2) == 1800


@pytest.mark.asyncio
@respx.mock
async def test_A4_backoff_escalates_so_a_broken_game_costs_less_and_less(monkeypatch):
    """A game stuck at 4 consecutive failures waits 2h, not 15m -- so a
    permanently-broken game stops being the reason a call is made."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_MISSING_ODDS_IDENTITY)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    last_attempt = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=last_attempt,
            last_attempt_outcome=OUTCOME_UNRESOLVED,
            last_success_at=None,
            consecutive_failure_count=4,
        )
        for g in _ALL_GAMES
    }

    # Seven cron ticks later (1h45m) it is STILL inside its 2h window.
    result = await _run(now=last_attempt + timedelta(minutes=105), poll_state=state)
    assert result.games_due == 0
    assert result.games_skipped_backoff == 3
    assert odds_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_A5_identity_repair_recovers_the_game_with_no_manual_step(monkeypatch):
    """Mirrors the real 2026-09-16 recovery: 15 team-mapping rows were
    inserted, nothing else changed, and the next natural tick linked and
    persisted everything. No quarantine had to be lifted."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)  # <-- the repair
    _mock_game_provider_ids()
    insert_route = _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    written = _capture_poll_state_writes()

    last_attempt = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=last_attempt,
            last_attempt_outcome=OUTCOME_UNRESOLVED,
            last_success_at=None,
            consecutive_failure_count=3,
        )
        for g in _ALL_GAMES
    }

    # 1h later: the 3-failure backoff (1h) has elapsed, so it retries.
    result = await _run(now=last_attempt + timedelta(hours=1), poll_state=state)

    assert result.games_due == 3
    assert result.lines_persisted > 0
    assert result.unresolved_events == []
    assert insert_route.called
    # Every game is back to zero failures and now carries a real success.
    assert {row["consecutive_failure_count"] for row in written} == {0}
    for row in written:
        assert row["last_attempt_outcome"] == OUTCOME_SUCCESS
        assert row["last_success_at"] is not None
        assert row["last_failure_reason"] is None


@pytest.mark.asyncio
@respx.mock
async def test_A6_a_provider_outage_is_recorded_as_an_attempt_too(monkeypatch):
    """Without this, an outage would leave every game reading as never-polled
    and hammering the provider on every tick for as long as it lasted."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_credit_ledger()
    respx.get(ODDS_URL).mock(return_value=httpx.Response(500, text="upstream is down"))
    written = _capture_poll_state_writes()

    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "failed"
    assert len(written) == 3
    for row in written:
        assert row["last_attempt_outcome"] == OUTCOME_PROVIDER_FAILURE
        assert row["consecutive_failure_count"] == 1
        assert "provider call failed" in row["last_failure_reason"]
        assert "last_success_at" not in row


# ===========================================================================
# B. A healthy FAR game keeps its ordinary 24h throttle
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_B1_successful_far_game_keeps_its_24h_throttle(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    # Captured 23h ago: FAR's interval is 24h, so not due yet.
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=now - timedelta(hours=23),
            last_attempt_outcome=OUTCOME_SUCCESS,
            last_success_at=now - timedelta(hours=23),
            consecutive_failure_count=0,
        )
        for g in _ALL_GAMES
    }

    result = await _run(now=now, poll_state=state)

    assert result.games_due == 0
    assert result.games_skipped_not_due == 3
    assert result.games_skipped_backoff == 0  # throttled by cadence, NOT backoff
    assert odds_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_B2_far_game_becomes_due_again_after_a_full_24h(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=now - timedelta(hours=24),
            last_attempt_outcome=OUTCOME_SUCCESS,
            last_success_at=now - timedelta(hours=24),
            consecutive_failure_count=0,
        )
        for g in _ALL_GAMES
    }

    result = await _run(now=now, poll_state=state)

    assert result.games_due == 3
    assert odds_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_B3_a_game_with_no_poll_state_row_still_honours_snapshot_history(monkeypatch):
    """Migration safety. Every game that captured before this feature shipped
    has snapshot history but no attempt row. Without the fallback, all of
    them would read as never-successful on the first run afterwards and come
    due at once -- spending a call to rediscover what odds_snapshots already
    knows."""
    _headers_env(monkeypatch)
    _mock_games()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    now = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    result = await _run(
        now=now,
        poll_state={},  # nothing migrated yet
        last_polled_at={g["id"]: now - timedelta(minutes=1) for g in _ALL_GAMES},
    )

    assert result.games_due == 0
    assert odds_route.call_count == 0


# ===========================================================================
# C. Mixed slate: one bulk request services every due game
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_C1_one_bulk_request_services_every_due_game_on_a_mixed_slate(monkeypatch):
    """The cost model's load-bearing fact: N due games cost exactly the same
    as one. This is why the budget layer counts CALLS rather than games, and
    why there is nothing to rank WITHIN a call."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    increment_route = _mock_daily_budget(calls_used=0)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")
    written = _capture_poll_state_writes()

    # 16:30 on game day: KC-BAL is 30m out (RAMP_60M), the two 20:25 games
    # are ~4h out (FAR). A genuinely mixed slate, all three due.
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.games_due == 3
    assert odds_route.call_count == 1  # ONE call, three games
    assert increment_route.call_count == 1  # and exactly one budget unit
    assert result.daily_calls_used == 1
    assert len(written) == 3  # every due game still gets its own attempt row


# ===========================================================================
# D. Exhausted daily budget: no call, explicit paused result, no crash
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_D1_exhausted_daily_budget_makes_no_provider_call(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    increment_route = _mock_daily_budget(calls_used=40)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")
    written = _capture_poll_state_writes()

    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    result = await _run(now=now)

    assert result.status == "skipped_daily_budget"
    assert result.games_due == 3  # the games WERE due -- that is why this is a distinct status
    assert odds_route.call_count == 0
    assert increment_route.call_count == 0  # a skipped call is not a spent call
    assert result.daily_calls_used == 40
    assert "daily call budget exhausted" in result.error
    # No call was made, so nothing was attempted: healthy games must not be
    # pushed into a backoff they did not earn.
    assert written == []


@pytest.mark.asyncio
@respx.mock
async def test_D2_a_budget_stop_returns_cleanly_rather_than_crashing(monkeypatch):
    """The cron must exit 0. A budget stop is a normal operating state, not a
    failure -- the same discipline master_refresh's `paused` status follows,
    which replaced a daily CRASHED deployment that looked like real breakage."""
    _headers_env(monkeypatch)
    _mock_games()
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    _mock_daily_budget(calls_used=99)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")

    result = await _run(now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc))

    assert result.status == "skipped_daily_budget"
    assert result.status != "failed"
    assert result.failures == []  # a budget stop is not a failure


@pytest.mark.asyncio
@respx.mock
async def test_D3_an_unset_budget_is_a_disclosed_no_op_not_an_invented_limit(monkeypatch):
    """Same discipline as the monthly credit guard: an unconfigured ceiling
    is never defaulted to a made-up number."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    release_default_route(DAILY_BUDGET_GET)
    budget_read = respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_daily_call_budget").mock(
        return_value=httpx.Response(200, json=[{"calls_used": 9999}])
    )
    monkeypatch.delenv("ODDS_API_MAX_CALLS_PER_DAY", raising=False)

    result = await _run(now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc))

    assert result.status != "skipped_daily_budget"
    assert odds_route.call_count == 1
    # Not even read: an unconfigured guard short-circuits before any query.
    assert budget_read.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_D4_the_reserve_holds_back_calls_for_games_close_to_kickoff(monkeypatch):
    """Priority mechanism. With the discretionary budget spent, a slate of
    only FAR games does not get a call..."""
    _headers_env(monkeypatch)
    _mock_games()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    _mock_daily_budget(calls_used=36)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")
    monkeypatch.setenv("ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP", "4")

    # Four days out: every game is FAR.
    result = await _run(now=datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc))

    assert result.status == "skipped_daily_budget"
    assert odds_route.call_count == 0
    assert "reserved for games inside 2h of kickoff" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_D5_the_reserve_is_released_for_a_ramp_tier_game(monkeypatch):
    """...but the same exhausted discretionary budget DOES release a call
    once a game is inside two hours, where movement matters most and a
    missed poll can never be made up."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    _mock_daily_budget(calls_used=36)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")
    monkeypatch.setenv("ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP", "4")

    # 16:30 -- KC-BAL kicks off at 17:00, so it is inside the 2h ramp.
    result = await _run(now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc))

    assert result.status != "skipped_daily_budget"
    assert odds_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_D6_the_hard_ceiling_still_wins_over_the_reserve(monkeypatch):
    """The reserve releases calls the ceiling still permits -- it can never
    authorize spending past the ceiling itself, however close kickoff is."""
    _headers_env(monkeypatch)
    _mock_games()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    _mock_daily_budget(calls_used=40)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")
    monkeypatch.setenv("ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP", "4")

    result = await _run(now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc))

    assert result.status == "skipped_daily_budget"
    assert "exhausted" in result.error
    assert odds_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_D7_a_cache_hit_never_consumes_the_daily_budget(monkeypatch):
    """Same rule the credit ledger already follows: no round-trip, no cost."""
    from app.adapters.cache import InMemoryCacheBackend

    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids()
    _mock_odds_snapshots_insert()
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    increment_route = _mock_daily_budget(calls_used=0)
    monkeypatch.setenv("ODDS_API_MAX_CALLS_PER_DAY", "40")

    shared_cache = InMemoryCacheBackend()
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    await _run(now=now, cache_backend=shared_cache)
    await _run(now=now, cache_backend=shared_cache)

    assert odds_route.call_count == 1  # second run served from cache
    assert increment_route.call_count == 1  # and charged only once


# ===========================================================================
# E. Success resets failure/backoff state
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_E1_one_success_clears_an_accumulated_failure_streak(monkeypatch):
    """A single genuine capture proves the game resolves, so whatever was
    wrong is over -- it returns to ordinary cadence immediately rather than
    serving out a residual penalty."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    _mock_odds_snapshots_insert()
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    written = _capture_poll_state_writes()

    last_attempt = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    state = {
        g["id"]: PollState(
            game_id=g["id"],
            last_attempt_at=last_attempt,
            last_attempt_outcome=OUTCOME_UNRESOLVED,
            last_success_at=None,
            consecutive_failure_count=6,  # at the cap
        )
        for g in _ALL_GAMES
    }

    result = await _run(now=last_attempt + timedelta(hours=6), poll_state=state)

    assert result.lines_persisted > 0
    for row in written:
        assert row["last_attempt_outcome"] == OUTCOME_SUCCESS
        assert row["consecutive_failure_count"] == 0
        assert row["last_failure_reason"] is None
        assert row["last_success_at"] is not None
    # Proven at the policy level too: zero failures means zero wait.
    assert backoff_seconds(0) == 0


@pytest.mark.asyncio
@respx.mock
async def test_E2_a_persistence_failure_is_not_recorded_as_a_success(monkeypatch):
    """Lines were fetched but nothing landed, so no game captured. Recording
    success here would both lie and re-open the leak: a repeating persistence
    fault would pay for a bulk call every tick and throw the results away."""
    _headers_env(monkeypatch)
    _mock_games()
    _mock_team_provider_ids(_TEAM_PROVIDER_ROWS_COMPLETE)
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    _mock_credit_ledger()
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(500, text="db is unhappy")
    )
    respx.get(ODDS_URL).mock(return_value=_odds_response())
    written = _capture_poll_state_writes()

    result = await _run(now=datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc))

    assert result.lines_persisted == 0
    assert any("persistence failed" in f for f in result.failures)
    for row in written:
        assert row["last_attempt_outcome"] == OUTCOME_UNRESOLVED
        assert row["consecutive_failure_count"] == 1
        assert "persistence failed" in row["last_failure_reason"]
        assert "last_success_at" not in row
