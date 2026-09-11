"""Tests for app.workers.msf_postgame_worker (Permanent Box Score Worker
Build, 2026-09-11). Every scenario injects its own `fetch_boxscore` fake
via the module's dependency-injection seam -- NO test in this file makes
or mocks a real network call to MySportsFeeds; `_default_fetch_boxscore`
(the one function that could) is never invoked anywhere here."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.workers.msf_postgame_worker import (
    BoxscoreFetchResult,
    MSFPostgameCaptureResult,
    run_msf_postgame_capture,
)

SUPABASE_URL = "https://test-project.supabase.co"
GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"
MSF_GAME_ID = "163542"
RAW_EVENT_ID = "e0000000-0000-0000-0000-000000000001"

KICKOFF = datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc)


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row():
    return {"id": GAME_ID, "home_team": "LAR", "away_team": "SF", "scheduled_start": KICKOFF.isoformat(), "status": "scheduled"}


def _boxscore_body(*, played_status="COMPLETED", players=None):
    players = players if players is not None else []
    return {
        "game": {
            "id": int(MSF_GAME_ID),
            "playedStatus": played_status,
            "awayTeam": {"abbreviation": "SF"},
            "homeTeam": {"abbreviation": "LAR"},
        },
        "stats": {"away": {"players": players}, "home": {"players": []}},
        "lastUpdatedOn": "2026-09-14T00:00:00Z",
    }


def _player_entry(pid: str, name: str, position: str = "QB", pass_yards: int = 100):
    first, _, last = name.partition(" ")
    return {
        "player": {"id": int(pid), "firstName": first, "lastName": last, "position": position},
        "playerStats": [{"passing": {"passYards": pass_yards}}],
    }


def _mock_ingestion_state_get(row: dict | None):
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[row] if row else [])
    )


def _mock_season(year: int = 2026):
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "league-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200, json=[{"year": year, "start_date": "2026-09-01", "end_date": "2027-02-01"}]
        )
    )


def _mock_msf_game_mapping(present: bool = True):
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"provider_game_id": MSF_GAME_ID}] if present else [])
    )


@pytest.mark.asyncio
@respx.mock
async def test_already_finalized_game_never_calls_fetch_or_touches_anything_else(monkeypatch):
    """'Already captured/confirmed games never call again' -- any
    terminal state short-circuits before fetch_boxscore, before game
    lookup, before season resolution."""
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "confirmed_complete", "attempt_count": 2})
    fetch_calls: list = []

    async def _fake(*, season, msf_game_id):
        fetch_calls.append((season, msf_game_id))
        return BoxscoreFetchResult(status="success", http_status=200, body={})

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=KICKOFF, fetch_boxscore=_fake)

    assert result == MSFPostgameCaptureResult(
        game_id=GAME_ID, outcome="already_finalized", state="confirmed_complete", attempt_count=2
    )
    assert fetch_calls == []


@pytest.mark.asyncio
@respx.mock
async def test_not_yet_eligible_creates_scheduled_row_and_skips_without_fetching(monkeypatch):
    """No existing row, `now` well before kickoff+3h30m -- a 'scheduled'
    row is created but the claim never applies (not due yet), and
    fetch_boxscore is never called."""
    _env(monkeypatch)
    get_calls = {"n": 0}

    def _get_side_effect(request):
        get_calls["n"] += 1
        # Call 1: run_msf_postgame_capture's own top-level check (no row
        # yet). Call 2: ensure_scheduled_row's own internal existence
        # check (still no row -- it's about to create one). Call 3+: the
        # re-check after the claim fails, now reporting the just-created
        # 'scheduled' row.
        if get_calls["n"] <= 2:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"state": "scheduled", "attempt_count": 0}])

    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(side_effect=_get_side_effect)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_game_row()]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(201, json=[{"id": "row-1", "state": "scheduled", "attempt_count": 0}])
    )
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[])
    )
    fetch_calls: list = []

    async def _fake(*, season, msf_game_id):
        fetch_calls.append((season, msf_game_id))
        return BoxscoreFetchResult(status="success", http_status=200, body={})

    now = KICKOFF + timedelta(hours=1)  # well before +3h30m
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "skipped_not_eligible"
    assert result.state == "scheduled"
    assert fetch_calls == []
    assert insert_route.called
    assert patch_route.called  # promote + claim attempts both fired, neither applied


@pytest.mark.asyncio
@respx.mock
async def test_missing_msf_game_mapping_escalates_permanent_without_fetching(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping(present=False)
    fetch_calls: list = []

    async def _fake(*, season, msf_game_id):
        fetch_calls.append((season, msf_game_id))
        return BoxscoreFetchResult(status="success", http_status=200, body={})

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "capture_failed_permanent"
    assert result.attempt_count == 1
    assert fetch_calls == []


@pytest.mark.asyncio
@respx.mock
async def test_transient_fetch_failure_below_hard_cap_stays_eligible(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 1})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 1}])
    )
    _mock_msf_game_mapping()
    _mock_season()

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="transient_error", http_status=503, error="provider returned 503")

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "capture_failed_transient"
    assert result.attempt_count == 2  # 1 (pre-existing) + 1 (this tick)
    assert result.state == "eligible_for_postgame_check"

    # The final PATCH call (the ingestion-state update, not the claim)
    # must carry the next_eligible_attempt_at +1h from `now`, and
    # error_classification='transient'.
    update_body = json.loads(patch_route.calls[-1].request.content)
    assert update_body["error_classification"] == "transient"
    assert update_body["state"] == "eligible_for_postgame_check"
    assert update_body["next_eligible_attempt_at"] == (now + timedelta(hours=1)).isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_transient_fetch_failure_at_hard_cap_escalates_permanent(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 3})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 3}])
    )
    _mock_msf_game_mapping()
    _mock_season()

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="transient_error", http_status=None, error="timeout")

    now = KICKOFF + timedelta(hours=8)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "capture_failed_permanent"
    assert result.attempt_count == 4  # hard cap reached
    update_body = json.loads(patch_route.calls[-1].request.content)
    assert update_body["state"] == "capture_failed_permanent"
    assert update_body["error_classification"] == "permanent"


@pytest.mark.asyncio
@respx.mock
async def test_permanent_fetch_failure_escalates_regardless_of_attempt_count(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="permanent_error", http_status=401, error="authentication failed (401)")

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "capture_failed_permanent"
    assert result.attempt_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_successful_fetch_preserves_raw_evidence_before_validation(monkeypatch):
    """Raw preservation happens even when validation subsequently fails
    -- the game_events POST must be observed regardless of the
    validation outcome, and it must happen before the ingestion-state
    row is ever marked validation_failed."""
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    raw_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}])
    )

    wrong_game_body = _boxscore_body(played_status="COMPLETED")
    wrong_game_body["game"]["id"] = 999999999  # does not match MSF_GAME_ID

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=wrong_game_body)

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "validation_failed"
    assert raw_insert_route.called
    raw_body = json.loads(raw_insert_route.calls.last.request.content)
    assert raw_body["raw_payload"]["body"] == wrong_game_body  # untouched, byte-identical evidence


@pytest.mark.asyncio
@respx.mock
async def test_not_completed_below_hard_cap_schedules_next_check_no_persistence(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}]))
    # Deliberately no route registered for /rest/v1/players or
    # /rest/v1/player_provider_ids -- a not-COMPLETED result must never
    # reach player processing at all; respx would raise if it tried.

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=_boxscore_body(played_status="LIVE"))

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "not_ready"
    assert result.state == "eligible_for_postgame_check"
    update_body = json.loads(patch_route.calls[-1].request.content)
    assert update_body["next_eligible_attempt_at"] == (now + timedelta(hours=1)).isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_not_completed_at_hard_cap_escalates_permanent(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 3})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 3}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}]))

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=_boxscore_body(played_status="LIVE"))

    now = KICKOFF + timedelta(hours=10)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "capture_failed_permanent"
    assert result.attempt_count == 4
    update_body = json.loads(patch_route.calls[-1].request.content)
    assert update_body["state"] == "capture_failed_permanent"


@pytest.mark.asyncio
@respx.mock
async def test_completed_all_players_resolve_confirms_complete(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}]))

    # Both real players already resolved (reuse path) -- zero creates, zero quarantines.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"player_id": "player-a", "provider_player_id": "1"}, {"player_id": "player-b", "provider_player_id": "2"}]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    body = _boxscore_body(players=[_player_entry("1", "Player One"), _player_entry("2", "Player Two")])

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=body)

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "confirmed_complete"
    assert result.resolved_players == 2
    assert result.quarantined_players == 0
    assert result.persisted_rows == 2
    assert stats_insert_route.call_count == 2
    # Two 'validated' + one final 'confirmed_complete' state update expected among patch calls.
    states_written = [json.loads(c.request.content).get("state") for c in patch_route.calls if json.loads(c.request.content).get("state")]
    assert "validated" in states_written
    assert states_written[-1] == "confirmed_complete"


@pytest.mark.asyncio
@respx.mock
async def test_completed_one_quarantined_player_yields_partially_confirmed(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}]))

    # Player "1" resolves via reuse; player "2" is genuinely unseen with
    # NO team mapping for its team abbreviation -> quarantines team_unresolved.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-a", "provider_player_id": "1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(return_value=httpx.Response(200, json=[]))
    quarantine_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_identity_quarantine").mock(
        return_value=httpx.Response(201, json=[{"id": "q-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    body = _boxscore_body(players=[_player_entry("1", "Player One"), _player_entry("2", "Player Two")])

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=body)

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "partially_confirmed"
    assert result.resolved_players == 1
    assert result.quarantined_players == 1
    assert result.persisted_rows == 1
    assert stats_insert_route.call_count == 1
    assert quarantine_insert_route.called
    final_states = [json.loads(c.request.content).get("state") for c in patch_route.calls if json.loads(c.request.content).get("state")]
    assert final_states[-1] == "partially_confirmed"


@pytest.mark.asyncio
@respx.mock
async def test_persistence_failure_after_valid_capture_leaves_state_at_validated(monkeypatch):
    """A genuine persistence failure mid per-player loop (simulated: the
    player_stats insert itself fails with a 500) must NOT be reported as
    confirmed_complete/partially_confirmed -- the row is left at
    'validated', a resting/recoverable checkpoint, per HQ's rule 5."""
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "eligible_for_postgame_check", "attempt_count": 0})
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    _mock_msf_game_mapping()
    _mock_season()
    respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(201, json=[{"id": RAW_EVENT_ID}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-a", "provider_player_id": "1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(500))

    body = _boxscore_body(players=[_player_entry("1", "Player One")])

    async def _fake(*, season, msf_game_id):
        return BoxscoreFetchResult(status="success", http_status=200, body=body)

    now = KICKOFF + timedelta(hours=4)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "persistence_failed"
    assert result.state == "validated"
    written_states = [json.loads(c.request.content).get("state") for c in patch_route.calls if json.loads(c.request.content).get("state")]
    assert written_states[-1] == "validated"  # never advanced past this
    assert "confirmed_complete" not in written_states
    assert "partially_confirmed" not in written_states


@pytest.mark.asyncio
@respx.mock
async def test_resume_from_validated_state_makes_zero_new_fetch_calls(monkeypatch):
    """A row already at 'validated' (raw captured, confirmed COMPLETED,
    persistence not yet finished) resumes straight into per-player
    processing using the ALREADY-PRESERVED raw game_events row --
    fetch_boxscore must never be invoked."""
    _env(monkeypatch)
    body = _boxscore_body(players=[_player_entry("1", "Player One")])
    _mock_ingestion_state_get({"state": "validated", "attempt_count": 1, "raw_capture_id": RAW_EVENT_ID})
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(200, json=[{"id": RAW_EVENT_ID, "raw_payload": {"body": body}}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "player-a", "provider_player_id": "1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(204)
    )
    fetch_calls: list = []

    async def _fake(*, season, msf_game_id):
        fetch_calls.append((season, msf_game_id))
        return BoxscoreFetchResult(status="success", http_status=200, body=body)

    now = KICKOFF + timedelta(hours=5)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "confirmed_complete"
    assert fetch_calls == []  # zero new provider calls
    assert stats_insert_route.call_count == 1
    final_body = json.loads(patch_route.calls.last.request.content)
    assert final_body["state"] == "confirmed_complete"


@pytest.mark.asyncio
@respx.mock
async def test_resume_from_validated_with_missing_raw_evidence_is_reported_not_guessed(monkeypatch):
    _env(monkeypatch)
    _mock_ingestion_state_get({"state": "validated", "attempt_count": 1, "raw_capture_id": RAW_EVENT_ID})
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(return_value=httpx.Response(200, json=[]))

    async def _fake(*, season, msf_game_id):
        raise AssertionError("fetch_boxscore must never be called on this path")

    now = KICKOFF + timedelta(hours=5)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(supabase_client=client, game_id=GAME_ID, now=now, fetch_boxscore=_fake)

    assert result.outcome == "skipped_missing_evidence"
