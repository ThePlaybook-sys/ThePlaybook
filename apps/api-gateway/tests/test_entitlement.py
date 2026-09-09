"""Unit tests for app.entitlement.tier_permits.

**Centralized Product Entitlement Foundation (2026-09-09):** `tier_permits`
is now a plain membership test against an already-resolved
`permitted_tiers` list (from `resolve_permitted_tiers`, the one
authoritative Postgres function) -- it contains no ordering/hierarchy
logic of its own any more. These cases are the exact same scenarios the
old two-copy (`tier_permits` + inline RLS subquery) design covered,
rewritten against the new signature to prove behavior is unchanged --
Requirement 1 of the foundation's own test list ("current free/pro/
elite/syndicate behavior is unchanged")."""
from __future__ import annotations

import pytest

from app.entitlement import tier_permits

_FREE = ["free"]
_PRO = ["free", "pro"]
_ELITE = ["free", "pro", "elite"]
_SYNDICATE = ["free", "pro", "elite", "syndicate"]
_NONE: list[str] = []


@pytest.mark.parametrize(
    "min_required_tier,permitted_tiers,expected",
    [
        # -- free: every real resolved set (even the empty/no-access one,
        # which never actually occurs since resolve_permitted_tiers
        # always includes 'free' -- tested here anyway as a defensive
        # case) --
        ("free", _NONE, False),
        ("free", _FREE, True),
        ("free", _PRO, True),
        ("free", _ELITE, True),
        ("free", _SYNDICATE, True),
        # -- pro --
        ("pro", _FREE, False),
        ("pro", _PRO, True),
        ("pro", _ELITE, True),
        ("pro", _SYNDICATE, True),
        # -- elite --
        ("elite", _FREE, False),
        ("elite", _PRO, False),
        ("elite", _ELITE, True),
        ("elite", _SYNDICATE, True),
        # -- syndicate: the exact case the 2026-09-02 hotfix corrected
        # (a syndicate-gated product must be reachable by a syndicate-
        # equivalent resolved set, and only that set) --
        ("syndicate", _SYNDICATE, True),
        ("syndicate", _ELITE, False),
        ("syndicate", _PRO, False),
        ("syndicate", _FREE, False),
        ("syndicate", _NONE, False),
        # -- unknown/unrecognized tier strings: safe by default --
        ("unknown_future_tier", _SYNDICATE, False),
        ("pro", ["unknown_future_tier"], False),
    ],
)
def test_tier_permits_is_a_plain_membership_test(min_required_tier, permitted_tiers, expected):
    assert tier_permits(min_required_tier, permitted_tiers) is expected
