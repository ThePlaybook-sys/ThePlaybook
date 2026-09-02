"""Phase 7 Milestone 7.0B.1 (2026-09-02): proves the adaptive cadence
built in `app.workers.windows` actually survives repeated, genuinely
STATELESS invocations of `POST /v1/internal/odds-worker/run` -- the
concrete concern HQ raised after Gate A: "a worker that is called every 5
minutes must not treat every game as never polled."

**Audit finding (documented here, not just asserted):** Gate A already
built the fix -- `app.persistence.odds_snapshots.read_last_polled_at()`
derives each game's last-successful-capture time from already-persisted
`odds_snapshots.captured_at` history, and the endpoint
(`app.main.internal_run_odds_worker`) calls it fresh on every request
before invoking `run_odds_worker`. No Python-level state is shared
between requests in this test file at all -- each `client.post(...)` call
below is a genuinely independent HTTP call through FastAPI's TestClient,
exactly mirroring what two separate cron ticks (or two separate container
processes, or a redeploy in between) would do. The only thing that
carries information between them is the fake Supabase table itself,
proving the mechanism, not assuming it.

Uses the same stateful-mock convention `tests/test_odds_worker.py`
already established for `game_provider_ids` (`_mock_game_provider_ids`),
extended here to `odds_snapshots` itself: one shared in-memory row list
that both the GET `read_last_polled_at` makes and the POST
`persist_odds_lines` makes read from / write to, with `captured_at` set
server-side from a controllable clock (mirroring the real column's
`default now()`, which the real INSERT payload never sets client-side)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app
from app.persistence.odds_snapshots import read_last_polled_at
from app.workers.odds_worker import run_odds_worker
from tests.test_odds_worker import (
    DB_GAME_DAL_PHI,
    DB_GAME_KC_BAL,
    DB_GAME_SF_BUF,
    GAME_CHIEFS_RAVENS,
    GAME_COWBOYS_EAGLES,
    GAME_49ERS_BILLS,
    _game_row,
    _mock_game_provider_ids,
    _mock_team_provider_ids,
    _odds_response,
)

client = TestClient(app)
SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"


def _set_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-the-odds-api-key")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")


def _mock_games_at(games: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_odds_snapshots_stateful(clock: dict):
    """`clock` is a mutable `{"now": datetime}` the test advances between
    calls -- simulating real elapsed wall-clock time between cron ticks,
    without any of this module's own Python state leaking into what the
    endpoint itself sees (the endpoint never receives `clock` -- it always
    calls `datetime.now(timezone.utc)` internally via `run_odds_worker`'s
    own default). The `now` this test controls only sets what a
    successful INSERT's server-side `captured_at` becomes; the endpoint's
    real `now` is wall-clock and therefore effectively identical since
    these tests run near-instantly -- immaterial for what's being proven
    here (whether persisted history round-trips correctly), which is
    orthogonal to `classify_window`'s own already-tested boundary math."""
    rows: list[dict] = []

    def _get_respond(request: httpx.Request) -> httpx.Response:
        ordered = sorted(rows, key=lambda r: r["captured_at"], reverse=True)
        return httpx.Response(200, json=[{"game_id": r["game_id"], "captured_at": r["captured_at"]} for r in ordered])

    def _post_respond(request: httpx.Request) -> httpx.Response:
        new_rows = json.loads(request.content)
        now_iso = clock["now"].isoformat().replace("+00:00", "Z")
        for r in new_rows:
            stored = dict(r)
            stored["captured_at"] = now_iso
            rows.append(stored)
        return httpx.Response(201, json=new_rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(side_effect=_get_respond)
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(side_effect=_post_respond)
    return post_route, rows


_KICKOFF = datetime(2026, 9, 14, 17, 20, tzinfo=timezone.utc)  # 50 min after T0 below
_T0 = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)  # kickoff - 50min -> RAMP_60M (interval 900s)

_GAME_ROW = _game_row(game_id=DB_GAME_KC_BAL, home="KC", away="BAL", scheduled_start=_KICKOFF.isoformat())


async def _run_one_cycle(*, now: datetime):
    """Mirrors `app.main.internal_run_odds_worker`'s own real call
    sequence exactly (`read_last_polled_at()` then `run_odds_worker`),
    but as a direct call rather than through `TestClient` -- needed only
    for the two tests below that must control `now` precisely (kickoff
    proximity / window classification), since the real endpoint
    deliberately has no way to inject a fake wall clock (correct for
    production; `run_odds_worker`'s own `now` parameter already exists
    for exactly this testing purpose, the same pattern
    `tests/test_odds_worker.py` already uses throughout). Every other
    test in this file goes through the real HTTP endpoint instead,
    proven unnecessary here since real wall-clock time barely moves
    within a single test run."""
    os.environ["SUPABASE_URL"] = SUPABASE_URL
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
    last_polled_at = await read_last_polled_at()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=ODDS_API_URL
    ) as odds_client:
        return await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-the-odds-api-key",
            now=now,
            last_polled_at=last_polled_at,
        )


@respx.mock
def test_first_ever_invocation_treats_the_game_as_due(monkeypatch):
    _set_env(monkeypatch)
    _mock_games_at([_GAME_ROW])
    _mock_team_provider_ids()
    _mock_game_provider_ids(existing={GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL})
    _mock_odds_snapshots_stateful({"now": _T0})
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    response = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert response.status_code == 200
    assert response.json()["games_due"] == 1
    assert odds_route.call_count == 1


@respx.mock
def test_immediate_second_stateless_invocation_is_not_due(monkeypatch):
    """The critical proof: a SECOND, entirely independent HTTP call (no
    shared Python object between it and the first) must see the row the
    first call persisted and correctly conclude the game isn't due yet --
    this is exactly the "repeated stateless HTTP invocations" scenario
    HQ's directive named."""
    _set_env(monkeypatch)
    _mock_games_at([_GAME_ROW])
    _mock_team_provider_ids()
    _mock_game_provider_ids(existing={GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL})
    _mock_odds_snapshots_stateful({"now": _T0})
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    first = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})
    second = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert first.json()["games_due"] == 1
    assert second.json()["games_due"] == 0
    assert second.json()["games_skipped_not_due"] == 1
    assert odds_route.call_count == 1  # not 2 -- the second call made zero provider requests


@pytest.mark.asyncio
@respx.mock
async def test_due_state_returns_after_the_correct_elapsed_window(monkeypatch):
    """RAMP_60M's own poll interval is 900s (15 min). 16 minutes after the
    first successful capture, the game must become due again. Two fully
    independent calls to `_run_one_cycle` -- each one calls
    `read_last_polled_at()` fresh, exactly like a real stateless HTTP
    invocation would -- with only the fake Supabase table carrying
    information between them, `now` advanced to simulate real elapsed
    wall-clock time between two cron ticks."""
    _set_env(monkeypatch)
    _mock_games_at([_GAME_ROW])
    _mock_team_provider_ids()
    _mock_game_provider_ids(existing={GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL})
    clock = {"now": _T0}
    _mock_odds_snapshots_stateful(clock)
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    first = await _run_one_cycle(now=_T0)
    clock["now"] = _T0 + timedelta(minutes=16)
    third = await _run_one_cycle(now=_T0 + timedelta(minutes=16))

    assert first.games_due == 1
    assert third.games_due == 1
    assert odds_route.call_count == 2


@respx.mock
def test_failed_provider_fetch_does_not_advance_cadence_state(monkeypatch):
    """A 500 from the provider must not falsely make the next invocation
    believe the game was successfully captured -- `run_odds_worker`
    itself already fails the whole cycle without persisting anything on a
    `ProviderError`; this proves that behavior actually round-trips
    through `read_last_polled_at` into the NEXT stateless call, not just
    that this one call reported `status="failed"`."""
    _set_env(monkeypatch)
    _mock_games_at([_GAME_ROW])
    _mock_team_provider_ids()
    _mock_game_provider_ids(existing={GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL})
    _mock_odds_snapshots_stateful({"now": _T0})
    odds_route = respx.get(ODDS_URL).mock(return_value=httpx.Response(500, text="provider outage"))

    first = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})
    second = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert first.json()["status"] == "failed"
    assert second.json()["games_due"] == 1  # still due -- the failed attempt never persisted a row
    assert odds_route.call_count == 2  # both calls genuinely tried the provider


@respx.mock
def test_unresolved_event_does_not_advance_cadence_state(monkeypatch):
    """The provider response resolves to NO known game (unlinked, no
    matching team_provider_ids row) -- `persist_odds_lines` must skip it,
    not write a row under any game_id, so the next invocation still sees
    this game as due rather than incorrectly believing it was captured."""
    _set_env(monkeypatch)
    _mock_games_at([_GAME_ROW])
    # No team_provider_ids rows at all -> the response's event can never link to DB_GAME_KC_BAL.
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    _mock_game_provider_ids(existing={})
    _mock_odds_snapshots_stateful({"now": _T0})
    respx.get(ODDS_URL).mock(return_value=_odds_response())

    first = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})
    second = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert first.json()["lines_persisted"] == 0
    assert second.json()["games_due"] == 1  # still due -- nothing was ever actually captured for it


@pytest.mark.asyncio
@respx.mock
async def test_post_kickoff_game_never_becomes_due_regardless_of_capture_history(monkeypatch):
    """STOPPED overrides everything, including a stale/absent capture
    history -- this milestone's new mechanism must not accidentally make
    a kicked-off game look "due" just because it was never captured."""
    _set_env(monkeypatch)
    already_kicked_off = _game_row(
        game_id=DB_GAME_DAL_PHI, home="DAL", away="PHI", scheduled_start=(_T0 - timedelta(hours=1)).isoformat()
    )
    _mock_games_at([already_kicked_off])
    _mock_team_provider_ids()
    _mock_game_provider_ids(existing={GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI})
    _mock_odds_snapshots_stateful({"now": _T0})
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())

    result = await _run_one_cycle(now=_T0)

    assert result.games_due == 0
    assert odds_route.call_count == 0


@respx.mock
def test_all_games_recently_captured_means_zero_provider_calls_end_to_end(monkeypatch):
    """The full-fleet version of Gate A's own
    `test_no_games_due_skips_the_provider_call_entirely`, proven through
    this milestone's real derived-cadence mechanism specifically: every
    candidate game already has a fresh enough `read_last_polled_at` entry
    -> zero provider requests, end to end through the real HTTP boundary."""
    _set_env(monkeypatch)
    games = [
        _game_row(game_id=DB_GAME_KC_BAL, home="KC", away="BAL", scheduled_start=_KICKOFF.isoformat()),
        _game_row(
            game_id=DB_GAME_DAL_PHI, home="DAL", away="PHI", scheduled_start=(_T0 + timedelta(minutes=50)).isoformat()
        ),
        _game_row(
            game_id=DB_GAME_SF_BUF, home="SF", away="BUF", scheduled_start=(_T0 + timedelta(minutes=50)).isoformat()
        ),
    ]
    _mock_games_at(games)
    _mock_team_provider_ids()
    _mock_game_provider_ids(
        existing={
            GAME_CHIEFS_RAVENS: DB_GAME_KC_BAL,
            GAME_COWBOYS_EAGLES: DB_GAME_DAL_PHI,
            GAME_49ERS_BILLS: DB_GAME_SF_BUF,
        }
    )
    odds_route = respx.get(ODDS_URL).mock(return_value=_odds_response())
    _mock_odds_snapshots_stateful({"now": _T0})

    first = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})
    second = client.post("/v1/internal/odds-worker/run", headers={"X-Internal-Token": "correct-token"})

    assert first.json()["games_due"] == 3
    assert second.json()["games_due"] == 0
    assert odds_route.call_count == 1
