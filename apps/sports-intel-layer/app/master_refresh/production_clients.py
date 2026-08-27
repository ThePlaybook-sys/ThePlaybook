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


def build_real_master_refresh_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, sportsdataio_client, sportsdataio_api_key)`
    bound to this process's real env vars -- the exact three positional
    inputs `run_master_refresh` needs beyond its own defaults. The
    caller owns closing both clients (e.g. via `async with`)."""
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    sportsdataio_client = httpx.AsyncClient(base_url=_SPORTSDATAIO_BASE_URL, timeout=60.0)
    sportsdataio_api_key = os.environ["SPORTSDATAIO_API_KEY"]
    return supabase_client, sportsdataio_client, sportsdataio_api_key
