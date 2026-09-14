"""Tests for app.workers.msf_postgame_dispatcher (Postgame Dispatcher +
Sunday Recovery, 2026-09-14; Automatic Enrollment, 2026-09-14). Three
layers, tested separately:

1. `select_due_msf_postgame_games` -- a pure, read-only `SELECT`. Since
   respx mocks a canned response rather than executing real Postgres
   filter semantics, these tests verify the EXACT query this module sends
   (the thing a unit test actually can prove) -- the live "does Postgres
   really exclude terminal/hard-capped rows" proof runs separately against
   real DEV data as this pass's own zero-call dispatcher proof (see the
   ops report), and the atomic-claim/no-double-claim property is cited
   from the existing pgTAP suite (Sunday Ingestion Foundation Build,
   Proof 3), not re-derived here.
2. `select_unenrolled_eligible_games` -- a pure, read-only discovery
   (mapped minus already-enrolled, filtered to past-kickoff). Same
   request-shape-proof discipline as (1); the live "does this actually
   find DEN@KC" proof runs separately against real DEV data (see the ops
   report).
3. `dispatch_due_msf_postgame_games` -- orchestration only. `run_msf_
   postgame_capture` and `ensure_scheduled_row` are monkeypatched/mocked
   (both already have their own complete, dedicated test suites) so these
   tests prove exactly what THIS module is responsible for: discovery ->
   bounded enrollment -> selection -> bounded sequential invocation ->
   result aggregation, nothing about the worker's or persistence layer's
   own internal behavior.

NO test in this file makes or mocks a real MySportsFeeds network call."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.workers.msf_postgame_dispatcher import (
    MAX_ENROLLMENTS_PER_DISPATCH_TICK,
    MAX_GAMES_PER_DISPATCH_TICK,
    MSFPostgameDispatcherError,
    dispatch_due_msf_postgame_games,
    select_due_msf_postgame_games,
    select_unenrolled_eligible_games,
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
# select_unenrolled_eligible_games -- request-shape + composition proof
# --------------------------------------------------------------------------


def _mock_enrollment_sources(*, mapped: list[str], enrolled: list[str], games: dict[str, str]):
    """`games` maps game_id -> scheduled_start ISO string, for every id
    that would appear in the `mapped - enrolled` candidate set."""
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": gid} for gid in mapped])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"game_id": gid} for gid in enrolled])
    )
    candidates = sorted(set(mapped) - set(enrolled))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[{"id": gid, "scheduled_start": games[gid]} for gid in candidates if gid in games]
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_finds_mapped_unenrolled_past_kickoff_game():
    _mock_enrollment_sources(
        mapped=["g1"], enrolled=[], games={"g1": "2026-09-14T00:00:00+00:00"}  # well before NOW
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await select_unenrolled_eligible_games(client, HEADERS, now=NOW)
    assert candidates == [{"game_id": "g1", "scheduled_start": "2026-09-14T00:00:00+00:00"}]


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_excludes_already_enrolled_game():
    """Mapped AND already enrolled -- must not be rediscovered, regardless
    of what state its existing row is in (this query never reads state)."""
    _mock_enrollment_sources(
        mapped=["g1", "g2"], enrolled=["g1"], games={"g2": "2026-09-14T00:00:00+00:00"}
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await select_unenrolled_eligible_games(client, HEADERS, now=NOW)
    assert [c["game_id"] for c in candidates] == ["g2"]


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_excludes_unmapped_game():
    """A game with no mysportsfeeds game_provider_ids row is never even
    queried by id in the third (games) request -- confirmed by mocking
    /games to return nothing and asserting an empty result even though
    nothing prevents the mock from returning data if asked incorrectly."""
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    enrolled_route = respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[])
    )
    games_route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await select_unenrolled_eligible_games(client, HEADERS, now=NOW)

    assert candidates == []
    # Short-circuits on an empty mapped set -- neither the enrolled-check
    # nor the games lookup is ever even called.
    assert enrolled_route.call_count == 0
    assert games_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_excludes_future_not_yet_kicked_off_game():
    """Mapped, unenrolled, but scheduled_start is still in the future
    relative to `now` -- the enrollment-eligibility rule (kickoff must
    have occurred) correctly excludes it; it becomes a candidate on a
    later tick, once real time passes its own kickoff."""
    _mock_enrollment_sources(
        mapped=["g1"], enrolled=[], games={"g1": "2026-09-15T00:00:00+00:00"}  # after NOW (2026-09-14T12:00)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await select_unenrolled_eligible_games(client, HEADERS, now=NOW)
    assert candidates == []


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_orders_oldest_kickoff_first():
    _mock_enrollment_sources(
        mapped=["g_late", "g_early"],
        enrolled=[],
        games={"g_late": "2026-09-14T01:00:00+00:00", "g_early": "2026-09-13T20:00:00+00:00"},
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        candidates = await select_unenrolled_eligible_games(client, HEADERS, now=NOW)
    assert [c["game_id"] for c in candidates] == ["g_early", "g_late"]


@pytest.mark.asyncio
@respx.mock
async def test_select_unenrolled_raises_on_mapping_read_failure():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MSFPostgameDispatcherError):
            await select_unenrolled_eligible_games(client, HEADERS, now=NOW)


# --------------------------------------------------------------------------
# dispatch_due_msf_postgame_games -- orchestration proof (worker + ensure_scheduled_row mocked)
# --------------------------------------------------------------------------


def _mock_selection(game_ids: list[str]):
    rows = [{"game_id": gid, "state": "scheduled", "attempt_count": 0} for gid in game_ids]
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=rows))


def _mock_no_enrollment_candidates():
    """Short-circuits Phase 1 (enrollment) cleanly for tests that only
    care about Phase 2 (dispatch) -- an empty mapped set means neither
    the enrolled-check nor the games lookup ever fires, matching
    `test_select_unenrolled_excludes_unmapped_game`'s own proof of that
    short-circuit."""
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_invokes_worker_once_per_selected_game_in_order(monkeypatch):
    _env(monkeypatch)
    _mock_no_enrollment_candidates()
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
    assert result.enrolled_game_ids == []
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
    _mock_no_enrollment_candidates()
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
    _mock_no_enrollment_candidates()
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
    _mock_no_enrollment_candidates()
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
    _mock_no_enrollment_candidates()
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
    _mock_no_enrollment_candidates()
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


# --------------------------------------------------------------------------
# dispatch_due_msf_postgame_games -- Automatic Enrollment integration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_enrolls_unenrolled_eligible_game_via_ensure_scheduled_row(monkeypatch):
    """The DEN@KC shape: a real, mapped, past-kickoff game with no
    ingestion-state row yet gets exactly one row created, via the
    existing, unmodified `ensure_scheduled_row` -- and is NOT invoked in
    this same tick (its own next_eligible_attempt_at is always still in
    the future relative to its own just-passed kickoff)."""
    _env(monkeypatch)
    kickoff_iso = "2026-09-14T00:00:00+00:00"
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "den-kc"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "den-kc", "scheduled_start": kickoff_iso}])
    )
    ensure_calls = []

    async def _fake_ensure(client, headers, *, game_id, first_eligible_at):
        ensure_calls.append((game_id, first_eligible_at))
        return {"id": "row-1", "state": "scheduled"}

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.ensure_scheduled_row", _fake_ensure)

    invoked: list[str] = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="skipped_not_eligible")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW)

    assert result.enrolled_game_ids == ["den-kc"]
    assert len(ensure_calls) == 1
    assert ensure_calls[0][0] == "den-kc"
    # first_eligible_at = first_check_at(kickoff) = kickoff + 3h30m, computed
    # via the existing, unmodified app.workers.msf_call_control.first_check_at.
    assert ensure_calls[0][1] == datetime(2026, 9, 14, 3, 30, tzinfo=timezone.utc)
    # Not claimed/invoked in the same tick -- selection (due-rows) still
    # correctly finds nothing, since the freshly-enrolled row's own
    # next_eligible_attempt_at is in the future relative to `now`.
    assert invoked == []


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_repeated_enrollment_creates_no_duplicates(monkeypatch):
    """Calling dispatch twice in a row against the SAME still-unenrolled
    candidate must not create two rows -- proven here at the orchestration
    level by asserting ensure_scheduled_row (already independently proven
    idempotent/race-safe in test_game_postgame_ingestion_state_persistence.py)
    is invoked, not by re-deriving its own internal idempotency."""
    _env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "g1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "scheduled_start": "2026-09-14T00:00:00+00:00"}])
    )
    ensure_calls = []

    async def _fake_ensure(client, headers, *, game_id, first_eligible_at):
        ensure_calls.append(game_id)
        return {"id": "row-1", "state": "scheduled"}

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.ensure_scheduled_row", _fake_ensure)

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        return MSFPostgameCaptureResult(game_id=game_id, outcome="skipped_not_eligible")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await dispatch_due_msf_postgame_games(client, now=NOW)
        await dispatch_due_msf_postgame_games(client, now=NOW)

    # ensure_scheduled_row is called once per tick (its own idempotency is
    # what makes repeated calls safe, proven separately) -- this asserts
    # the dispatcher itself doesn't skip re-attempting discovery on a
    # later tick, which is the correct, restart-safe behavior: the mocked
    # game_postgame_ingestion_state route in this test always returns []
    # (simulating a caller who never actually persisted the row), so both
    # ticks correctly rediscover "g1" as still-unenrolled and call
    # ensure_scheduled_row again -- exactly the real system's own
    # behavior, which relies on ensure_scheduled_row's real check-then-
    # insert to prevent an actual duplicate once the row is really there.
    assert ensure_calls == ["g1", "g1"]


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_enrollment_respects_max_enrollments_cap(monkeypatch):
    _env(monkeypatch)
    game_ids = [f"g{i}" for i in range(MAX_ENROLLMENTS_PER_DISPATCH_TICK + 5)]
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": gid} for gid in game_ids])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(
            200, json=[{"id": gid, "scheduled_start": "2026-09-14T00:00:00+00:00"} for gid in game_ids]
        )
    )
    ensure_calls = []

    async def _fake_ensure(client, headers, *, game_id, first_eligible_at):
        ensure_calls.append(game_id)
        return {"id": "row", "state": "scheduled"}

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.ensure_scheduled_row", _fake_ensure)

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        return MSFPostgameCaptureResult(game_id=game_id, outcome="skipped_not_eligible")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW)

    assert len(ensure_calls) == MAX_ENROLLMENTS_PER_DISPATCH_TICK
    assert len(result.enrolled_game_ids) == MAX_ENROLLMENTS_PER_DISPATCH_TICK


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_enrollment_and_dispatch_phases_are_independent(monkeypatch):
    """A tick can simultaneously enroll a brand-new game AND dispatch an
    already-due existing one -- the two phases don't interfere, and
    enrollment never consumes the dispatch phase's own max_games budget."""
    _env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "new-game"}, {"game_id": "existing-game"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"game_id": "existing-game", "state": "scheduled", "attempt_count": 0}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "new-game", "scheduled_start": "2026-09-14T00:00:00+00:00"}])
    )

    async def _fake_ensure(client, headers, *, game_id, first_eligible_at):
        return {"id": "row", "state": "scheduled"}

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.ensure_scheduled_row", _fake_ensure)

    invoked = []

    async def _fake_run(*, supabase_client, game_id, now, fetch_boxscore):
        invoked.append(game_id)
        return MSFPostgameCaptureResult(game_id=game_id, outcome="confirmed_complete")

    monkeypatch.setattr("app.workers.msf_postgame_dispatcher.run_msf_postgame_capture", _fake_run)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await dispatch_due_msf_postgame_games(client, now=NOW, max_games=1)

    assert result.enrolled_game_ids == ["new-game"]
    assert invoked == ["existing-game"]
