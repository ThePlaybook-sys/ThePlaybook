"""Persistent Postgame Checkpoint Foundation (2026-09-18, HQ-authorized).

The ten proofs HQ's directive names, one test each, plus the provider
parameterization the foundation rests on.

**No provider HTTP request appears anywhere in this file** -- requirement 10.
Every route registered below is Supabase (`/rest/v1/...`). respx is in strict
mode by default, so a call to any unregistered host raises rather than
escaping, which means requirement 10 is enforced by the harness rather than
asserted by a comment.

The "fresh process" in these tests is modelled exactly as it really happens:
a brand-new `httpx.AsyncClient` and no Python object carried across, with the
only continuity being what Supabase returns. That is the whole point of the
foundation -- the old `ReconciliationGameState` dict was the continuity, and a
cron does not have one.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.persistence.game_postgame_ingestion_state import (
    claim_game_for_capture,
    ensure_scheduled_row,
    get_ingestion_state,
    read_checkpoints_done,
    record_checkpoints_done,
)
from app.workers.reconciliation import due_checkpoints, is_reconciliation_complete

SUPABASE_URL = "https://test-project.supabase.co"
STATE_PATH = f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state"
GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"
PROVIDER = "balldontlie"
NOW = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)
FINALIZED_AT = NOW - timedelta(hours=3)


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _row(**overrides) -> dict:
    row = {
        "id": "row-1",
        "game_id": GAME_ID,
        "provider_name": PROVIDER,
        "state": "eligible_for_postgame_check",
        "attempt_count": 0,
        "checkpoints_done": [],
        "next_eligible_attempt_at": NOW.isoformat(),
    }
    row.update(overrides)
    return row


async def _fresh_process_read(**row_overrides) -> frozenset[str]:
    """Simulates a brand-new cron invocation: new client, nothing carried
    over, state recovered from Supabase alone."""
    respx.get(STATE_PATH).mock(return_value=httpx.Response(200, json=[_row(**row_overrides)]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        return await read_checkpoints_done(
            client, _headers(), game_id=GAME_ID, provider_name=PROVIDER
        )


# --------------------------------------------------------------------------
# 1. A fresh process sees the previous checkpoint state.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_1_fresh_process_sees_previous_checkpoint_state():
    done = await _fresh_process_read(checkpoints_done=["initial", "+10m"])
    assert done == frozenset({"initial", "+10m"})


@pytest.mark.asyncio
@respx.mock
async def test_1b_absent_row_reads_as_no_checkpoints_not_an_error():
    """The honest answer for a game nobody has scheduled yet. It must not
    raise, because the dispatcher calls this before `ensure_scheduled_row`."""
    respx.get(STATE_PATH).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        assert await read_checkpoints_done(
            client, _headers(), game_id=GAME_ID, provider_name=PROVIDER
        ) == frozenset()


# --------------------------------------------------------------------------
# 2. A process restart does not re-run a completed checkpoint.
#    This is the defect the foundation exists to fix, stated as a test.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_2_restart_does_not_rerun_completed_checkpoints():
    done = await _fresh_process_read(checkpoints_done=["initial", "+10m", "+30m", "+2h"])
    due = due_checkpoints(now=NOW, finalized_at=FINALIZED_AT, checks_done=done)

    # Three hours after finalization, five offsets have elapsed
    # (initial/+10m/+30m/+2h are done, +24h and +72h have not come due).
    assert due == []

    # And the old behaviour, for contrast: with the process-local dict a
    # restart loses, the same instant re-buys four checkpoints.
    assert due_checkpoints(
        now=NOW, finalized_at=FINALIZED_AT, checks_done=frozenset()
    ) == ["initial", "+10m", "+30m", "+2h"]


# --------------------------------------------------------------------------
# 3. A concurrent claim cannot double-dispatch.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_3_concurrent_claim_cannot_double_dispatch():
    """Two ticks race for one row. The conditional PATCH is the lock: the
    winner's write flips `state` out of `eligible_for_postgame_check`, so the
    loser's WHERE clause matches zero rows and it returns `None`. The loser
    must not fall through into provider work."""
    responses = [
        httpx.Response(200, json=[_row(state="capture_in_progress")]),  # winner
        httpx.Response(200, json=[]),                                    # loser
    ]
    respx.patch(STATE_PATH).mock(side_effect=responses)

    claims = []
    for _ in range(2):
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            claims.append(
                await claim_game_for_capture(
                    client, _headers(), game_id=GAME_ID, now=NOW, provider_name=PROVIDER
                )
            )

    assert claims[0] is not None
    assert claims[1] is None
    assert sum(1 for c in claims if c is not None) == 1


@pytest.mark.asyncio
@respx.mock
async def test_3b_claim_filters_on_the_requested_provider():
    """A generic table needs the claim scoped, or one provider's tick claims
    another's row."""
    route = respx.patch(STATE_PATH).mock(return_value=httpx.Response(200, json=[_row()]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await claim_game_for_capture(
            client, _headers(), game_id=GAME_ID, now=NOW, provider_name=PROVIDER
        )
    assert f"provider_name=eq.{PROVIDER}" in str(route.calls[0].request.url)


# --------------------------------------------------------------------------
# 4. A transient failure advances bounded retry/backoff, durably.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_4_transient_failure_persists_backoff_and_attempt_count():
    next_attempt = NOW + timedelta(minutes=15)
    route = respx.patch(STATE_PATH).mock(return_value=httpx.Response(204))
    from app.persistence.game_postgame_ingestion_state import update_ingestion_state

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await update_ingestion_state(
            client,
            _headers(),
            game_id=GAME_ID,
            provider_name=PROVIDER,
            state="capture_failed_transient",
            error_classification="transient",
            attempt_count=3,
            next_eligible_attempt_at=next_attempt.isoformat(),
        )

    body = json.loads(route.calls[0].request.content)
    assert body["error_classification"] == "transient"
    assert body["attempt_count"] == 3
    assert body["next_eligible_attempt_at"] == next_attempt.isoformat()
    # Backoff lives in the row, not in the process, so the next tick honours it.
    assert body["state"] == "capture_failed_transient"


# --------------------------------------------------------------------------
# 5. A permanent failure does not retry forever.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_5_permanent_failure_is_not_reclaimable():
    """`capture_failed_permanent` is not `eligible_for_postgame_check`, so the
    claim's WHERE clause can never match it again -- no attempt ceiling
    arithmetic required, the state machine itself stops it."""
    respx.patch(STATE_PATH).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        claimed = await claim_game_for_capture(
            client, _headers(), game_id=GAME_ID, now=NOW, provider_name=PROVIDER
        )
    assert claimed is None

    route = respx.patch(STATE_PATH).calls[0]
    assert "state=eq.eligible_for_postgame_check" in str(route.request.url)


# --------------------------------------------------------------------------
# 6. A finalized game produces zero provider work.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_6_finalized_game_produces_zero_provider_work():
    done = await _fresh_process_read(
        state="confirmed_complete",
        checkpoints_done=["initial", "+10m", "+30m", "+2h", "+24h", "+72h"],
    )
    assert is_reconciliation_complete(done) is True
    # Complete means complete at any later instant, not just this one.
    far_future = FINALIZED_AT + timedelta(days=30)
    assert due_checkpoints(now=far_future, finalized_at=FINALIZED_AT, checks_done=done) == []


# --------------------------------------------------------------------------
# 7. A future game produces zero provider work.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_7_future_game_produces_zero_provider_work():
    """A game that has not kicked off has no `finalized_at`, so it never
    reaches `due_checkpoints` at all; and its state row, if one exists, is
    `scheduled` with a future `next_eligible_attempt_at`, which the claim
    refuses."""
    respx.patch(STATE_PATH).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        claimed = await claim_game_for_capture(
            client, _headers(), game_id=GAME_ID, now=NOW, provider_name=PROVIDER
        )
    assert claimed is None
    # Read the decoded param rather than the raw query string -- httpx
    # percent-encodes the `+00:00` offset, and asserting on the encoded form
    # would be testing httpx's escaping rather than our filter.
    params = respx.patch(STATE_PATH).calls[0].request.url.params
    assert params["next_eligible_attempt_at"] == f"lte.{NOW.isoformat()}"


# --------------------------------------------------------------------------
# 8. State survives a simulated new cron invocation.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_8_state_survives_a_simulated_new_cron_invocation():
    """Tick one records `+30m`; tick two is a different client with no shared
    Python state and must see it."""
    stored: list[str] = ["initial", "+10m"]

    def _get(request):
        return httpx.Response(200, json=[_row(checkpoints_done=list(stored))])

    def _patch(request):
        stored[:] = json.loads(request.content)["checkpoints_done"]
        return httpx.Response(204)

    respx.get(STATE_PATH).mock(side_effect=_get)
    respx.patch(STATE_PATH).mock(side_effect=_patch)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as tick_one:
        await record_checkpoints_done(
            tick_one, _headers(), game_id=GAME_ID, labels={"+30m"}, provider_name=PROVIDER
        )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as tick_two:
        recovered = await read_checkpoints_done(
            tick_two, _headers(), game_id=GAME_ID, provider_name=PROVIDER
        )

    assert recovered == frozenset({"initial", "+10m", "+30m"})


@pytest.mark.asyncio
@respx.mock
async def test_8b_record_unions_rather_than_replaces():
    """A caller that knows only about the checkpoint it just finished must not
    erase the ones an earlier process finished."""
    respx.get(STATE_PATH).mock(
        return_value=httpx.Response(200, json=[_row(checkpoints_done=["initial", "+10m"])])
    )
    route = respx.patch(STATE_PATH).mock(return_value=httpx.Response(204))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        merged = await record_checkpoints_done(
            client, _headers(), game_id=GAME_ID, labels={"+2h"}, provider_name=PROVIDER
        )

    assert merged == frozenset({"initial", "+10m", "+2h"})
    assert json.loads(route.calls[0].request.content)["checkpoints_done"] == [
        "+10m",
        "+2h",
        "initial",
    ]


# --------------------------------------------------------------------------
# 9. Completion is idempotent.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_9_recording_an_already_done_checkpoint_writes_nothing():
    """A duplicate cron tick costs one read and no write -- so duplicate ticks
    cannot multiply provider calls OR row churn."""
    respx.get(STATE_PATH).mock(
        return_value=httpx.Response(200, json=[_row(checkpoints_done=["initial", "+10m"])])
    )
    patch_route = respx.patch(STATE_PATH).mock(return_value=httpx.Response(204))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        merged = await record_checkpoints_done(
            client, _headers(), game_id=GAME_ID, labels={"initial"}, provider_name=PROVIDER
        )

    assert merged == frozenset({"initial", "+10m"})
    assert patch_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_9b_ensure_scheduled_row_is_idempotent_and_never_clobbers():
    """Called again on a row already mid-capture, it returns that row and does
    not insert -- terminal and in-flight state is what this table protects."""
    in_flight = _row(state="capture_in_progress", attempt_count=2)
    respx.get(STATE_PATH).mock(return_value=httpx.Response(200, json=[in_flight]))
    insert_route = respx.post(STATE_PATH).mock(return_value=httpx.Response(201, json=[_row()]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await ensure_scheduled_row(
            client,
            _headers(),
            game_id=GAME_ID,
            first_eligible_at=NOW,
            provider_name=PROVIDER,
        )

    assert row == in_flight
    assert insert_route.call_count == 0


# --------------------------------------------------------------------------
# 10. No provider HTTP request is needed to prove any of the above.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_10_no_provider_host_is_ever_contacted():
    """Enforced rather than asserted: respx is strict, and only Supabase
    routes are registered. A request to any provider host raises
    `AllMockedAssertionError` and fails the test."""
    respx.get(STATE_PATH).mock(return_value=httpx.Response(200, json=[_row()]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await get_ingestion_state(
            client, _headers(), game_id=GAME_ID, provider_name=PROVIDER
        )

    hosts = {call.request.url.host for call in respx.calls}
    assert hosts == {"test-project.supabase.co"}


# --------------------------------------------------------------------------
# Provider parameterization: the MSF default must be preserved exactly, or
# three existing callers change behaviour silently.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_default_provider_is_still_mysportsfeeds():
    route = respx.get(STATE_PATH).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await get_ingestion_state(client, _headers(), game_id=GAME_ID)
    assert "provider_name=eq.mysportsfeeds" in str(route.calls[0].request.url)
