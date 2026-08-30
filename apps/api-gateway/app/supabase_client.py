"""Shared Supabase REST client construction for API Gateway's Phase 6
Milestone 2 read routes (recommendations, track record, subscription).

Mirrors `main.py`'s own `_postgrest_headers()` and
`ai-orchestrator`'s `app.supabase_client` -- same convention, extracted
here so the new Milestone 2 modules don't each redefine it. `main.py`'s
existing two routes are left exactly as they are (untouched, still
using their own inline helper) since they are outside this milestone's
scope.
"""
from __future__ import annotations

import os

import httpx


def postgrest_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}


def new_client(*, timeout: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=timeout)
