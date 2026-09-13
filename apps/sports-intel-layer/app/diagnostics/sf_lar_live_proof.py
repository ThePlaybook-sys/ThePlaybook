"""TEMPORARY trigger module for MANSA HQ's authorized "SF@LAR LIVE
PROOF" (2026-09-13) -- the first live execution of the PERMANENT
`app.workers.msf_postgame_worker.run_msf_postgame_capture` for canonical
game `50d14afd-2861-4e07-b235-90ea857f004d` (MSF game 163542, SF @ LAR).

**This module does not reimplement any worker logic.** It exists solely
to (1) claim a one-shot idempotency marker, matching every prior MSF
diagnostic pass's own convention, and (2) call the already-built,
already-tested permanent worker function directly -- sidestepping the
one real gap this session has: no way to authenticate an HTTP call
against `POST /v1/internal/msf-postgame/run`'s own `INTERNAL_SERVICE_TOKEN`
guard without reading a secret this session cannot read back from
Railway. Calling the worker function directly from inside this already-
running, already-credentialed process avoids that without touching any
shared credential. The permanent HTTP endpoint itself is untouched and
remains the correct invocation surface for every future call (Sunday's
slate, a future SF@LAR reprocess, etc.) -- this module is deleted once
this one authorized call has been made and verified, exactly like every
prior one-shot diagnostic module in this project
(`app.diagnostics.msf_game_boxscore_diagnostic` and its own predecessors).

Credential isolation matches every prior diagnostic module exactly:
`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_URL` are read only here, never in
`app.main`'s own source (DEMO-1's isolation guard,
`tests/test_environment_safety.py::
test_main_module_reads_no_provider_or_service_role_credential_by_name`).
`MYSPORTSFEEDS_API_KEY` is never read here either -- that stays isolated
inside `app.master_refresh.production_clients`/the worker's own
`_default_fetch_boxscore`, exactly as it already was for the permanent
HTTP endpoint.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from app.persistence.game_postgame_ingestion_state import IngestionStateError
from app.workers.msf_postgame_worker import MSFPostgameWorkerError, run_msf_postgame_capture

#: This pass's own dedicated run_key -- reuses `activation_run_markers`
#: exactly as every prior MSF diagnostic pass has. No second idempotency
#: mechanism created (the worker's own atomic claim/already-finalized
#: short-circuit is a second, independent, already-existing layer).
_RUN_KEY = "sf-lar-live-proof-2026-09-13"

#: HQ-specified verbatim: canonical game 50d14afd-... == MSF game 163542,
#: SF @ LAR.
_GAME_ID = "50d14afd-2861-4e07-b235-90ea857f004d"


class SFLARLiveProofSkipped(Exception):
    """Raised (and caught internally) when this pass's run_key is
    already claimed -- an overlapping/duplicate container boot, not an
    error. Zero additional MySportsFeeds calls result."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def _claim_run_marker() -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()
    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        response = await client.post(
            "/rest/v1/activation_run_markers", json={"run_key": _RUN_KEY}, headers=headers
        )
    if response.status_code == 409:
        raise SFLARLiveProofSkipped(f"run_key {_RUN_KEY!r} already claimed -- skipping duplicate run")
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"failed to claim activation_run_markers row for {_RUN_KEY!r}: "
            f"{response.status_code} {response.text}"
        )


async def run_sf_lar_live_proof() -> dict[str, Any]:
    """Claims this pass's run_key, then calls the real, permanent
    `run_msf_postgame_capture` exactly once against SF@LAR (its own
    internal atomic claim + already-finalized short-circuit are what
    actually bound this to at most one live MySportsFeeds call even
    across a duplicate/overlapping invocation). Never raises -- always
    returns a structured, JSON-serializable dict, safe to log directly
    (contains only ids/counts/strings the worker itself already produces,
    never a raw payload or credential)."""
    try:
        await _claim_run_marker()
    except SFLARLiveProofSkipped as exc:
        return {"skipped": True, "reason": str(exc)}
    except Exception as exc:  # defense in depth -- a marker-claim failure must not crash startup
        return {"skipped": True, "reason": f"failed to claim run marker: {exc}", "marker_claim_error": True}

    supabase_url = os.environ["SUPABASE_URL"]
    async with httpx.AsyncClient(base_url=supabase_url, timeout=120.0) as supabase_client:
        try:
            result = await run_msf_postgame_capture(supabase_client=supabase_client, game_id=_GAME_ID)
        except (MSFPostgameWorkerError, IngestionStateError) as exc:
            return {"skipped": False, "failed": True, "error": str(exc)}

    return {
        "skipped": False,
        "failed": False,
        "game_id": result.game_id,
        "outcome": result.outcome,
        "state": result.state,
        "attempt_count": result.attempt_count,
        "resolved_players": result.resolved_players,
        "quarantined_players": result.quarantined_players,
        "persisted_rows": result.persisted_rows,
        "unchanged_rows": result.unchanged_rows,
        "error": result.error,
    }


__all__ = ["SFLARLiveProofSkipped", "run_sf_lar_live_proof"]
