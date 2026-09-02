"""Tier-gating logic shared by every Phase 6 Milestone 2 read route.

Mirrors `recommendation_products`' own RLS policy
(`recommendation_products_tier_gated_select`,
`supabase/migrations/20260825120000_recommendation_products_schema.sql`)
in Python -- required because these routes read via the service-role
key: every downstream Phase 5 table these routes also touch (legs,
explanations, agent outputs, consensus snapshots, activation snapshots,
grade events) has RLS enabled with NO select policy at all, so a
caller's own JWT could never read them via PostgREST regardless (Volume
5 v5.0 Milestone 2 pre-implementation inspection). This module is the
one place the tier decision is made, so every new route enforces
exactly the same rule the database's own policy encodes -- never more
permissive, never a separate reinvented rule.

Never infers a locked/paywalled state for content a caller's tier
doesn't reach (HQ Final Decision 9) -- an ungated caller simply doesn't
see the row at all, exactly as RLS would behave for a table that did
have a select policy of its own.
"""
from __future__ import annotations

import httpx

from app.supabase_client import postgrest_headers


def tier_permits(min_required_tier: str, user_tier: str | None) -> bool:
    """True iff `user_tier` (the caller's own active subscription tier,
    or None if they have none) satisfies `min_required_tier`.

    Mirrors `recommendation_products_tier_gated_select` LITERALLY.

    **Hotfix (HQ-authorized, 2026-09-02, DEV only):** a real gap existed
    here and in the database policy through Milestone 2 -- neither
    special-cased `min_required_tier = 'syndicate'` (schema-permitted,
    since `recommendation_products.min_required_tier` has no CHECK
    constraint), so a syndicate-gated row was denied to EVERY caller,
    including a syndicate-tier subscriber -- MANSA's own top paid tier.
    Both this function and the SQL policy (`supabase/migrations/
    20260902020000_fix_recommendation_products_syndicate_entitlement.sql`)
    are corrected together, extending the exact nested-membership
    pattern already used for `'pro'`/`'elite'` one rung further for
    `'syndicate'` -- same ordering semantics (free < pro < elite <
    syndicate), no new architecture. Any tier string outside the known
    four (`free`/`pro`/`elite`/`syndicate`) still safely falls through
    to `False` here, same as before.
    """
    if min_required_tier == "free":
        return True
    if user_tier is None:
        return False
    if min_required_tier == "pro":
        return user_tier in ("pro", "elite", "syndicate")
    if min_required_tier == "elite":
        return user_tier in ("elite", "syndicate")
    if min_required_tier == "syndicate":
        return user_tier in ("syndicate",)
    return False


async def read_active_subscription_tier(client: httpx.AsyncClient, *, user_id: str) -> str | None:
    """The caller's own active subscription tier, or None if they have
    no active subscription row -- mirrors
    `app.persistence.subscriptions.read_subscription_tier`
    (ai-orchestrator) exactly: an unknown/missing subscription is never
    defaulted to any tier, including 'free'."""
    response = await client.get(
        "/rest/v1/subscriptions",
        params={"user_id": f"eq.{user_id}", "status": "eq.active", "select": "tier"},
        headers=postgrest_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0]["tier"] if rows else None
