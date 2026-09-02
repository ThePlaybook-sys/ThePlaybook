"""Unit tests for app.entitlement.tier_permits -- mirrors
recommendation_products_tier_gated_select exactly.

**Hotfix regression coverage (HQ-authorized, 2026-09-02, DEV only):**
the 'syndicate' gap this module's docstring used to describe as a
deliberately-mirrored, unfixed policy defect is now corrected in both
this function and the SQL policy
(`supabase/migrations/20260902020000_fix_recommendation_products_syndicate_entitlement.sql`).
The cases below are organized to prove each property HQ's hotfix
authorization required: lower tiers are unchanged, syndicate can now
reach syndicate-gated content, no tier gained MORE access than before,
and an unrecognized tier string still safely denies."""
from __future__ import annotations

import pytest

from app.entitlement import tier_permits


@pytest.mark.parametrize(
    "min_required_tier,user_tier,expected",
    [
        # -- free: unchanged --
        ("free", None, True),
        ("free", "free", True),
        ("free", "pro", True),
        ("free", "elite", True),
        ("free", "syndicate", True),
        # -- pro: unchanged (a syndicate subscriber could already reach
        # pro-gated content before this hotfix; still can, nothing wider) --
        ("pro", None, False),
        ("pro", "free", False),
        ("pro", "pro", True),
        ("pro", "elite", True),
        ("pro", "syndicate", True),
        # -- elite: unchanged, same reasoning --
        ("elite", None, False),
        ("elite", "free", False),
        ("elite", "pro", False),
        ("elite", "elite", True),
        ("elite", "syndicate", True),
        # -- syndicate: THE FIX. A syndicate-gated product is now
        # reachable by a syndicate subscriber (was False before the
        # hotfix -- this is the corrected behavior, not a regression)
        # and still correctly denied to every lower tier and to no
        # subscription at all -- no broader access was accidentally
        # granted beyond exactly the syndicate tier itself.
        ("syndicate", "syndicate", True),
        ("syndicate", "elite", False),
        ("syndicate", "pro", False),
        ("syndicate", "free", False),
        ("syndicate", None, False),
        # -- unknown/unrecognized tier strings: safe by default, both
        # as a min_required_tier value (falls through to False, same
        # as before the hotfix) and as a user_tier value (never
        # special-cased anywhere, so it simply fails every `in (...)`
        # membership check) --
        ("unknown_future_tier", "syndicate", False),
        ("pro", "unknown_future_tier", False),
    ],
)
def test_tier_permits_mirrors_the_real_rls_policy(min_required_tier, user_tier, expected):
    assert tier_permits(min_required_tier, user_tier) is expected
