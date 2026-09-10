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

#: The real, production BALLDONTLIE base URL -- confirmed from the
#: official `balldontlie` PyPI package's own `client.py` source
#: (`BalldontlieAPI.__init__`'s default), the same provenance discipline
#: used for the 2026-09-03 NFL provider bake-off (this sandbox's egress
#: policy blocks balldontlie.io directly, same as every other vendor).
_BALLDONTLIE_BASE_URL = "https://api.balldontlie.io"

#: The real, production GNews base URL -- confirmed from the official
#: `gnews-io/gnews-io-js` client's own documented base, carried forward
#: from the 2026-09-03 News Provider Validation's own (reverted)
#: diagnostic, which used this exact value against the real API.
_GNEWS_BASE_URL = "https://gnews.io"

#: The real, production WeatherAPI.com base URL -- matches
#: `app.adapters.providers.weatherapi.WeatherAPIWeatherAdapter`'s own
#: `/v1/forecast.json` path and every existing WeatherAPI adapter test
#: fixture's respx mock target.
_WEATHERAPI_BASE_URL = "https://api.weatherapi.com"

#: The real, production MySportsFeeds v2.1 base URL, diagnostic use only
#: (MANSA Gate B Railway Diagnostic Build, 2026-09-10 -- see
#: `app.diagnostics.msf_game_boxscore_diagnostic`). CONFIRMED from the
#: official `mysportsfeeds-node` npm package source (`API_v2_1.js`),
#: identical to every prior MSF diagnostic's own value (all since
#: reverted, e.g. Phase 8.3C).
_MYSPORTSFEEDS_BASE_URL = "https://api.mysportsfeeds.com/v2.1/pull"


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


def build_real_balldontlie_client() -> tuple[httpx.AsyncClient, str]:
    """Returns `(balldontlie_client, balldontlie_api_key)` -- Phase 7 Real
    Sunday Cluster Discovery (2026-09-07 follow-up), HQ's directive to use
    BALLDONTLIE (on its paid GOAT-tier DEV credential) as the authoritative
    schedule-discovery source. Same isolation discipline as every other
    credential reader in this module: `BALLDONTLIE_API_KEY` is read here
    only, never by `app.main`'s own source
    (`tests/test_environment_safety.py::
    test_main_module_reads_no_provider_or_service_role_credential_by_name`
    reserves the name), and `MissingCredentialError` -- not a raw
    `KeyError` -- is raised if it isn't configured. The caller owns
    closing the returned client (e.g. via `async with`)."""
    api_key = os.environ.get("BALLDONTLIE_API_KEY")
    if not api_key:
        raise MissingCredentialError("BALLDONTLIE_API_KEY is not configured.")
    balldontlie_client = httpx.AsyncClient(base_url=_BALLDONTLIE_BASE_URL, timeout=60.0)
    return balldontlie_client, api_key


def build_real_balldontlie_injury_worker_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, balldontlie_client, balldontlie_api_key)`
    -- Phase 8.0.5 Data Activation Pass 1 (2026-09-07), the three
    positional inputs `run_balldontlie_injury_worker` needs. Same
    `BALLDONTLIE_API_KEY` credential as `build_real_balldontlie_client`
    above -- a separate function only because this caller also needs a
    bound `supabase_client`, matching the exact three-tuple shape every
    other `build_real_*_worker_clients` function in this module already
    returns. Raises `MissingCredentialError` if the key isn't configured.
    The caller owns closing both clients."""
    api_key = os.environ.get("BALLDONTLIE_API_KEY")
    if not api_key:
        raise MissingCredentialError("BALLDONTLIE_API_KEY is not configured.")
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    balldontlie_client = httpx.AsyncClient(base_url=_BALLDONTLIE_BASE_URL, timeout=60.0)
    return supabase_client, balldontlie_client, api_key


def build_real_news_worker_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, gnews_client, gnews_api_key)` -- Phase
    8.0.5 Data Activation Pass 1 (2026-09-07), HQ's explicit instruction
    to use the existing GNews DEV credential (`GNEWS_API_KEY`) for this
    activation, not `NEWSAPI_API_KEY` (confirmed absent from this
    environment by a live check this same session). Same isolation
    discipline as every other credential reader in this module --
    `GNEWS_API_KEY` is read here only, `MissingCredentialError` (not a
    raw `KeyError`) if it isn't configured. The caller owns closing both
    clients."""
    api_key = os.environ.get("GNEWS_API_KEY")
    if not api_key:
        raise MissingCredentialError("GNEWS_API_KEY is not configured.")
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    gnews_client = httpx.AsyncClient(base_url=_GNEWS_BASE_URL, timeout=60.0)
    return supabase_client, gnews_client, api_key


def build_real_weather_worker_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient, str]:
    """Returns `(supabase_client, weatherapi_client, weatherapi_api_key)` --
    Phase 8.0.5 Weather Activation (2026-09-07), now that
    `WEATHERAPI_API_KEY` is configured in Railway DEV. Same isolation
    discipline as every other credential reader in this module --
    `WEATHERAPI_API_KEY` is read here only (already reserved in
    `tests/test_environment_safety.py`'s forbidden-names list ahead of
    this moment), `MissingCredentialError` (not a raw `KeyError`) if it
    isn't configured. The caller owns closing both clients."""
    api_key = os.environ.get("WEATHERAPI_API_KEY")
    if not api_key:
        raise MissingCredentialError("WEATHERAPI_API_KEY is not configured.")
    supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=60.0)
    weatherapi_client = httpx.AsyncClient(base_url=_WEATHERAPI_BASE_URL, timeout=60.0)
    return supabase_client, weatherapi_client, api_key


def build_msf_game_boxscore_diagnostic_client() -> tuple[httpx.AsyncClient, str] | None:
    """MANSA Gate B Railway Diagnostic Build (2026-09-10, diagnostic
    only -- see `app.diagnostics.msf_game_boxscore_diagnostic`): returns
    `(client, api_key)` bound to `MYSPORTSFEEDS_API_KEY`, or `None` if
    that credential isn't configured. 120.0s timeout from the start --
    Phase 8.3B/8.3C's own proven lesson (a 30.0s timeout was too short
    for at least one other MySportsFeeds v2.1 feed) applied immediately,
    not re-learned the hard way. `MYSPORTSFEEDS_API_KEY` is never read
    anywhere outside this function, matching the isolation convention
    every other provider credential in this module already follows. The
    caller owns closing the returned client."""
    api_key = os.environ.get("MYSPORTSFEEDS_API_KEY")
    if not api_key:
        return None
    return httpx.AsyncClient(base_url=_MYSPORTSFEEDS_BASE_URL, timeout=120.0), api_key
