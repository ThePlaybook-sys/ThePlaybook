"""Tests for app.diagnostics.msf_week1_schedule_recovery (MANSA MSF Week
1 Identity Recovery, 2026-09-11, HQ-authorized ONE-CALL pass).

No live MySportsFeeds request is made by this file or by the module it
tests -- everything is respx-mocked. Proves:

- the diagnostic hook is not wired into app.main's startup events at all
  when RUN_MSF_WEEK1_SCHEDULE_RECOVERY is unset, and that it IS wired
  when the flag is set.
- the activation_run_markers guard blocks a duplicate/redeploy run
  outright -- a 409 from the marker claim short-circuits before any MSF
  request is attempted.
- the happy path claims the marker, requests the proven
  week/{N}/games.json shape for the current season, makes exactly one
  call, and persists a full evidence envelope (the complete raw body,
  not just a summary) via the existing, unmodified
  app.persistence.game_events.write_raw_game_events.
- the credential and the full raw body/headers never appear in the
  redacted logging summary.
- timeout/transport/missing-credential failures return a structured
  result and never raise.
"""
from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from app.diagnostics.msf_week1_schedule_recovery import (
    _RUN_KEY,
    redact_for_logging,
    run_msf_week1_schedule_recovery,
)

SUPABASE_URL = "https://test-project.supabase.co"
MARKERS_URL = f"{SUPABASE_URL}/rest/v1/activation_run_markers"
GAME_EVENTS_URL = f"{SUPABASE_URL}/rest/v1/game_events"
MSF_URL = "https://api.mysportsfeeds.com/v2.1/pull/nfl/2026-2027-regular/week/1/games.json"
ANCHOR_CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
MSF_TEST_KEY = "test-msf-key-not-real"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("MYSPORTSFEEDS_API_KEY", MSF_TEST_KEY)


# ---------------------------------------------------------------------------
# Flag-off wiring
# ---------------------------------------------------------------------------


def test_hook_is_not_registered_when_flag_is_unset(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.delenv("RUN_MSF_WEEK1_SCHEDULE_RECOVERY", raising=False)
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_msf_week1_schedule_recovery_once" not in names
    finally:
        importlib.reload(main_module)


def test_hook_is_registered_when_flag_is_set(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.setenv("RUN_MSF_WEEK1_SCHEDULE_RECOVERY", "1")
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_msf_week1_schedule_recovery_once" in names
    finally:
        monkeypatch.delenv("RUN_MSF_WEEK1_SCHEDULE_RECOVERY", raising=False)
        importlib.reload(main_module)


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_duplicate_run_key_is_skipped_with_zero_provider_calls():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(409))
    schedule_route = respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={}))

    result = await run_msf_week1_schedule_recovery()

    assert result["skipped"] is True
    assert result["provider_call_made"] is False
    assert schedule_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_marker_claim_failure_is_skipped_not_raised():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(500, text="boom"))
    schedule_route = respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={}))

    result = await run_msf_week1_schedule_recovery()

    assert result["skipped"] is True
    assert result["marker_claim_error"] is True
    assert schedule_route.call_count == 0


# ---------------------------------------------------------------------------
# Happy path -- exactly one call, full evidence envelope persisted via the
# existing, unmodified write_raw_game_events.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_success_persists_evidence_envelope_and_makes_exactly_one_call():
    schedule_payload = {
        "games": [
            {"schedule": {"id": 163600, "awayTeam": {"id": 30, "abbreviation": "SF"}, "homeTeam": {"id": 32, "abbreviation": "LAR"}}},
            {"schedule": {"id": 163541, "awayTeam": {"id": 1, "abbreviation": "NE"}, "homeTeam": {"id": 31, "abbreviation": "SEA"}}},
        ]
    }
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    schedule_route = respx.get(MSF_URL).mock(
        return_value=httpx.Response(200, json=schedule_payload, headers={"content-type": "application/json"})
    )
    events_route = respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_week1_schedule_recovery()

    assert schedule_route.call_count == 1
    assert result["skipped"] is False
    assert result["http_status"] == 200
    assert result["games_found"] == 2
    assert result["evidence_persisted"] is True
    assert events_route.call_count == 1

    sent_rows = _json.loads(events_route.calls[0].request.content)
    assert len(sent_rows) == 1
    sent_row = sent_rows[0]
    assert sent_row["game_id"] == ANCHOR_CANONICAL_GAME_ID
    assert sent_row["provider_name"] == "mysportsfeeds"

    envelope = sent_row["raw_payload"]
    assert envelope["recovery_run_key"] == _RUN_KEY
    assert envelope["anchor_canonical_game_id"] == ANCHOR_CANONICAL_GAME_ID
    assert envelope["http_status"] == 200
    assert envelope["season_param"] == "2026-2027-regular"
    assert envelope["week_param"] == "1"
    assert envelope["endpoint"].endswith("/nfl/2026-2027-regular/week/1/games.json")
    assert envelope["body"] == schedule_payload
    assert envelope["games_found"] == 2

    # The credential must never appear anywhere in the persisted evidence.
    assert MSF_TEST_KEY not in _json.dumps(envelope)


@pytest.mark.asyncio
@respx.mock
async def test_persistence_failure_is_reported_not_raised():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={"games": []}))
    respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(500, text="db down"))

    result = await run_msf_week1_schedule_recovery()

    assert result["skipped"] is False
    assert result["http_status"] == 200
    assert result["evidence_persisted"] is False
    assert "persistence_error" in result


# ---------------------------------------------------------------------------
# Redacted logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_redacted_logging_summary_never_contains_body_headers_or_credential():
    schedule_payload = {"games": [{"schedule": {"should_not_appear_in_logs": "full schedule row"}}]}
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(return_value=httpx.Response(200, json=schedule_payload))
    respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_week1_schedule_recovery()
    summary = redact_for_logging(result)

    assert "body" not in summary
    assert "response_headers" not in summary
    dumped = _json.dumps(summary)
    assert MSF_TEST_KEY not in dumped
    assert "should_not_appear_in_logs" not in dumped
    assert summary["run_key"] == _RUN_KEY
    assert summary["http_status"] == 200
    assert summary["games_found"] == 1
    assert summary["evidence_persisted"] is True


# ---------------------------------------------------------------------------
# Exception safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_timeout_returns_structured_result_and_does_not_raise():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(side_effect=httpx.ReadTimeout("boom"))

    result = await run_msf_week1_schedule_recovery()

    assert result["provider_call_made"] is True
    assert result["http_status"] is None
    assert result["error"] == "timeout"
    assert result["timeout_seconds"] == 120.0


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_returns_structured_result_and_does_not_raise():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(side_effect=httpx.ConnectError("boom"))

    result = await run_msf_week1_schedule_recovery()

    assert result["provider_call_made"] is True
    assert result["http_status"] is None
    assert result["error"] == "transport_error"


@pytest.mark.asyncio
@respx.mock
async def test_missing_credential_is_skipped_cleanly(monkeypatch):
    monkeypatch.delenv("MYSPORTSFEEDS_API_KEY", raising=False)
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_week1_schedule_recovery()

    assert result["skipped"] is True
    assert result["provider_call_made"] is False
    assert "MYSPORTSFEEDS_API_KEY" in result["reason"]
