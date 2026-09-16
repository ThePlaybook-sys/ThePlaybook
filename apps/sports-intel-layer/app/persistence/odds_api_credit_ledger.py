"""Phase 7 Controlled Real Odds Activation (2026-09-07) -- a self-counted
credit accounting ledger for The Odds API's bulk `/odds` endpoint.

**Deliberately NOT dependent on parsing the vendor's own
`x-requests-remaining`/`x-requests-used` response headers** for the count
itself -- every bulk `/odds` call this project's adapter makes costs a fixed,
deterministic `CREDITS_PER_CALL` credits (`markets=h2h,spreads,totals` x
`regions=us`, CONFIRMED from the vendor's own docs, 2026-08-10 credit-usage
projection), and counting our own successful calls is more reliable than
trusting a header for a safety guard whose entire job is to fail closed
correctly. (Those headers ARE now used, as a reconciliation signal -- see
below -- but they never replace our own count.)

=============================================================================
UTC calendar-month periods (2026-09-16, "ODDS CREDIT LEDGER MONTHLY ROLLOVER")
=============================================================================

**The defect this closes.** `record_call` never wrote `period_start`, and no
code ever read it, so the guard compared a *monotonically increasing lifetime*
counter against a *monthly* budget. Once usage crossed the trip point it would
stay tripped permanently, silently stopping odds collection while the real
vendor allowance was full.

**The authoritative rule**, from The Odds API's official FAQ: *"Usage credits
are automatically reset on the first of every month."* So the period is a
calendar month; MANSA's internal convention is the **UTC** calendar month,
keyed `YYYY-MM`.

**Rollover is a LOOKUP, not a MUTATION.** `period_key` is part of the row's
identity (`unique (provider_name, period_key)`), so a new month simply has no
row and reads as zero. There is no reset to run, no boundary arithmetic that
can half-apply, and a stale prior-period row can never block a new month
because the new month never reads it. Prior months are immutable because
nothing writes to them again. This is the same shape
`odds_api_daily_call_budget` and `news_provider_daily_quota` already use.

**No provider call is needed to roll over** -- the key comes from the clock.

=============================================================================
Provider header reconciliation
=============================================================================

The vendor returns `x-requests-used`, `x-requests-remaining` and
`x-requests-last`, and is definitionally authoritative about its own quota.
They are recorded ALONGSIDE our count, never on top of it:

* `credits_used_this_period` -- ours, never overwritten, so our own spend
  record survives reconciliation and a disagreement stays visible.
* `provider_reported_used` -- the vendor's. `effective_used_credits()` prefers
  it when present, which is what makes the guard correct at the exact reset
  boundary in BOTH directions: at 00:05 on the 1st our new row reads 0 while
  the vendor may not have reset yet and still reports 490 (trusting only
  ourselves would overspend), and equally if the vendor resets slightly early
  our own carried count would block spending that is actually allowed.

Writes go through atomic RPCs rather than the previous read-then-write upsert.
That race was an accepted, disclosed risk on the old single-row design; with
per-month rows, two workers crossing the boundary together is exactly when it
would bite, and a hard spending guard should not inherit a known race.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

#: markets=h2h,spreads,totals (3) x regions=us (1) -- CONFIRMED vendor
#: credit formula, matching `app.adapters.providers.the_odds_api`'s own
#: fixed request shape exactly. Keep in sync if that adapter's markets/
#: regions selection ever changes.
CREDITS_PER_CALL = 3

_TABLE = "/rest/v1/odds_api_credit_ledger"


class CreditLedgerError(Exception):
    """Raised when a credit-ledger read or write fails on Supabase's side."""


def utc_period_key(now: datetime | None = None) -> str:
    """The `YYYY-MM` key for the UTC calendar month containing `now`.

    **Always UTC, never local.** The vendor resets on the first of the month;
    a local-time boundary would make the same instant fall in different
    periods in different deployments, which is exactly the class of bug a
    spending guard cannot afford. Every other time-keyed table in this project
    (the daily call budget, the news quota) makes the same choice for the same
    reason.
    """
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m")


def effective_used_credits(ledger: dict | None) -> int:
    """Credits considered used for guard purposes.

    The provider's own figure wins when present -- it is authoritative about
    its own quota, and it is the only signal that is correct on both sides of
    the reset boundary. Our deterministic count is the fallback, and remains
    the record of what *we* spent regardless.
    """
    if not ledger:
        return 0
    provider_used = ledger.get("provider_reported_used")
    if provider_used is not None:
        return int(provider_used)
    return int(ledger.get("credits_used_this_period") or 0)


async def read_credit_ledger(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, period_key: str | None = None
) -> dict | None:
    """Reads the ledger row for `provider_name` in `period_key` (defaulting to
    the current UTC month).

    Returns `None` when no row exists yet -- which is both the bootstrap case
    and, by design, **every new month**. A caller must treat `None` as "zero
    credits used in this period", never as an error: that is what makes
    rollover free.
    """
    key = period_key or utc_period_key()
    response = await client.get(
        _TABLE,
        params={
            "provider_name": f"eq.{provider_name}",
            "period_key": f"eq.{key}",
            "select": (
                "credits_used_this_period,period_key,period_start,updated_at,"
                "provider_reported_used,provider_reported_remaining,"
                "provider_reported_last,provider_reported_at,last_discrepancy"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise CreditLedgerError(
            f"failed to read credit ledger for {provider_name!r} period {key}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def record_call(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    credits: int = CREDITS_PER_CALL,
    period_key: str | None = None,
) -> int:
    """Atomically adds `credits` to this period's count, creating the period's
    row if this is its first call. Returns the new total for the period.

    Call this ONLY after a real provider round-trip actually succeeded --
    never for a cache hit, never for a guard-skipped or failed call.
    """
    key = period_key or utc_period_key()
    response = await client.post(
        "/rest/v1/rpc/increment_odds_api_credits",
        json={"p_provider_name": provider_name, "p_period_key": key, "p_credits": credits},
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise CreditLedgerError(
            f"failed to record credit usage for {provider_name!r} period {key}: "
            f"{response.status_code} {response.text}"
        )
    return int(response.json())


async def reconcile_provider_usage(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str,
    requests_used: int | None,
    requests_remaining: int | None = None,
    requests_last: int | None = None,
    local_used: int | None = None,
    period_key: str | None = None,
) -> str | None:
    """Records what the vendor says about this period, and returns a
    human-readable discrepancy string when its number differs from ours (or
    `None` when they agree or there is nothing to compare).

    Never touches `credits_used_this_period`: our own count is preserved so
    the disagreement stays visible and auditable rather than being silently
    resolved away. A no-op when the vendor reported nothing -- an absent or
    unparseable header must degrade to "no reconciliation signal", never to a
    fabricated zero, which would read as a full allowance.
    """
    if requests_used is None:
        return None

    key = period_key or utc_period_key()
    discrepancy: str | None = None
    if local_used is not None and int(requests_used) != int(local_used):
        discrepancy = (
            f"provider_reported_used={requests_used} != local_counted={local_used} "
            f"(delta {int(requests_used) - int(local_used):+d}) for period {key}"
        )

    response = await client.post(
        "/rest/v1/rpc/reconcile_odds_api_provider_usage",
        json={
            "p_provider_name": provider_name,
            "p_period_key": key,
            "p_used": int(requests_used),
            "p_remaining": None if requests_remaining is None else int(requests_remaining),
            "p_last": None if requests_last is None else int(requests_last),
            "p_discrepancy": discrepancy,
        },
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise CreditLedgerError(
            f"failed to reconcile provider usage for {provider_name!r} period {key}: "
            f"{response.status_code} {response.text}"
        )
    return discrepancy
