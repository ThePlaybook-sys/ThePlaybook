"""Shared test setup for `apps/workers`.

Created 2026-09-18 for Recomputation V1, which added one Supabase read that
EVERY recommendation cycle now performs: `read_game_ids_with_completed_paid_cycle`
against `/rest/v1/recommendations`.

Without a default, fourteen pre-existing tests would fail on an unmocked
route -- not because their behaviour changed, but because a new
infrastructure read appeared underneath them. Registering a permissive
default here keeps those tests testing what they were written to test.

**The default is deliberately inert**, and that matters: it returns `[]`,
i.e. *no game has completed a paid cycle*. So a test that does not opt in
sees the new rule as a no-op and its slate behaves exactly as it did
before. The tests that actually exercise the rule
(`test_recomputation_v1.py`) release the default and register their own.

Mirrors `apps/sports-intel-layer/tests/conftest.py`, which solved the
identical problem for the odds hardening pass -- same idiom, same
release-by-name escape hatch, so there is one pattern in this repository
rather than two.

Registered before respx's own per-test snapshot is taken, so these act as
fallbacks rather than overriding anything a test sets up for itself.
"""
from __future__ import annotations

import httpx
import pytest
import respx

#: Name for the default route, so a test that needs to assert on this
#: endpoint can release it and register its own. respx matches routes in
#: registration order and this is registered first, so without releasing
#: it a test-specific route would never be reached.
COMPLETED_PAID_CYCLES_GET = "default_recommendations_completed_paid_cycles_get"


def release_default_route(*names: str) -> None:
    """Drops a default registered by `_default_recomputation_routes`, so the
    caller can register its own behaviour for that endpoint."""
    for name in names:
        respx.mock.pop(name, None)


@pytest.fixture(autouse=True)
def _default_recomputation_routes():
    """Permissive, inert default for the read added by Recomputation V1.
    Rolled back after every test."""
    router = respx.mock
    snapshot = list(router.routes)
    # Matched on PATH rather than full URL so any Supabase base a test
    # chooses is covered.
    router.route(
        method="GET", path="/rest/v1/recommendations", name=COMPLETED_PAID_CYCLES_GET
    ).mock(return_value=httpx.Response(200, json=[]))
    try:
        yield
    finally:
        router.routes.clear()
        for route in snapshot:
            router.routes.add(route)
