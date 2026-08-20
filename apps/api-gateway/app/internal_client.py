"""Internal service-to-service HTTP client (DEMO-4, Decision 2/3).

The API Gateway side of the same `INTERNAL_SERVICE_TOKEN` seam
`sports-intel-layer/app/internal_auth.py` guards its `/internal/demo/*`
routes with -- confirmed by direct inspection of the already-established
project convention (`docs/ops/secrets-management.md`, Milestone 3) before
reuse, not a new credential or a redesign of existing service auth.

`SPORTS_INTEL_LAYER_URL` (new, DEMO-4): the one thing this seam needed
that didn't already exist -- no prior code in this repo had API Gateway
call another internal service, so there was no established env var name
for "where is sports-intel-layer" to reuse. Expected to be each
environment's Railway private-networking address for that service (e.g.
`http://sports-intel-layer.railway.internal:PORT`) once actually set;
this module has no opinion about the value beyond reading it.
"""
from __future__ import annotations

import os

import httpx
from fastapi import HTTPException


class InternalServiceError(Exception):
    """Raised when the internal call itself fails at the transport level
    (connection refused, timeout) -- distinct from the called service
    returning a normal HTTP error status, which callers forward as-is."""


def _internal_headers() -> dict:
    token = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="Internal service token not configured")
    return {"X-Internal-Token": token}


async def call_sports_intel_layer(
    method: str, path: str, *, json: dict | None = None, timeout: float = 10.0
) -> httpx.Response:
    """Proxies one request to `sports-intel-layer`'s `/internal/demo/*`
    router, attaching the internal service token. Never logs the token;
    never echoes it back in any response this function returns."""
    base_url = os.environ.get("SPORTS_INTEL_LAYER_URL")
    if not base_url:
        raise HTTPException(status_code=500, detail="SPORTS_INTEL_LAYER_URL not configured")
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            return await client.request(method, path, json=json, headers=_internal_headers())
    except httpx.HTTPError as exc:
        raise InternalServiceError(f"sports-intel-layer call failed: {method} {path}: {exc}") from exc
