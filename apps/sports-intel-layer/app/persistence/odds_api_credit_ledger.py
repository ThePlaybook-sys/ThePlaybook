"""Phase 7 Controlled Real Odds Activation (2026-09-07) -- a self-counted
credit accounting ledger for The Odds API's bulk `/odds` endpoint.

**Deliberately NOT dependent on parsing the vendor's own
`x-requests-remaining`/`x-requests-used` response headers** -- those
header names are already flagged elsewhere in this codebase as ASSUMED,
never independently live-verified (`app.adapters.providers.the_odds_api`'s
own `_get` helper). Every bulk `/odds` call this project's adapter makes
costs a fixed, deterministic `CREDITS_PER_CALL` credits (`markets=h2h,
spreads,totals` x `regions=us`, CONFIRMED from the vendor's own docs,
2026-08-10 credit-usage projection) -- counting our own successful calls
is more reliable than trusting an unverified header name for a safety
guard whose entire job is to fail closed correctly.

One row per provider (`odds_api_credit_ledger`, unique on `provider_name`),
incremented only after a REAL provider round-trip succeeds -- never on a
cache hit (`AdapterResponse.from_cache=True`), never on a failed or
guard-skipped call. Read-then-write increment, not an atomic RPC (unlike
`display_id_counters`' concurrent-activation problem, this ledger has
exactly one writer -- one cron service, one schedule -- so the narrow
race window between two truly overlapping runs is an accepted, disclosed
risk, not solved with new RPC infrastructure for a single low-concurrency
internal counter)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

#: markets=h2h,spreads,totals (3) x regions=us (1) -- CONFIRMED vendor
#: credit formula, matching `app.adapters.providers.the_odds_api`'s own
#: fixed request shape exactly. Keep in sync if that adapter's markets/
#: regions selection ever changes.
CREDITS_PER_CALL = 3


class CreditLedgerError(Exception):
    """Raised when a credit-ledger read or write fails on Supabase's side."""


async def read_credit_ledger(client: httpx.AsyncClient, headers: dict, *, provider_name: str) -> dict | None:
    """Reads the current ledger row for `provider_name`. Returns `None`
    when no row exists yet -- the bootstrap case, meaning zero credits
    have been counted as used in the current period."""
    response = await client.get(
        "/rest/v1/odds_api_credit_ledger",
        params={"provider_name": f"eq.{provider_name}", "select": "credits_used_this_period,period_start,updated_at"},
        headers=headers,
    )
    if response.status_code != 200:
        raise CreditLedgerError(f"failed to read credit ledger for {provider_name!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def record_call(client: httpx.AsyncClient, headers: dict, *, provider_name: str, credits: int = CREDITS_PER_CALL) -> int:
    """Increments the ledger's `credits_used_this_period` by `credits`
    (read-then-write, see module docstring), creating the row if it
    doesn't exist yet. Returns the new total. Call this ONLY after a real
    provider round-trip actually succeeded -- never for a cache hit,
    never for a guard-skipped or failed call."""
    existing = await read_credit_ledger(client, headers, provider_name=provider_name)
    new_total = (existing["credits_used_this_period"] if existing else 0) + credits
    response = await client.post(
        "/rest/v1/odds_api_credit_ledger",
        params={"on_conflict": "provider_name"},
        json={
            "provider_name": provider_name,
            "credits_used_this_period": new_total,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={**headers, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=representation"},
    )
    if response.status_code not in (200, 201):
        raise CreditLedgerError(f"failed to record credit usage for {provider_name!r}: {response.status_code} {response.text}")
    return new_total
