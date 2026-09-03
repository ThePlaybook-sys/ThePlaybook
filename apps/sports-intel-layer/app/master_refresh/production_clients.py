"""Real, non-test client construction for `run_master_refresh`'s one
production caller (Pre-Phase-6 Operational Readiness Gate, Decision 6).

Deliberately NOT inlined into `app.main`: DEMO-1's own isolation-guard
test (`tests/test_environment_safety.py::
test_main_module_reads_no_provider_or_service_role_credential_by_name`)
requires `app.main`'s own source to never reference
`SPORTSDATAIO_API_KEY` (or any other provider/service-role credential)
by name, so there is nothing for a misconfigured demo deploy to leak
even if one of those vars were ever set there by mistake. This module is
where that real credential reading actually happens, exactly once, for
the one real caller that needs it -- `app.main.internal_run_master_refresh`
imports and calls this function, never reading the env var itself."""
from __future__ import annotations

import os

import httpx

#: The real, production SportsDataIO base URL -- confirmed against every
#: existing adapter test fixture's own respx mock target (`tests/adapters/
#: test_sportsdataio_adapters.py` and every worker test), never a
#: placeholder.
_SPORTSDATAIO_BASE_URL = "https://api.sportsdata.io"

#: The real, production The Odds API base URL -- matches
#: `tests/test_odds_worker.py::ODDS_API_URL` and `app.adapters.providers.
#: the_odds_api`'s own documented v4 REST contract.
_THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com"


class MissingCredentialError(Exception):
    """Raised when a required provider credential is absent from this
    process's environment. Deliberately distinct from a bare `KeyError` --
    callers (internal HTTP endpoints) catch this specific type to return a
    clean, structured "not configured" result instead of a raw exception,
    and its message never contains the credential's own value (there isn't
    one to contain -- the whole point is that it's missing)."""


def build_real_master_refresh_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, sportsdataio_client, sportsdataio_api_key)`
    bound to this process's real env vars -- the exact three positional
    inputs `run_master_refresh` needs beyond its own defaults. The
    caller owns closing both clients (e.g. via `async with`)."""
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    sportsdataio_client = httpx.AsyncClient(base_url=_SPORTSDATAIO_BASE_URL, timeout=60.0)
    sportsdataio_api_key = os.environ["SPORTSDATAIO_API_KEY"]
    return supabase_client, sportsdataio_client, sportsdataio_api_key


def build_real_odds_worker_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, the_odds_api_client, the_odds_api_key)` --
    the exact three positional inputs `run_odds_worker` needs beyond its
    own defaults. The caller owns closing both clients (e.g. via `async
    with`).

    **Phase 7 Milestone 7.0B (2026-09-02): the canonical credential
    convention for The Odds API is `THE_ODDS_API_KEY`** -- server-side
    only, never `NEXT_PUBLIC_*`, never logged, never returned by any
    health/status endpoint. This is the first real reader of that name;
    `tests/test_environment_safety.py::
    test_main_module_reads_no_provider_or_service_role_credential_by_name`
    already reserved it in `main_module`'s forbidden-names list ahead of
    this milestone, matching the same isolation discipline
    `SPORTSDATAIO_API_KEY` follows above -- `app.main`'s own source must
    never reference it by name, only this module may.

    Raises `MissingCredentialError` -- not `KeyError` -- if the key isn't
    set, so a caller can fail the request safely and clearly (per HQ's
    explicit instruction) before any network activity is attempted,
    without ever needing to reference the credential's name itself to do
    so."""
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        raise MissingCredentialError("THE_ODDS_API_KEY is not configured.")
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    the_odds_api_client = httpx.AsyncClient(base_url=_THE_ODDS_API_BASE_URL, timeout=60.0)
    return supabase_client, the_odds_api_client, api_key
