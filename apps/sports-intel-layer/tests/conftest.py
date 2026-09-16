"""Shared test setup.

Created 2026-09-16 for the Odds Worker cost + failure hardening pass, which
added two Supabase tables that EVERY odds run now touches:
`odds_worker_poll_state` (attempt state) and `odds_api_daily_call_budget`
(the per-day call ceiling).

Without a default, all forty-two pre-existing odds tests would fail on an
unmocked route -- not because their behaviour changed, but because two new
infrastructure endpoints appeared underneath them. Registering permissive
defaults here keeps those tests testing what they were written to test.

**These defaults are deliberately inert**, and that matters:

  * `odds_worker_poll_state` GET returns `[]` -- no game has attempt state,
    so no game is ever suppressed by backoff and due-selection falls through
    to exactly the cadence-only behaviour those tests were written against.
  * the POST accepts the write and returns 201, so recording an attempt
    never fails a run that is really testing something else.
  * `increment_odds_api_daily_calls` returns 1, a low number that can never
    trip a ceiling.
  * `odds_api_daily_call_budget` GET returns `[]`, i.e. zero calls used
    today.

So a test that does not opt in sees the new machinery as a no-op. The tests
that actually exercise backoff and budget behaviour
(`test_odds_worker_cost_and_failure_hardening.py`) register their own routes,
which take precedence for the specific behaviour they assert.

Registered before respx's own per-test snapshot is taken, so these act as
fallbacks rather than overriding anything a test sets up for itself.
"""
from __future__ import annotations

import httpx
import pytest
import respx

SUPABASE_URL = "https://test-project.supabase.co"

#: Names for the default routes, so a test that needs to assert on one of
#: these endpoints can release the default and register its own. respx
#: matches routes in registration order and these are registered first, so
#: without releasing them a test-specific route would never be reached.
POLL_STATE_GET = "default_odds_poll_state_get"
POLL_STATE_POST = "default_odds_poll_state_post"
DAILY_BUDGET_GET = "default_odds_daily_budget_get"
DAILY_BUDGET_INCREMENT = "default_odds_daily_budget_increment"
CREDIT_LEDGER_INCREMENT = "default_odds_credit_ledger_increment"
CREDIT_LEDGER_RECONCILE = "default_odds_credit_ledger_reconcile"


def release_default_route(*names: str) -> None:
    """Drops a default registered by `_default_odds_hardening_routes`, so the
    caller can register its own behaviour for that endpoint.

    Used by `test_odds_worker_cost_and_failure_hardening.py`, which is the
    file that actually exercises these tables rather than merely tolerating
    them.
    """
    for name in names:
        respx.mock.pop(name, None)


@pytest.fixture(autouse=True)
def _default_odds_hardening_routes():
    """Permissive, inert defaults for the two tables added by the 2026-09-16
    hardening pass. Rolled back after every test."""
    router = respx.mock
    snapshot = list(router.routes)
    # Matched on PATH rather than full URL, so these also cover the demo
    # project's own Supabase host -- Demo Mode runs the real
    # `run_odds_worker` against a different base URL, and a host-specific
    # default would leave its scenario tests failing on an unmocked route.
    router.route(
        method="GET", path="/rest/v1/odds_worker_poll_state", name=POLL_STATE_GET
    ).mock(return_value=httpx.Response(200, json=[]))
    router.route(
        method="POST", path="/rest/v1/odds_worker_poll_state", name=POLL_STATE_POST
    ).mock(return_value=httpx.Response(201))
    router.route(
        method="GET", path="/rest/v1/odds_api_daily_call_budget", name=DAILY_BUDGET_GET
    ).mock(return_value=httpx.Response(200, json=[]))
    router.route(
        method="POST", path="/rest/v1/rpc/increment_odds_api_daily_calls", name=DAILY_BUDGET_INCREMENT
    ).mock(return_value=httpx.Response(200, json=1))
    # Monthly-period credit ledger (2026-09-16). Writes moved from a
    # read-then-write upsert on the table to two atomic RPCs, so every test
    # that exercises a real fetch now touches these paths. Both defaults are
    # inert: a low credit count that cannot trip any guard, and a
    # reconciliation that records nothing interesting.
    router.route(
        method="POST", path="/rest/v1/rpc/increment_odds_api_credits", name=CREDIT_LEDGER_INCREMENT
    ).mock(return_value=httpx.Response(200, json=3))
    router.route(
        method="POST",
        path="/rest/v1/rpc/reconcile_odds_api_provider_usage",
        name=CREDIT_LEDGER_RECONCILE,
    ).mock(return_value=httpx.Response(200, json=3))
    try:
        yield
    finally:
        router.routes.clear()
        for route in snapshot:
            router.routes.add(route)
