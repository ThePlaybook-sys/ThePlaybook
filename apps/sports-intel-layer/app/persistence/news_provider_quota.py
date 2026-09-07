"""Phase 8.0.5 Pass 2.2 (2026-09-07) -- a real, durable, concurrency-safe
daily request-quota ledger for News Worker's injected provider (GNews
today; provider-neutral by design, keyed on `news_adapter.provider_name`,
never a hardcoded vendor name).

**Deliberately NOT a reuse of `app.persistence.odds_api_credit_ledger`.**
That module tracks a MONTHLY figure with no automatic period rollover --
retrofitting daily-rollover behavior onto a table already trusted for
Odds' own real financial-safety guard was explicitly flagged in the Pass
2.1 safety check as carrying blast radius beyond News, and was not done
without HQ's explicit sign-off. This table sidesteps rollover by
construction: `(provider_name, quota_date)` is the identity, so a new UTC
day simply has no row yet (reads as zero) rather than needing any reset
logic at all.

**Atomic increment, not read-then-write.** Unlike the odds ledger's
accepted single-writer read-then-write risk, this pass's directive
explicitly requires concurrency safety -- `increment_news_provider_quota`
(the migration's own SQL function) performs one atomic UPSERT with an
expression-based increment, called here via PostgREST's RPC endpoint, so
there is no read-modify-write race window regardless of how many
overlapping callers exist."""
from __future__ import annotations

from datetime import date

import httpx


class NewsQuotaError(Exception):
    """Raised when a quota read or increment fails on Supabase's side."""


async def read_daily_quota(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, quota_date: date
) -> int:
    """Returns `requests_used` for `provider_name` on `quota_date` (UTC
    calendar day). Returns `0` when no row exists yet -- the real, correct
    "nothing used today" state, not a bootstrap special case."""
    response = await client.get(
        "/rest/v1/news_provider_daily_quota",
        params={
            "provider_name": f"eq.{provider_name}",
            "quota_date": f"eq.{quota_date.isoformat()}",
            "select": "requests_used",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise NewsQuotaError(
            f"failed to read daily quota for {provider_name!r} on {quota_date}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0]["requests_used"] if rows else 0


async def increment_daily_quota(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str, quota_date: date
) -> int:
    """Atomically increments today's real usage by 1 (one real provider
    round-trip = one unit, matching GNews's own per-request quota unit).
    Call this ONLY after a real, non-cached provider call was actually
    attempted -- a genuine network round-trip, success or provider error
    alike (GNews counts the request either way), never a cache hit and
    never a call the quota guard itself already blocked. Returns the new
    total."""
    response = await client.post(
        "/rest/v1/rpc/increment_news_provider_quota",
        json={"p_provider_name": provider_name, "p_quota_date": quota_date.isoformat()},
        headers={**headers, "Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise NewsQuotaError(
            f"failed to increment daily quota for {provider_name!r} on {quota_date}: {response.status_code} {response.text}"
        )
    return response.json()


__all__ = ["NewsQuotaError", "read_daily_quota", "increment_daily_quota"]
