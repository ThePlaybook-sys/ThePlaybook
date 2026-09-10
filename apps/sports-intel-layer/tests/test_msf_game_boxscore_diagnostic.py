"""Tests for app.diagnostics.msf_game_boxscore_diagnostic (MANSA Gate B
Railway Diagnostic Build, 2026-09-10, HQ-authorized BUILD-ONLY pass).

No live MySportsFeeds request is made by this file or by the module it
tests -- everything is respx-mocked. Proves:

- the diagnostic hook is not wired into app.main's startup events at all
  when RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC is unset (mirrors
  test_demo_router.py's own reload/restore technique for a conditionally
  mounted feature), and that it IS wired when the flag is set.
- the activation_run_markers guard blocks a duplicate/redeploy run
  outright -- a 409 from the marker claim short-circuits before any MSF
  request is attempted, so a second (racing) container makes zero calls.
- the happy path claims the marker, makes exactly one call, and persists
  a full evidence envelope via the existing, unmodified
  app.persistence.game_events.write_raw_game_events.
- the credential and the full raw body/headers never appear in the
  redacted logging summary.
- timeout/transport failures return a structured result and never raise.
"""
from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from app.diagnostics.msf_game_boxscore_diagnostic import (
    _RUN_KEY,
    redact_for_logging,
    run_msf_game_boxscore_diagnostic,
)

SUPABASE_URL = "https://test-project.supabase.co"
MARKERS_URL = f"{SUPABASE_URL}/rest/v1/activation_run_markers"
GAME_EVENTS_URL = f"{SUPABASE_URL}/rest/v1/game_events"
MSF_URL = "https://api.mysportsfeeds.com/v2.1/pull/nfl/2026-2027-regular/games/163541/boxscore.json"
CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
MSF_TEST_KEY = "test-msf-key-not-real"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("MYSPORTSFEEDS_API_KEY", MSF_TEST_KEY)


# ---------------------------------------------------------------------------
# Flag-off wiring: the hook must not exist at all in app.main's startup
# events when the flag is unset -- proven at the app.main level, same
# reload/restore technique test_demo_router.py already uses for DEMO-4's
# own conditionally-mounted router.
# ---------------------------------------------------------------------------


def test_hook_is_not_registered_when_flag_is_unset(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.delenv("RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC", raising=False)
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_msf_game_boxscore_diagnostic_once" not in names
    finally:
        importlib.reload(main_module)


def test_hook_is_registered_when_flag_is_set(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.setenv("RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC", "1")
        importlib.reload(main_module)
        names = [getattr(h, "__name__", "") for h in main_module.app.router.on_startup]
        assert "_run_msf_game_boxscore_diagnostic_once" in names
    finally:
        monkeypatch.delenv("RUN_MSF_GAME_BOXSCORE_DIAGNOSTIC", raising=False)
        importlib.reload(main_module)


# ---------------------------------------------------------------------------
# Idempotency guard -- proves duplicate/redeploy execution makes ZERO
# provider calls, not just that the function returns "skipped".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_duplicate_run_key_is_skipped_with_zero_provider_calls():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(409))
    msf_route = respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={}))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["skipped"] is True
    assert result["provider_call_made"] is False
    assert msf_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_marker_claim_failure_is_skipped_not_raised():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(500, text="boom"))
    msf_route = respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={}))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["skipped"] is True
    assert result["marker_claim_error"] is True
    assert msf_route.call_count == 0


# ---------------------------------------------------------------------------
# Happy path -- exactly one call, full evidence envelope persisted via the
# existing, unmodified write_raw_game_events.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_success_persists_evidence_envelope_and_makes_exactly_one_call():
    boxscore_payload = {"game": {"id": 163541}, "stats": {"away": {}, "home": {}}}
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    msf_route = respx.get(MSF_URL).mock(
        return_value=httpx.Response(200, json=boxscore_payload, headers={"content-type": "application/json"})
    )
    events_route = respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_game_boxscore_diagnostic()

    assert msf_route.call_count == 1
    assert result["skipped"] is False
    assert result["http_status"] == 200
    assert result["evidence_persisted"] is True
    assert events_route.call_count == 1

    sent_rows = _json.loads(events_route.calls[0].request.content)
    assert len(sent_rows) == 1
    sent_row = sent_rows[0]
    assert sent_row["game_id"] == CANONICAL_GAME_ID
    assert sent_row["provider_name"] == "mysportsfeeds"

    envelope = sent_row["raw_payload"]
    assert envelope["gate_b_run_key"] == _RUN_KEY
    assert envelope["provider_game_id"] == "163541"
    assert envelope["canonical_game_id"] == CANONICAL_GAME_ID
    assert envelope["http_status"] == 200
    assert envelope["content_type"] == "application/json"
    assert "request_timestamp_utc" in envelope
    assert "response_timestamp_utc" in envelope
    assert envelope["endpoint"].endswith("/nfl/2026-2027-regular/games/163541/boxscore.json")
    assert envelope["body"] == boxscore_payload

    # The credential must never appear anywhere in the persisted evidence.
    assert MSF_TEST_KEY not in _json.dumps(envelope)


@pytest.mark.asyncio
@respx.mock
async def test_persistence_failure_is_reported_not_raised():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(500, text="db down"))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["skipped"] is False
    assert result["http_status"] == 200
    assert result["evidence_persisted"] is False
    assert "persistence_error" in result


# ---------------------------------------------------------------------------
# Redacted logging -- the one boundary that guarantees Gate B's "do not
# print the full raw payload or credential into logs" requirement.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_redacted_logging_summary_never_contains_body_headers_or_credential():
    boxscore_payload = {"should_not_appear_in_logs": "player-level data goes here"}
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(return_value=httpx.Response(200, json=boxscore_payload))
    respx.post(GAME_EVENTS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_game_boxscore_diagnostic()
    summary = redact_for_logging(result)

    assert "body" not in summary
    assert "response_body" not in summary
    assert "response_headers" not in summary
    dumped = _json.dumps(summary)
    assert MSF_TEST_KEY not in dumped
    assert "should_not_appear_in_logs" not in dumped
    # The provenance Gate B actually asked for IS present:
    assert summary["run_key"] == _RUN_KEY
    assert summary["http_status"] == 200
    assert summary["provider_game_id"] == "163541"
    assert summary["evidence_persisted"] is True


# ---------------------------------------------------------------------------
# Exception safety -- a diagnostic failure must never raise out of
# run_msf_game_boxscore_diagnostic (Phase 8.3B's own disclosed defect).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_timeout_returns_structured_result_and_does_not_raise():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(side_effect=httpx.ReadTimeout("boom"))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["provider_call_made"] is True
    assert result["http_status"] is None
    assert result["error"] == "timeout"
    assert result["timeout_seconds"] == 120.0


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_returns_structured_result_and_does_not_raise():
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))
    respx.get(MSF_URL).mock(side_effect=httpx.ConnectError("boom"))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["provider_call_made"] is True
    assert result["http_status"] is None
    assert result["error"] == "transport_error"


@pytest.mark.asyncio
@respx.mock
async def test_missing_credential_is_skipped_cleanly(monkeypatch):
    monkeypatch.delenv("MYSPORTSFEEDS_API_KEY", raising=False)
    respx.post(MARKERS_URL).mock(return_value=httpx.Response(201))

    result = await run_msf_game_boxscore_diagnostic()

    assert result["skipped"] is True
    assert result["provider_call_made"] is False
    assert "MYSPORTSFEEDS_API_KEY" in result["reason"]
