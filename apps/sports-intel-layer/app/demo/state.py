"""Process-local `ScenarioRunner` singleton (DEMO-4).

DEMO-3's own explicit decision (Mac, "Prefer in-memory for DEMO-3 unless
restart persistence is genuinely required") extended one step further: one
`ScenarioRunner` instance lives for the lifetime of this process, shared
across every request the new demo router handles. A process restart loses
scenario-control state -- exactly as already approved -- there is still no
Demo-only Supabase control-state table.

This is the only place in DEMO-4 that constructs the real `supabase_client`
pointed at whatever `SUPABASE_URL` this process was started with. Every
demo route still independently re-verifies isolation before using it
(`app.demo.router`'s own guard, Decision 4) -- this module holds no
opinion about which project that URL points to.
"""
from __future__ import annotations

import os

import httpx

from app.demo.runner import ScenarioRunner

_runner: ScenarioRunner | None = None


def auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def get_runner() -> ScenarioRunner:
    global _runner
    if _runner is None:
        supabase_client = httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=10.0)
        _runner = ScenarioRunner(supabase_client=supabase_client)
    return _runner


def discard_runner() -> None:
    """Drops the singleton so the next `get_runner()` call starts clean --
    called after a successful destructive reset so in-memory control state
    never claims a scenario is mid-run against data that no longer
    exists. Does not itself touch Supabase."""
    global _runner
    _runner = None
