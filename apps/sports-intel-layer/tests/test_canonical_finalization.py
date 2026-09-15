"""Tests for `app.workers.canonical_finalization` -- the MSF -> canonical
finalization wiring (2026-09-15, HQ-authorized "CANONICAL SCHEDULE +
FINALIZATION HARDENING").

Every Supabase read/write is respx-mocked and NO provider adapter is imported
anywhere in this module -- which is itself part of what's being proven: this
path finalizes games from already-persisted evidence and never calls a vendor.

The payload fixtures mirror the real shape verified live in dev
(`body.game.playedStatus`, `body.scoring.homeScoreTotal/awayScoreTotal`), and
the score used throughout is a real Week 1 result (NE @ SEA, 13-10).
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.workers.canonical_finalization import (
    extract_final_score,
    finalize_completed_games,
    is_completed_observation,
    resolve_canonical_capture,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _state_row(
    *,
    game_id: str = "game-1",
    raw_capture_id: str | None = "capture-1",
    captured_at: str = "2026-09-15T04:00:00+00:00",
    row_id: str = "state-1",
) -> dict:
    return {
        "id": row_id,
        "game_id": game_id,
        "provider_name": "mysportsfeeds",
        "state": "confirmed_complete",
        "raw_capture_id": raw_capture_id,
        "captured_at": captured_at,
    }


def _boxscore(*, played_status: str = "COMPLETED", home=13, away=10) -> dict:
    payload: dict = {"body": {"game": {"playedStatus": played_status}, "scoring": {}}}
    if home is not None:
        payload["body"]["scoring"]["homeScoreTotal"] = home
    if away is not None:
        payload["body"]["scoring"]["awayScoreTotal"] = away
    return payload


def _mock_env(monkeypatch):
    """`read_game_event` builds its own client from env (it predates this
    worker and is shared with the MSF postgame path -- not refactored here)."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_states(rows: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=rows)
    )


def _mock_captures(by_id: dict[str, dict | None]):
    def _respond(request: httpx.Request) -> httpx.Response:
        event_id = request.url.params["id"].removeprefix("eq.")
        payload = by_id.get(event_id)
        if payload is None:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"id": event_id, "raw_payload": payload}])

    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(side_effect=_respond)


def _mock_finalize(*, already_finalized: set[str] | None = None):
    """PATCH /games guarded on `finalized_at=is.null`. The mock enforces that
    guard itself: a game in `already_finalized` returns zero rows, exactly as
    Postgres would."""
    already_finalized = already_finalized or set()

    def _respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["finalized_at"] == "is.null", "terminal guard missing"
        game_id = request.url.params["id"].removeprefix("eq.")
        if game_id in already_finalized:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"id": game_id}])

    return respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)


# --------------------------------------------------------------------------
# Payload authority -- the capture is the evidence, the state row is bookkeeping.
# --------------------------------------------------------------------------


def test_only_a_completed_payload_authorizes_finalization():
    assert is_completed_observation(_boxscore()) is True
    assert is_completed_observation(_boxscore(played_status="LIVE")) is False
    assert is_completed_observation(_boxscore(played_status="UNPLAYED")) is False
    assert is_completed_observation({"body": {}}) is False
    assert is_completed_observation({}) is False


def test_score_is_copied_both_sides_or_not_at_all():
    score = extract_final_score(_boxscore(home=13, away=10))
    assert score is not None and score.to_json() == {"home": 13, "away": 10}
    # A one-sided score is never half-written.
    assert extract_final_score(_boxscore(home=13, away=None)) is None
    assert extract_final_score(_boxscore(home=None, away=10)) is None
    assert extract_final_score({"body": {"game": {"playedStatus": "COMPLETED"}}}) is None


def test_a_zero_zero_score_is_a_real_score_not_a_missing_one():
    """`0` is falsy in Python -- a truthiness check here would silently drop a
    legitimate shutout."""
    score = extract_final_score(_boxscore(home=0, away=0))
    assert score is not None and score.to_json() == {"home": 0, "away": 0}


def test_string_scores_survive_a_json_round_trip_but_garbage_does_not():
    assert extract_final_score(_boxscore(home="13", away="10")).to_json() == {"home": 13, "away": 10}
    assert extract_final_score(_boxscore(home="thirteen", away=10)) is None
    # bools are ints in Python; they are not scores.
    assert extract_final_score(_boxscore(home=True, away=10)) is None


# --------------------------------------------------------------------------
# Duplicate captures.
# --------------------------------------------------------------------------


def test_duplicate_captures_for_one_game_collapse_to_the_latest():
    rows = [
        _state_row(row_id="a", raw_capture_id="cap-old", captured_at="2026-09-15T01:00:00+00:00"),
        _state_row(row_id="b", raw_capture_id="cap-new", captured_at="2026-09-15T05:00:00+00:00"),
    ]
    canonical, collapsed = resolve_canonical_capture(rows)
    assert collapsed == 1
    assert len(canonical) == 1
    assert canonical[0]["raw_capture_id"] == "cap-new"


def test_distinct_games_are_never_collapsed_into_each_other():
    rows = [_state_row(game_id="g1", row_id="a"), _state_row(game_id="g2", row_id="b")]
    canonical, collapsed = resolve_canonical_capture(rows)
    assert collapsed == 0
    assert {row["game_id"] for row in canonical} == {"g1", "g2"}


def test_tied_timestamps_resolve_deterministically_rather_than_arbitrarily():
    rows = [
        _state_row(row_id="row-b", raw_capture_id="cap-b", captured_at="2026-09-15T05:00:00+00:00"),
        _state_row(row_id="row-a", raw_capture_id="cap-a", captured_at="2026-09-15T05:00:00+00:00"),
    ]
    first, _ = resolve_canonical_capture(rows)
    second, _ = resolve_canonical_capture(list(reversed(rows)))
    assert first[0]["raw_capture_id"] == second[0]["raw_capture_id"]


# --------------------------------------------------------------------------
# End-to-end orchestration.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_completed_game_is_finalized_with_the_persisted_score(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([_state_row()])
    _mock_captures({"capture-1": _boxscore(home=13, away=10)})
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert (result.considered, result.finalized, result.skipped) == (1, 1, 0)
    body = json.loads(patch_route.calls.last.request.content)
    assert body["status"] == "final"
    assert body["final_score"] == {"home": 13, "away": 10}
    assert body["finalized_at"]  # stamped, never left null
    assert result.outcomes[0].final_score == {"home": 13, "away": 10}


@pytest.mark.asyncio
@respx.mock
async def test_zero_provider_calls_are_made(monkeypatch):
    """respx is in strict mode here: any request to a non-Supabase host would
    raise `AllMockedAssertionError` rather than pass silently."""
    _mock_env(monkeypatch)
    _mock_states([_state_row()])
    _mock_captures({"capture-1": _boxscore()})
    _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await finalize_completed_games(client, _headers())

    hosts = {call.request.url.host for call in respx.calls}
    assert hosts == {"test-project.supabase.co"}


@pytest.mark.asyncio
@respx.mock
async def test_rerunning_is_idempotent_and_reports_already_finalized(monkeypatch):
    """The DB guard, not a prior read, is what makes this safe -- a second run
    writes nothing and never overwrites the original finalization moment."""
    _mock_env(monkeypatch)
    _mock_states([_state_row()])
    _mock_captures({"capture-1": _boxscore()})
    _mock_finalize(already_finalized={"game-1"})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert (result.finalized, result.already_finalized, result.skipped) == (0, 1, 0)


@pytest.mark.asyncio
@respx.mock
async def test_duplicate_captures_do_not_double_process(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states(
        [
            _state_row(row_id="a", raw_capture_id="cap-old", captured_at="2026-09-15T01:00:00+00:00"),
            _state_row(row_id="b", raw_capture_id="cap-new", captured_at="2026-09-15T05:00:00+00:00"),
        ]
    )
    _mock_captures({"cap-old": _boxscore(home=7, away=3), "cap-new": _boxscore(home=13, away=10)})
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.duplicate_captures_collapsed == 1
    assert result.considered == 1
    assert patch_route.call_count == 1  # exactly one write, not two
    assert json.loads(patch_route.calls.last.request.content)["final_score"] == {"home": 13, "away": 10}


@pytest.mark.asyncio
@respx.mock
async def test_a_non_completed_payload_never_finalizes_whatever_the_state_says(monkeypatch):
    """The state row reads `confirmed_complete`, the payload says LIVE. The
    payload wins and nothing is written."""
    _mock_env(monkeypatch)
    _mock_states([_state_row()])
    _mock_captures({"capture-1": _boxscore(played_status="LIVE")})
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.skipped == 1
    assert result.outcomes[0].reason == "observation_not_completed"
    assert not patch_route.called


@pytest.mark.asyncio
@respx.mock
async def test_an_unparseable_score_is_skipped_with_a_reason_not_guessed(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([_state_row()])
    _mock_captures({"capture-1": _boxscore(home=13, away=None)})
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.outcomes[0].reason == "incomplete_or_unparseable_score"
    assert not patch_route.called


@pytest.mark.asyncio
@respx.mock
async def test_a_state_row_without_a_capture_is_skipped_not_finalized(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([_state_row(raw_capture_id=None)])
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.outcomes[0].reason == "no_raw_capture_id"
    assert not patch_route.called


@pytest.mark.asyncio
@respx.mock
async def test_a_missing_capture_row_is_skipped_not_finalized(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([_state_row(raw_capture_id="gone")])
    _mock_captures({})
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.outcomes[0].reason == "capture_missing_or_unreadable"
    assert not patch_route.called


@pytest.mark.asyncio
@respx.mock
async def test_one_failing_game_never_aborts_the_batch(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([_state_row(game_id="g1", row_id="a"), _state_row(game_id="g2", row_id="b")])
    _mock_captures({"capture-1": _boxscore()})

    def _respond(request: httpx.Request) -> httpx.Response:
        if request.url.params["id"] == "eq.g1":
            return httpx.Response(500, text="db error")
        return httpx.Response(200, json=[{"id": "g2"}])

    respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert result.finalized == 1  # g2 still got finalized
    assert len(result.failures) == 1 and "g1" in result.failures[0]


@pytest.mark.asyncio
@respx.mock
async def test_nothing_confirmed_complete_is_a_clean_no_op(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([])
    patch_route = _mock_finalize()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await finalize_completed_games(client, _headers())

    assert (result.considered, result.finalized, result.skipped) == (0, 0, 0)
    assert not patch_route.called


@pytest.mark.asyncio
@respx.mock
async def test_only_confirmed_complete_msf_rows_are_ever_read(monkeypatch):
    _mock_env(monkeypatch)
    _mock_states([])
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await finalize_completed_games(client, _headers())

    params = respx.calls[0].request.url.params
    assert params["state"] == "eq.confirmed_complete"
    assert params["provider_name"] == "eq.mysportsfeeds"
