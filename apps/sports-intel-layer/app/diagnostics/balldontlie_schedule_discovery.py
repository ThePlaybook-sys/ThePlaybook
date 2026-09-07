"""Temporary, dev-only diagnostic probe -- Phase 7, Current-Week Real Game
Discovery (2026-09-07), HQ's directive to use BALLDONTLIE (paid GOAT-tier
DEV credential) as the authoritative schedule-discovery source for the
current NFL week.

Makes ONE real, raw call to `nfl/v1/games` (`seasons=[2026]`,
`weeks=[1]` -- Week 1 is the real, already-confirmed week number for the
existing 9/10 opener already tracked in this project's own `games` table,
not a guess) and logs the **raw, unmodified JSON** for every game
returned, at WARNING level (this project's own established finding: the
root logger here defaults to WARNING, so INFO-level diagnostic output
would otherwise be invisible in Railway logs). Deliberately logs the raw
payload rather than parsing it into a typed model first -- this probe's
whole purpose is to determine BALLDONTLIE's *actual* field shapes (in
particular, whether `date` carries a real kickoff time or only a calendar
date) before any permanent adapter code commits to an assumption about
it.

Gated behind `RUN_BALLDONTLIE_SCHEDULE_DISCOVERY=1`, reverted after use --
same "temporary probe, then revert" discipline as every prior diagnostic
pass this project has run (GNews validation, NFL provider bake-off, the
Odds API /events discovery probe). Real credential/client construction
lives in `app.master_refresh.production_clients` (not here) -- DEMO-1's
isolation guard forbids `app.main`'s own source from ever naming a
provider credential directly, and this probe is invoked from `app.main`."""
from __future__ import annotations

import logging

from app.master_refresh.production_clients import MissingCredentialError, build_real_balldontlie_client

_logger = logging.getLogger("sports-intel-layer.diagnostics.balldontlie_schedule_discovery")


async def run_balldontlie_schedule_discovery() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up."""
    try:
        balldontlie_client, api_key = build_real_balldontlie_client()
    except MissingCredentialError as exc:
        _logger.warning("balldontlie_schedule_discovery skipped: %s", exc)
        return

    try:
        response = await balldontlie_client.get(
            "/nfl/v1/games",
            params={"seasons[]": "2026", "weeks[]": "1", "per_page": "25"},
            headers={"Authorization": api_key},
        )
        _logger.warning(
            "balldontlie_schedule_discovery http_status=%s ratelimit_remaining=%s",
            response.status_code,
            response.headers.get("x-ratelimit-remaining"),
        )
        if response.status_code != 200:
            _logger.warning("balldontlie_schedule_discovery non-200 body=%s", response.text[:2000])
            return

        payload = response.json()
        games = payload.get("data", [])
        _logger.warning("balldontlie_schedule_discovery found %d real games", len(games))
        for game in games:
            _logger.warning("balldontlie_schedule_discovery raw_game=%s", game)
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("balldontlie_schedule_discovery failed: %s", exc)
    finally:
        await balldontlie_client.aclose()
