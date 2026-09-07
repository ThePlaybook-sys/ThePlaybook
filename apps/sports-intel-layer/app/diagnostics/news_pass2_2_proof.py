"""Temporary, dev-only diagnostic probe -- Phase 8.0.5 Pass 2.2
(2026-09-07), HQ's explicit instruction: "perform one controlled real
run" against the new durable quota guard + persisted last_polled_at
before re-enabling `cron-news-worker`.

Calls the exact same REAL, permanent code path
`/v1/internal/news-worker/run` calls (`run_news_worker` injected with
`GNewsNewsAdapter`, `persist_state=True`) -- not a second implementation,
not a mock. This probe exists only because this sandbox cannot reach
Railway's own private network to POST to that endpoint directly and this
session's Railway MCP connection returns redacted variable values (no
plaintext `INTERNAL_SERVICE_TOKEN` available to authenticate such a call)
-- the same constraint every prior temporary probe in this project has
worked around via a deploy-time startup hook + Railway deploy logs.

Runs the worker TWICE, back to back, in the same process invocation --
directly proving HQ's explicit "verify immediate repeat does not refetch
every team" requirement within one controlled run, not merely asserted
from unit tests.

Gated behind `RUN_NEWS_PASS2_2_PROOF=1`, reverted after use -- same
"temporary probe, then revert" discipline as every prior diagnostic pass.
Logs at WARNING (this project's own established finding: the root logger
here defaults to WARNING)."""
from __future__ import annotations

import logging

from app.adapters.providers.gnews import GNewsNewsAdapter
from app.master_refresh.production_clients import MissingCredentialError, build_real_news_worker_clients
from app.workers.news_worker import run_news_worker

_logger = logging.getLogger("sports-intel-layer.diagnostics.news_pass2_2_proof")


async def run_news_pass2_2_proof() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up."""
    try:
        supabase_client, gnews_client, gnews_api_key = build_real_news_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("news_pass2_2_proof skipped: %s", exc)
        return

    try:
        result1 = await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=gnews_client,
            newsapi_key=gnews_api_key,
            news_adapter=GNewsNewsAdapter(client=gnews_client, api_key=gnews_api_key),
            inter_call_delay_seconds=5.0,
            persist_state=True,
        )
        _logger.warning("news_pass2_2_proof run1 result=%s", result1)

        result2 = await run_news_worker(
            supabase_client=supabase_client,
            newsapi_client=gnews_client,
            newsapi_key=gnews_api_key,
            news_adapter=GNewsNewsAdapter(client=gnews_client, api_key=gnews_api_key),
            inter_call_delay_seconds=5.0,
            persist_state=True,
        )
        _logger.warning("news_pass2_2_proof run2 (immediate repeat) result=%s", result2)
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("news_pass2_2_proof failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await gnews_client.aclose()
