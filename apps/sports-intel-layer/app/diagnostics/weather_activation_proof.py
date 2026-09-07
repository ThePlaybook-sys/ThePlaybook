"""Temporary, dev-only diagnostic probe -- Phase 8.0.5 Weather Activation
(2026-09-07), HQ's explicit instruction: "execute one controlled real
WeatherAPI pull" before any recurring cron activation.

Calls the exact same REAL, permanent code path
`/v1/internal/weather-worker/run` calls (`run_weather_worker` with a real
`last_polled_at` derived from `weather_snapshots.captured_at`) -- not a
second implementation, not a mock. This probe exists only because this
sandbox cannot reach Railway's own private network to POST to that
endpoint directly and this session's Railway MCP connection returns
redacted variable values (no plaintext `INTERNAL_SERVICE_TOKEN` available
to authenticate such a call) -- the same constraint every prior temporary
probe in this project has worked around via a deploy-time startup hook +
Railway deploy logs.

Runs the worker TWICE, back to back, in the same process invocation --
proving dedup/idempotency behavior (an immediate repeat must not
re-persist already-covered games within the same cadence window) within
one controlled run, same discipline as the Pass 2.2 News proof.

Gated behind `RUN_WEATHER_ACTIVATION_PROOF=1`, reverted after use -- same
"temporary probe, then revert" discipline as every prior diagnostic pass.
Logs at WARNING (this project's own established finding: the root logger
here defaults to WARNING)."""
from __future__ import annotations

import logging

from app.master_refresh.production_clients import MissingCredentialError, build_real_weather_worker_clients
from app.persistence.weather_snapshots import read_last_polled_at
from app.workers.weather_worker import run_weather_worker

_logger = logging.getLogger("sports-intel-layer.diagnostics.weather_activation_proof")


async def run_weather_activation_proof() -> None:
    """Never raises -- a startup-hook failure here must not prevent the
    service itself from coming up."""
    try:
        supabase_client, weatherapi_client, weatherapi_api_key = build_real_weather_worker_clients()
    except MissingCredentialError as exc:
        _logger.warning("weather_activation_proof skipped: %s", exc)
        return

    try:
        last_polled_at_1 = await read_last_polled_at()
        result1 = await run_weather_worker(
            supabase_client=supabase_client,
            weatherapi_client=weatherapi_client,
            weatherapi_key=weatherapi_api_key,
            last_polled_at=last_polled_at_1,
        )
        _logger.warning("weather_activation_proof run1 result=%s", result1)

        last_polled_at_2 = await read_last_polled_at()
        result2 = await run_weather_worker(
            supabase_client=supabase_client,
            weatherapi_client=weatherapi_client,
            weatherapi_key=weatherapi_api_key,
            last_polled_at=last_polled_at_2,
        )
        _logger.warning("weather_activation_proof run2 (immediate repeat) result=%s", result2)
    except Exception as exc:  # noqa: BLE001 -- a diagnostic probe must never crash startup
        _logger.warning("weather_activation_proof failed: %s", exc)
    finally:
        await supabase_client.aclose()
        await weatherapi_client.aclose()
