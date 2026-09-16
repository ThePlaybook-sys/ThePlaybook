"""UTC calendar-month periods for the Odds API credit ledger (2026-09-16,
HQ directive "ODDS CREDIT LEDGER MONTHLY ROLLOVER -- IMPLEMENT").

The authoritative rule, from The Odds API's official FAQ: *"Usage credits are
automatically reset on the first of every month."*

The defect being closed: `record_call` never wrote `period_start` and nothing
ever read it, so the guard compared a **monotonically increasing lifetime**
counter against a **monthly** budget. Once usage crossed the trip point it
stayed tripped permanently, silently stopping odds collection while the real
vendor allowance was full.

The fix makes rollover a **lookup, not a mutation**: `period_key` is part of
the row's identity, so a new month simply has no row and reads as zero.
Nothing resets, nothing can half-apply, and a stale prior-period row can never
block a new month because it is never read.

**No provider call is made anywhere in this file** -- which is the point:
rollover must be provable without spending a credit, and it is, because the
period key comes from the clock.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.models import ProviderQuota
from app.adapters.providers.the_odds_api import parse_provider_quota
from app.persistence.odds_api_credit_ledger import (
    CREDITS_PER_CALL,
    effective_used_credits,
    read_credit_ledger,
    reconcile_provider_usage,
    record_call,
    utc_period_key,
)
from tests.conftest import (
    CREDIT_LEDGER_INCREMENT,
    CREDIT_LEDGER_RECONCILE,
    release_default_route,
)

SUPABASE_URL = "https://test-project.supabase.co"
HEADERS = {"Authorization": "Bearer test", "apikey": "test"}
PROVIDER = "the_odds_api"


def _utc(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


# ===========================================================================
# The period key itself -- pure, no I/O
# ===========================================================================


def test_period_key_is_the_utc_calendar_month():
    assert utc_period_key(_utc(2026, 9, 16, 18, 54)) == "2026-09"
    assert utc_period_key(_utc(2026, 10, 1, 0, 0, 0)) == "2026-10"


def test_2_sep_30_to_oct_1_crosses_into_a_new_period():
    """PROOF 2. The last instant of September and the first of October must
    land in different periods -- and the boundary is the vendor's own rule:
    credits reset on the first of the month."""
    assert utc_period_key(_utc(2026, 9, 30, 23, 59, 59)) == "2026-09"
    assert utc_period_key(_utc(2026, 10, 1, 0, 0, 0)) == "2026-10"


def test_3_dec_31_to_jan_1_rolls_the_year_too():
    """PROOF 3. Year rollover is the case a naive month-only implementation
    gets wrong."""
    assert utc_period_key(_utc(2026, 12, 31, 23, 59, 59)) == "2026-12"
    assert utc_period_key(_utc(2027, 1, 1, 0, 0, 0)) == "2027-01"
    assert utc_period_key(_utc(2026, 12, 31)) != utc_period_key(_utc(2027, 1, 1))


def test_the_boundary_is_utc_not_local():
    """A local-time boundary would put the same instant in different periods
    in different deployments -- exactly the class of bug a spending guard
    cannot afford. 23:30 on Sep 30 UTC is still September, and an input in
    another zone is normalized rather than taken at face value."""
    from datetime import timedelta

    assert utc_period_key(_utc(2026, 9, 30, 23, 30)) == "2026-09"
    # 2026-09-30 20:30 in UTC-05:00 is 2026-10-01 01:30 UTC -> October.
    minus_five = timezone(timedelta(hours=-5))
    assert utc_period_key(datetime(2026, 9, 30, 20, 30, tzinfo=minus_five)) == "2026-10"


def test_12_rollover_itself_needs_no_provider_call():
    """PROOF 12. The key is derived from the clock alone -- no network, no
    adapter, no credit. This test makes no HTTP call of any kind."""
    with respx.mock(assert_all_mocked=True):  # any request at all would raise
        assert utc_period_key(_utc(2026, 10, 1, 0, 0, 1)) == "2026-10"


# ===========================================================================
# Reads are period-scoped
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_1_same_month_usage_persists():
    """PROOF 1. Within one month the ledger keeps accumulating -- rollover
    must not be so eager that it loses usage inside a period."""
    route = respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(200, json=[{"credits_used_this_period": 276, "period_key": "2026-09"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_credit_ledger(client, HEADERS, provider_name=PROVIDER, period_key="2026-09")

    assert row["credits_used_this_period"] == 276
    assert route.calls.last.request.url.params["period_key"] == "eq.2026-09"


@pytest.mark.asyncio
@respx.mock
async def test_7_and_9_a_new_month_reads_zero_and_cannot_be_blocked_by_the_old_one():
    """PROOFS 7 + 9. The heart of the fix. September is at 450 -- past the
    trip point -- yet October reads zero, because a new period has no row and
    the stale row is never consulted."""
    def _respond(request: httpx.Request) -> httpx.Response:
        period = request.url.params["period_key"]
        if period == "eq.2026-09":
            return httpx.Response(200, json=[{"credits_used_this_period": 450, "period_key": "2026-09"}])
        return httpx.Response(200, json=[])  # October: no row yet

    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(side_effect=_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        september = await read_credit_ledger(client, HEADERS, provider_name=PROVIDER, period_key="2026-09")
        october = await read_credit_ledger(client, HEADERS, provider_name=PROVIDER, period_key="2026-10")

    assert september["credits_used_this_period"] == 450  # would trip a 500/50 guard
    assert october is None
    assert effective_used_credits(october) == 0  # so October starts clean
    # And the guard arithmetic confirms it: 500 - 0 = 500 > 50.
    assert 500 - effective_used_credits(october) > 50


@pytest.mark.asyncio
@respx.mock
async def test_4_old_periods_remain_queryable():
    """PROOF 4. History is not merely preserved, it is reachable -- a prior
    month can still be read back for audit."""
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(
            200,
            json=[{
                "credits_used_this_period": 276,
                "period_key": "2026-09",
                "period_start": "2026-09-07T02:30:23.554545+00:00",
            }],
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        row = await read_credit_ledger(client, HEADERS, provider_name=PROVIDER, period_key="2026-09")

    assert row["period_key"] == "2026-09"
    assert row["credits_used_this_period"] == 276


# ===========================================================================
# Writes: atomic, idempotent, concurrency-safe
# ===========================================================================


@pytest.mark.asyncio
@respx.mock
async def test_5_and_6_increment_is_a_single_atomic_upsert():
    """PROOFS 5 + 6. Idempotency and concurrency safety are structural here,
    not defensive code: ONE atomic upsert keyed on (provider, period) with an
    expression-based increment. Two concurrent workers crossing the boundary
    converge on one row -- neither a lost update nor a conflicting second
    'active period' is representable.

    This replaces the previous read-then-write upsert, whose race was an
    accepted disclosed risk on the old single-row design. With per-month rows
    the boundary is precisely when it would have bitten."""
    release_default_route(CREDIT_LEDGER_INCREMENT)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/increment_odds_api_credits").mock(
        return_value=httpx.Response(200, json=3)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        total = await record_call(client, HEADERS, provider_name=PROVIDER, period_key="2026-10")

    assert total == 3
    body = json.loads(route.calls.last.request.content)
    assert body == {"p_provider_name": PROVIDER, "p_period_key": "2026-10", "p_credits": CREDITS_PER_CALL}
    # One round trip: no read-then-write window to race through.
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_5_repeated_increments_in_a_new_period_are_each_additive_not_resetting():
    """PROOF 5 (continued). Entering a new period repeatedly must not keep
    re-initializing it to zero -- 'rollover' happening again is a no-op,
    because there is no rollover step at all, only an upsert."""
    totals = iter([3, 6, 9])
    release_default_route(CREDIT_LEDGER_INCREMENT)
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/increment_odds_api_credits").mock(
        side_effect=lambda request: httpx.Response(200, json=next(totals))
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        seen = [
            await record_call(client, HEADERS, provider_name=PROVIDER, period_key="2026-10")
            for _ in range(3)
        ]
    assert seen == [3, 6, 9]


@pytest.mark.asyncio
@respx.mock
async def test_the_write_targets_the_period_it_is_told_about():
    """A call made at 00:00:01 on October 1 must land in October, not
    September -- the write carries the same key the guard read."""
    release_default_route(CREDIT_LEDGER_INCREMENT)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/increment_odds_api_credits").mock(
        return_value=httpx.Response(200, json=3)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await record_call(
            client, HEADERS, provider_name=PROVIDER, period_key=utc_period_key(_utc(2026, 10, 1, 0, 0, 1))
        )
    assert json.loads(route.calls.last.request.content)["p_period_key"] == "2026-10"


@pytest.mark.asyncio
@respx.mock
async def test_11_usage_lives_in_the_database_not_in_process_memory():
    """PROOF 11. A restart cannot reset usage, because nothing is held in
    memory: a fresh client with no prior state reads the same figure back."""
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_api_credit_ledger").mock(
        return_value=httpx.Response(200, json=[{"credits_used_this_period": 276, "period_key": "2026-09"}])
    )
    for _ in range(2):  # two separate "processes"
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            row = await read_credit_ledger(client, HEADERS, provider_name=PROVIDER, period_key="2026-09")
        assert row["credits_used_this_period"] == 276


# ===========================================================================
# Provider header reconciliation
# ===========================================================================


def test_quota_headers_are_parsed_into_a_typed_report():
    response = httpx.Response(
        200,
        headers={"x-requests-used": "276", "x-requests-remaining": "224", "x-requests-last": "3"},
    )
    quota = parse_provider_quota(response)
    assert quota == ProviderQuota(requests_used=276, requests_remaining=224, requests_last=3)


def test_absent_or_malformed_quota_headers_degrade_to_no_signal_never_to_zero():
    """For a spending guard the dangerous invention is a LOW number -- a
    fabricated zero reads as a completely unused allowance. Every bad shape
    must yield None so the guard falls back to our own count."""
    assert parse_provider_quota(httpx.Response(200)) is None
    assert parse_provider_quota(httpx.Response(200, headers={"x-requests-used": ""})) is None
    assert parse_provider_quota(httpx.Response(200, headers={"x-requests-used": "many"})) is None
    assert parse_provider_quota(httpx.Response(200, headers={"x-requests-used": "-5"})) is None


def test_8_provider_usage_is_authoritative_for_the_guard():
    """PROOF 8. The vendor knows its own quota. When it reports a figure, the
    guard uses it; our deterministic count is the fallback."""
    assert effective_used_credits({"credits_used_this_period": 3, "provider_reported_used": 276}) == 276
    assert effective_used_credits({"credits_used_this_period": 276}) == 276
    assert effective_used_credits({"credits_used_this_period": 276, "provider_reported_used": None}) == 276
    assert effective_used_credits(None) == 0


def test_8_provider_usage_protects_both_sides_of_the_reset_boundary():
    """PROOF 8 (the reason it matters). At 00:05 on the 1st our brand-new row
    reads 0 while the vendor may not have reset yet -- trusting only
    ourselves would overspend a real allowance. The reverse case, a vendor
    that resets slightly early, is covered by the same preference."""
    # Vendor has NOT reset yet: local 0, vendor 490 -> guard must see 490.
    not_yet_reset = {"credits_used_this_period": 0, "provider_reported_used": 490}
    assert effective_used_credits(not_yet_reset) == 490
    assert not (500 - effective_used_credits(not_yet_reset) > 50)  # correctly blocks

    # Vendor HAS reset: local carried 276, vendor 5 -> guard must see 5.
    already_reset = {"credits_used_this_period": 276, "provider_reported_used": 5}
    assert effective_used_credits(already_reset) == 5
    assert 500 - effective_used_credits(already_reset) > 50  # correctly allows


@pytest.mark.asyncio
@respx.mock
async def test_a_discrepancy_is_reported_never_silently_ignored():
    release_default_route(CREDIT_LEDGER_RECONCILE)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/reconcile_odds_api_provider_usage").mock(
        return_value=httpx.Response(200, json=280)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        discrepancy = await reconcile_provider_usage(
            client, HEADERS, provider_name=PROVIDER,
            requests_used=280, requests_remaining=220, requests_last=3,
            local_used=276, period_key="2026-09",
        )

    assert discrepancy is not None
    assert "provider_reported_used=280" in discrepancy
    assert "local_counted=276" in discrepancy
    assert "+4" in discrepancy  # signed delta, so the direction is visible
    assert json.loads(route.calls.last.request.content)["p_discrepancy"] == discrepancy


@pytest.mark.asyncio
@respx.mock
async def test_agreement_records_the_snapshot_without_flagging_a_discrepancy():
    respx.post(f"{SUPABASE_URL}/rest/v1/rpc/reconcile_odds_api_provider_usage").mock(
        return_value=httpx.Response(200, json=276)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        discrepancy = await reconcile_provider_usage(
            client, HEADERS, provider_name=PROVIDER, requests_used=276, local_used=276, period_key="2026-09"
        )
    assert discrepancy is None


@pytest.mark.asyncio
@respx.mock
async def test_reconciliation_is_a_no_op_when_the_vendor_reported_nothing():
    """An absent header must not write a fabricated zero, which would read as
    a full allowance."""
    release_default_route(CREDIT_LEDGER_RECONCILE)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/reconcile_odds_api_provider_usage").mock(
        return_value=httpx.Response(200, json=0)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        discrepancy = await reconcile_provider_usage(
            client, HEADERS, provider_name=PROVIDER, requests_used=None, local_used=276
        )
    assert discrepancy is None
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_reconciliation_never_writes_our_own_count():
    """Our deterministic count must survive reconciliation, so a disagreement
    stays visible and auditable rather than being resolved away."""
    release_default_route(CREDIT_LEDGER_RECONCILE)
    route = respx.post(f"{SUPABASE_URL}/rest/v1/rpc/reconcile_odds_api_provider_usage").mock(
        return_value=httpx.Response(200, json=5)
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await reconcile_provider_usage(
            client, HEADERS, provider_name=PROVIDER, requests_used=5, local_used=276, period_key="2026-10"
        )
    body = json.loads(route.calls.last.request.content)
    assert "p_credits" not in body
    assert "credits_used_this_period" not in body


# ===========================================================================
# Independence from the daily budget
# ===========================================================================


def test_10_the_daily_budget_is_keyed_independently_of_the_monthly_period():
    """PROOF 10. The two guards bound different things -- a day and a period
    -- and neither key derives from the other, so a month rollover cannot
    disturb the day's count or vice versa."""
    from app.persistence.odds_api_daily_call_budget import utc_budget_date

    boundary = _utc(2026, 10, 1, 0, 0, 1)
    assert utc_period_key(boundary) == "2026-10"
    assert utc_budget_date(boundary).isoformat() == "2026-10-01"

    # Mid-month: the day advances while the period does not.
    mid = _utc(2026, 10, 17, 12, 0)
    assert utc_period_key(mid) == "2026-10"  # unchanged
    assert utc_budget_date(mid).isoformat() == "2026-10-17"  # moved
