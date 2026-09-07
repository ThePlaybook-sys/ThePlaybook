"""Temporary, dev-only diagnostic probe -- Phase 8.0.5 Data Activation
Pass 2 (2026-09-07), HQ's explicit authorization: execute another
controlled real DEV News pull to verify the new inter-call pacing fix
resolves Pass 1's real GNews rate-limit failures.

Calls the exact same real code path as the permanent
`/v1/internal/news-worker/run` endpoint -- `run_news_worker` injected
with `GNewsNewsAdapter` and the same `inter_call_delay_seconds=5.0`
that endpoint now passes. Exists only because there is no cron tick yet
and this sandbox cannot reach Railway's internal network directly.

Gated behind `RUN_NEWS_PACING_PROOF=1`, reverted after use -- same
"temporary probe, then revert" discipline as every prior diagnostic
pass. Logs at WARNING (this project's own established finding)."""
from __future__ import annotations

import logging

from app.adapters.providers.gnews import GNewsNewsAdapter
from app.master_refresh.production_clients import MissingCredentialError, build_real_news_worker_clients
from app.workers.news_worker import run_news_worker

_logger = logging.getLogger("sports-intel-layer.diagnostics.news_pacing_proof")


async def run_news_pacing_proof() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up."""
    try:
        supabase_client, gnews_client, gnews_api_key = build_real_news_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("news_pacing_proof skipped: %s", exc)
        return
    try:
        result = await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=gnews_client,
            newsapi_key=gnews_api_key,
            news_adapter=GNewsNewsAdapter(client=gnews_client, api_key=gnews_api_key),
            inter_call_delay_seconds=5.0,
        )
        _logger.warning("news_pacing_proof result=%s", result)
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("news_pacing_proof failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await gnews_client.aclose()
