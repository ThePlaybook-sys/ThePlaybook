"""Temporary, dev-only diagnostic probe -- Phase 7 Controlled Real Odds
Activation (2026-09-07), HQ's own locked rule after a real incident:
"never create a canonical real-world game from an assumed or invented
matchup; real game seeds require authoritative provider/source
evidence." Calls The Odds API's free (0-credit) `/events` discovery
endpoint and logs every real event found, so a Sunday tracking cluster
can be selected from that evidence directly rather than guessed.

Gated behind `RUN_ODDS_EVENTS_DISCOVERY=1`, reverted after use -- same
"temporary probe, then revert" discipline as every prior diagnostic pass
this project has run (GNews validation, NFL provider bake-off). Never
spends a credit -- `fetch_events()` is the free endpoint, not the paid
bulk `/odds` call `run_odds_worker` itself uses."""
from __future__ import annotations

import logging

from app.adapters.providers.the_odds_api import TheOddsApiOddsAdapter
from app.master_refresh.production_clients import MissingCredentialError, build_real_odds_worker_clients

_logger = logging.getLogger("sports-intel-layer.diagnostics.odds_events_discovery")


async def run_odds_events_discovery() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up. Logs at WARNING (this project's own
    established finding: the root logger here defaults to WARNING, so
    INFO-level diagnostic output would otherwise be invisible in Railway
    logs)."""
    try:
        supabase_client, the_odds_api_client, the_odds_api_key = build_real_odds_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("odds_events_discovery skipped: %s", exc)
        return

    try:
        adapter = TheOddsApiOddsAdapter(client=the_odds_api_client, api_key=the_odds_api_key)
        response = await adapter.fetch_events()
        _logger.warning("odds_events_discovery found %d real events", len(response.value))
        for event in response.value:
            _logger.warning(
                "odds_events_discovery event id=%s home=%r away=%r commence_time=%s",
                event.provider_event_id,
                event.home_team,
                event.away_team,
                event.commence_time.isoformat(),
            )
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("odds_events_discovery failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await the_odds_api_client.aclose()
