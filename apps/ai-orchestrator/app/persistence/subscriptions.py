"""Read-only `subscriptions` access (Milestone 4.7, Elite second-pass
trigger). Mirrors `app.persistence.user_profiles`'s exact convention.

**CONFIRMED live against dev (2026-08-22):** `subscriptions.tier` CHECK
constraint is exactly `'free' | 'pro' | 'elite' | 'syndicate'` -- matches
Volume 3's documented text with no drift. An unknown/missing tier (no
subscription row, or a `user_id` never supplied at all) must never be
treated as Elite -- this module returns `None` in both cases, never a
default tier."""
from __future__ import annotations

import httpx


class SubscriptionsReadError(Exception):
    """Raised when a `subscriptions` read fails on Supabase's side."""


async def read_active_subscribers(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    """Returns one `{"user_id": ..., "tier": ...}` row per user with a
    currently active subscription -- the enumeration source for the
    Milestone 4.9 Recommendation Worker's per-user fan-out (Bankroll
    Coach, Elite entitlement). Resolves Volume 4 Section 3.1's "the
    worker iterates active users" into a concrete query: every distinct
    `user_id` with a `status='active'` row (Mac's approved answer,
    2026-08-24) -- not `user_profiles` (onboarding data, not billing
    status) and not a separate `users` table (none exists; `user_profiles`
    /`subscriptions`/`betting_dna` all extend `auth.users` directly, per
    Volume 3 Section 3).

    Deduplicated to the single most recent active row per `user_id` -- a
    user should have at most one active subscription at a time, but this
    defends against a data anomaly rather than assuming the invariant,
    same discipline as `read_subscription_tier`'s own `limit=1`. Returns
    `[]` when nobody has an active subscription -- never fabricated."""
    response = await client.get(
        "/rest/v1/subscriptions",
        params={"status": "eq.active", "select": "user_id,tier,created_at", "order": "created_at.desc"},
        headers=headers,
    )
    if response.status_code != 200:
        raise SubscriptionsReadError(f"failed to list active subscribers: {response.status_code} {response.text}")
    rows = response.json()
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:  # already ordered created_at.desc -- first occurrence per user_id is the most recent
        if row["user_id"] in seen:
            continue
        seen.add(row["user_id"])
        deduped.append({"user_id": row["user_id"], "tier": row["tier"]})
    return deduped


async def read_subscription_tier(client: httpx.AsyncClient, headers: dict, *, user_id: str) -> str | None:
    """Returns the user's current `active` subscription tier, or `None`
    if no such row exists -- never a fabricated default tier. Filters to
    `status=eq.active` -- a `canceled`/`past_due`/`trialing` subscription
    is not a basis for Elite-tier treatment."""
    response = await client.get(
        "/rest/v1/subscriptions",
        params={"user_id": f"eq.{user_id}", "status": "eq.active", "select": "tier", "order": "created_at.desc", "limit": "1"},
        headers=headers,
    )
    if response.status_code != 200:
        raise SubscriptionsReadError(f"failed to read subscriptions for user_id={user_id!r}: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0]["tier"] if rows else None
