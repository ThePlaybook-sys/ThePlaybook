"""Supabase REST client construction for the Background Workers service
(Milestone 4.9). Mirrors `ai-orchestrator`'s `app.supabase_client`
exactly -- same `httpx.AsyncClient(base_url=SUPABASE_URL)` +
`{Authorization, apikey}` header convention every backend service in
this repo already uses. Both functions read their environment variable
lazily, inside the function body, not at module import time -- this
module can be imported (and the health check can run) without
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` ever being set."""
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
