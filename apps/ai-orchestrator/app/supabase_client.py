"""Supabase REST client construction for the AI Orchestrator (Milestone 4.1).

Mirrors the identical `httpx.AsyncClient(base_url=SUPABASE_URL)` +
`{Authorization, apikey}` header convention every other backend service in
this repo already uses (`sports-intel-layer`'s `master_refresh.run.
_auth_headers`, `app.demo.state`'s client construction) -- same
convention, not a new one invented here.

Both functions read their environment variable lazily, inside the
function body, not at module import time -- this module can be imported
(and its callers' tests can run) without `SUPABASE_URL`/
`SUPABASE_SERVICE_ROLE_KEY` ever being set, which matters specifically
because Milestone 4.1 does NOT configure `SUPABASE_SERVICE_ROLE_KEY` on
this service yet (Decision 3) -- only a caller that actually attempts a
live connection needs it to exist.
"""
from __future__ import annotations

import os

import httpx


def auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
    }


def new_client(*, timeout: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=timeout)
