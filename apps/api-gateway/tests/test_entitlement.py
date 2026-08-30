"""Unit tests for app.entitlement.tier_permits -- mirrors
recommendation_products_tier_gated_select exactly, including the real
policy gap discovered during Milestone 2's pre-implementation
inspection (see the function's own docstring)."""
from __future__ import annotations

import pytest

from app.entitlement import tier_permits


@pytest.mark.parametrize(
    "min_required_tier,user_tier,expected",
    [
        ("free", None, True),
        ("free", "free", True),
        ("free", "elite", True),
        ("pro", None, False),
        ("pro", "free", False),
        ("pro", "pro", True),
        ("pro", "elite", True),
        ("pro", "syndicate", True),
        ("elite", "pro", False),
        ("elite", "elite", True),
        ("elite", "syndicate", True),
        # The discovered gap: 'syndicate' is schema-permitted but the
        # real DB policy never grants access to it, for any tier --
        # this function must reproduce that exactly, not "fix" it.
        ("syndicate", "syndicate", False),
        ("syndicate", None, False),
    ],
)
def test_tier_permits_mirrors_the_real_rls_policy(min_required_tier, user_tier, expected):
    assert tier_permits(min_required_tier, user_tier) is expected
