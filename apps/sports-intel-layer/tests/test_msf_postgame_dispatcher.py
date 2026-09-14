"""Tests for app.workers.msf_postgame_dispatcher (Postgame Dispatcher +
Sunday Recovery, 2026-09-14). Two layers, tested separately:

1. `select_due_msf_postgame_games` -- a pure, read-only `SELECT`. Since
   respx mocks a canned response rather than executing real Postgres
   filter semantics, these tests verify the EXACT query this module sends
   (the thing a unit test actually can prove) -- the live "does Postgres
   really exclude terminal/hard-capped rows" proof runs separately against
   real DEV data as this pass's own zero-call dispatcher proof (see the
   ops report), and the atomic-claim/no-double-claim property is cited
   from the existing pgTAP suite (Sunday Ingestion Foundation Build,
   Proof 3), not re-derived here.
2. `dispatch_due_msf_postgame_games` -- orchestration only. `run_msf_
   postgame_capture` is monkeypatched (it already has its own complete,
   dedicated test suite in test_msf_postgame_worker.py) so these tests
   prove exactly what THIS module is responsible for: selection -> bounded
   sequential invocation -> result aggregation, nothing about the worker's
   own internal behavior.

NO test in this file makes or mocks a real MySportsFeeds network call."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.workers.msf_postgame_dispatcher import (
    MAX_GAMES_PER_DISPATCH_TICK,
    MSFPostgameDispatcherError,
    dispatch_due_msf_postgame_games,
    select_due_msf_postgame_games,
)
from app.workers.msf_postgame_worker import MSFPostgameCaptureResult

SUPABASE_URL = "https://test-project.supabase.co"
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
HEADERS = {"Authorization": "Bearer x", "apikey": "x"}


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


# --------------------------------------------------------------------------
# select_due_msf_postgame_games -- request-shape proof
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_select_due_games_sends_correct_filters_and_ordering():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1", "state": "scheduled", "attempt_count": 0}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await select_due_msf_postgame_games(client, HEADERS, now=NOW)

    assert rows == [{"game_id": "g1", "state": "scheduled", "attempt_count": 0}]
    sent = route.calls.last.request.url.params
    assert sent["provider_name"] == "eq.mysportsfeeds"
    assert sent["state"] == "in.(scheduled,eligible_for_postgame_check,validated)"
    assert sent["attempt_count"] == "lt.4"
    assert sent["or"] == f"(state.eq.validated,next_eligible_attempt_at.lte.{NOW.isoformat()})"
    assert sent["order"] == "next_eligible_attempt_at.asc.nullsfirst"


@pytest.mark.asyncio
@respx.mock
async def test_select_due_games_raises_on_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(500, text="boom")
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MSFPostgameDispatcherError):
            await select_due_msf_postgame_games(client, HEADERS, now=NOW)


@pytest.mark.asyncio
@respx.mock
async def test_select_due_games_returns_empty_list_for_no_due_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await select_due_msf_postgame_games(client, HEADERS, now=NOW)
    assert rows == []


# --------------------------------------------------------------------------
# dispatch_due_msf_postgame_games -- orchestration proof (worker mocked)
# --------------------------------------------------------------------------


def _mock_selection(game_ids: list[str]):
    rows = [{"game_id": gid, "state": "scheduled", "attempt_count": 0} for gid in game_ids]
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=rows))


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_invokes_worker_once_per_selected_game_in_order(monkeypatch):
    _env(monkeypatch)
    _mock_selection(["g1", "g2", "g3"])
    invoked: list[str] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete", state="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW, max_games=10)

    assert invoked == ["g1", "g2", "g3"]
    assert result.considered == 3
    assert result.selected_game_ids == ["g1", "g2", "g3"]
    assert result.invoked_game_ids == ["g1", "g2", "g3"]
    assert [r.outcome for r in result.results] == ["confirmed_complete"] * 3


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_respects_max_games_cap_leaving_the_rest_untouched(monkeypatch):
    """13-game-scale proof, mocked: more due rows than the per-tick cap
    exist (mirrors the real Sunday recovery shape) -- only the first
    `max_games` (oldest-overdue-first, per selection ordering) are
    invoked; the rest are reported as selected but not invoked, and the
    worker is never called for them at all this tick."""
    _env(monkeypatch)
    game_ids = [f"g{i}" for i in range(13)]
    _mock_selection(game_ids)
    invoked: list[str] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete", state="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW, max_games=4)

    assert invoked == game_ids[:4]
    assert result.considered == 13
    assert result.selected_game_ids == game_ids
    assert result.invoked_game_ids == game_ids[:4]
    assert len(result.results) == 4


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_default_cap_matches_module_constant(monkeypatch):
    _env(monkeypatch)
    game_ids = [f"g{i}" for i in range(MAX_GAMES_PER_DISPATCH_TICK + 5)]
    _mock_selection(game_ids)
    invoked: list[str] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete", state="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW)

    assert len(invoked) == MAX_GAMES_PER_DISPATCH_TICK


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_processes_strictly_sequentially_not_concurrently(monkeypatch):
    """Proves no burst: each invocation must fully complete (including an
    injected delay) before the next one starts -- if the dispatcher ever
    switched to concurrent invocation, the recorded start/end timestamps
    would overlap."""
    import asyncio

    _env(monkeypatch)
    _mock_selection(["g1", "g2", "g3"])
    events: list[tuple[str, str]] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        events.append((game_id, "start"))
        await asyncio.sleep(0.01)
        events.append((game_id, "end"))
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete", state="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await dispatch_due_msf_postgame_games(client, now=NOW, max_games=10)

    assert events == [
        ("g1", "start"), ("g1", "end"),
        ("g2", "start"), ("g2", "end"),
        ("g3", "start"), ("g3", "end"),
    ]


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_forwards_fetch_boxscore_injection_seam(monkeypatch):
    """The zero-call proof's own mechanism: a caller-supplied
    `fetch_boxscore` reaches the worker unchanged, so a dispatch run can
    be proven against real selection data with zero real network calls."""
    _env(monkeypatch)
    _mock_selection(["g1"])
    received = {}

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        received["fetch_boxscore"] = fetch_boxscore
        return MSFPostgameCaptureResult(game_id=game_id, outcome="not_ready", state="eligible_for_postgame_check")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async def _sentinel_fetch(*, season, msf_game_id):
        raise AssertionError("must not actually be called by this test")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await dispatch_due_msf_postgame_games(client, now=NOW, fetch_boxscore=_sentinel_fetch, max_games=10)

    assert received["fetch_boxscore"] is _sentinel_fetch


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_with_no_due_games_invokes_worker_zero_times(monkeypatch):
    _env(monkeypatch)
    _mock_selection([])
    invoked: list[str] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW)

    assert invoked == []
    assert result.considered == 0
    assert result.results == []
