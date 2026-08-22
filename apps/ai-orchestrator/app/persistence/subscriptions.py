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
