"""Temporary, dev-only diagnostic probe -- Phase 8.0.5 Data Activation
Pass 1 (2026-09-07), HQ's explicit authorization: "We explicitly
authorize controlled one-time live DEV pulls for News and BALLDONTLIE
Injuries. Do not wait for kickoff or an unrelated Odds Worker window."

Calls the two REAL, permanent worker functions this pass built
(`run_balldontlie_injury_worker`, `run_news_worker` injected with
`GNewsNewsAdapter`) directly -- not a second implementation, not a mock,
the exact same code path the new internal HTTP endpoints
(`/v1/internal/balldontlie-injury-worker/run`, `/v1/internal/news-worker/run`)
call. This probe exists only because there is no cron tick yet to fire
either endpoint and this sandbox cannot reach Railway's own internal
network to POST to them directly -- the same constraint every prior
temporary probe in this project has worked around via a deploy-time
startup hook + Railway deploy logs.

Gated behind `RUN_DATA_ACTIVATION_PASS1_PROOF=1`, reverted after use --
same "temporary probe, then revert" discipline as every prior diagnostic
pass. Logs at WARNING (this project's own established finding: the root
logger here defaults to WARNING)."""
from __future__ import annotations

import logging

from app.adapters.providers.gnews import GNewsNewsAdapter
from app.master_refresh.production_clients import (
    MissingCredentialError,
    build_real_balldontlie_injury_worker_clients,
    build_real_news_worker_clients,
)
from app.workers.balldontlie_injury_worker import run_balldontlie_injury_worker
from app.workers.news_worker import run_news_worker

_logger = logging.getLogger("sports-intel-layer.diagnostics.data_activation_pass1_proof")


async def _run_balldontlie_injury_proof() -> None:
    try:
        supabase_client, balldontlie_client, balldontlie_api_key = build_real_balldontlie_injury_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("data_activation_pass1_proof balldontlie_injury skipped: %s", exc)
        return
    try:
        result = await run_balldontlie_injury_worker(
            supabase_client=supabase_client,
            balldontlie_client=balldontlie_client,
            balldontlie_api_key=balldontlie_api_key,
        )
        _logger.warning("data_activation_pass1_proof balldontlie_injury result=%s", result)

        # Diagnostic-only comparison call (2026-09-07, same-day follow-up):
        # the injuries call above returned a real 401 despite the exact
        # same api_key/header shape this session's own earlier schedule-
        # discovery probe used successfully against /nfl/v1/games -- this
        # single extra call disambiguates "the key itself is broken" from
        # "this endpoint specifically is inaccessible on the current plan",
        # never re-run once that answer is known.
        games_response = await balldontlie_client.get(
            "/nfl/v1/games",
            params={"seasons[]": "2026", "weeks[]": "1", "per_page": "1"},
            headers={"Authorization": balldontlie_api_key},
        )
        _logger.warning(
            "data_activation_pass1_proof balldontlie_games_comparison_call http_status=%s",
            games_response.status_code,
        )
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("data_activation_pass1_proof balldontlie_injury failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await balldontlie_client.aclose()


async def _run_news_proof() -> None:
    try:
        supabase_client, gnews_client, gnews_api_key = build_real_news_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("data_activation_pass1_proof news skipped: %s", exc)
        return
    try:
        result = await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=gnews_client,
            newsapi_key=gnews_api_key,
            news_adapter=GNewsNewsAdapter(client=gnews_client, api_key=gnews_api_key),
        )
        _logger.warning("data_activation_pass1_proof news result=%s", result)
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("data_activation_pass1_proof news failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await gnews_client.aclose()


async def run_data_activation_pass1_proof() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up. Runs both real pulls sequentially
    (BALLDONTLIE's own 5 req/min rate limit and GNews's own limits are
    both comfortably respected by two single calls run one after the
    other, not concurrently)."""
    await _run_balldontlie_injury_proof()
    await _run_news_proof()
