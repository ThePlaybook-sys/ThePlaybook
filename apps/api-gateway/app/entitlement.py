"""Tier-gating logic shared by every Phase 6 Milestone 2 read route.

**Centralized Product Entitlement Foundation (2026-09-09, HQ-authorized).**
Previously, this module reimplemented the exact same nested-membership
ordering (`free < pro < elite < syndicate`) that `recommendation_products`'
own RLS policy also encoded inline -- two independent copies of the same
rule, the precise shape of drift the 2026-09-02 syndicate hotfix had to
correct once already. Both copies are now replaced by ONE authoritative
resolution path, the Postgres function `resolve_permitted_tiers(uuid)`
(`supabase/migrations/20260909200400_entitlement_grants_foundation.sql`)
-- this module (and the RLS policy itself) now only ever ASK that
function what a user is permitted to see; neither re-derives the
ordering. `read_permitted_tiers` calls it once per request (matching this
module's original one-fetch-then-loop-many-products shape, avoiding an
RPC-per-product regression); `tier_permits` is now a trivial membership
test against that resolved set, not an ordering computation.

`resolve_permitted_tiers` itself also answers "does this user have an
exceptional product-access grant" (`entitlement_grants` -- owner,
complimentary, promo; never billing-tied) as an equal alternate path to
the existing `subscriptions`-tier check, so a granted user reaches
exactly the same set of rows a real top-tier subscriber would, with zero
further changes needed anywhere in this module.

Never infers a locked/paywalled state for content a caller's tier
doesn't reach (HQ Final Decision 9) -- an ungated caller simply doesn't
see the row at all, exactly as RLS would behave for a table that did
have a select policy of its own.
"""
from __future__ import annotations

import httpx

from app.supabase_client import postgrest_headers


def tier_permits(min_required_tier: str, permitted_tiers: list[str]) -> bool:
    """True iff `permitted_tiers` (the caller's own resolved set of
    reachable `min_required_tier` values, from `read_permitted_tiers`)
    contains `min_required_tier`. Contains no ordering/hierarchy logic
    of its own -- `resolve_permitted_tiers` already resolved that; this
    is a plain membership test, by design, so there is exactly one place
    in the whole system (that SQL function) where the tier ladder is
    expressed."""
    return min_required_tier in permitted_tiers


async def read_permitted_tiers(client: httpx.AsyncClient, *, user_id: str) -> list[str]:
    """Calls the one authoritative `resolve_permitted_tiers` RPC
    (`supabase/migrations/20260909200400_entitlement_grants_foundation.sql`)
    -- the same function `recommendation_products_tier_gated_select`
    itself now calls, via `has_entitlement`. Always includes `'free'`;
    never defaults a missing subscription/grant to anything higher."""
    response = await client.post(
        "/rest/v1/rpc/resolve_permitted_tiers",
        json={"p_user_id": user_id},
        headers={**postgrest_headers(), "Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()
