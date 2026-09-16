"""Hard per-UTC-day provider call ceiling for The Odds API (2026-09-16,
"ODDS WORKER COST + FAILURE HARDENING").

**Why the existing monthly guard is not sufficient.**
`odds_api_credit_ledger` holds a MONTHLY figure, and `_check_credit_guard`
trips only when `budget - used <= floor`. That correctly prevents overrunning
the period, but it permits a legal-but-expensive single day to consume the
whole allocation: under the current `*/15` cron, 96 ticks x 3 credits = 288
credits is reachable in one day without the monthly guard objecting once --
right up to the moment it slams shut and stops odds collection entirely,
possibly mid-slate on a Sunday when the data is worth the most.

The monthly ledger is the OUTER bound. This is the INNER one. They are
complementary, not redundant, and both are checked.

**Day-keyed, so there is no rollover logic at all.** Each UTC day is its own
row; a new day simply has no row yet and reads as zero. This is the exact
rationale `news_provider_daily_quota` records for itself, reused deliberately:
retrofitting daily rollover onto the monthly ledger would put new logic inside
a table already trusted for real financial safety.

**Counts CALLS, not credits.** One bulk call costs a fixed
`CREDITS_PER_CALL` and serves every due game at once regardless of how many
there are, so the call is the unit the policy can actually control. Credits
are derived (`calls x CREDITS_PER_CALL`) and reported.

**Atomic increment**, via the `increment_odds_api_daily_calls` RPC, matching
`increment_news_provider_quota`. Deliberately stronger than
`odds_api_credit_ledger`'s accepted single-writer read-then-write race: this
counter is a hard spending ceiling and should not inherit a known race,
however narrow the window.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx


class DailyCallBudgetError(Exception):
    """Raised when reading or incrementing the daily call budget fails on
    Supabase's side."""


def utc_budget_date(now: datetime | None = None) -> date:
    """The UTC calendar day this call belongs to. Always UTC, never local --
    the cron, the ledger and every kickoff in this project are UTC, and a
    local-time boundary would make the ceiling mean different things in
    different deployments."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).date()


async def read_calls_used(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, budget_date: date
) -> int:
    """Calls already spent on `budget_date`. A day with no row has spent
    zero -- the bootstrap case, and also every new day."""
    response = await client.get(
        "/rest/v1/odds_api_daily_call_budget",
        params={
            "provider_name": f"eq.{provider_name}",
            "budget_date": f"eq.{budget_date.isoformat()}",
            "select": "calls_used",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise DailyCallBudgetError(
            f"failed to read daily call budget for {provider_name!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0]["calls_used"] if rows else 0


async def record_call(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, budget_date: date
) -> int:
    """Atomically increments today's call count and returns the new total.

    Call this ONLY after a real provider round-trip actually succeeded --
    never for a cache hit, never for a guard-skipped or failed call, the same
    discipline `odds_api_credit_ledger.record_call` already follows.
    """
    response = await client.post(
        "/rest/v1/rpc/increment_odds_api_daily_calls",
        json={"p_provider_name": provider_name, "p_budget_date": budget_date.isoformat()},
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise DailyCallBudgetError(
            f"failed to increment daily call budget for {provider_name!r}: "
            f"{response.status_code} {response.text}"
        )
    return int(response.json())
