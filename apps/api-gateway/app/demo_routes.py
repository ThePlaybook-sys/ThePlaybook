"""Demo-facing proxy routes (DEMO-4, Decision 1/3).

Frontend -> API Gateway (`/v1/demo/...`) -> internal authenticated call ->
sports-intel-layer's Demo router (`/internal/demo/...`) -> `ScenarioRunner`
/ existing persistence reads. This module owns none of that logic itself
-- every handler is a thin proxy: forward the request, forward the
response status/body back. No scenario/business logic, no ScenarioRunner
duplication (Decision 3's explicit prohibition).

**Access control (Mac's decision, Option A): a single shared demo-operator
token**, `DEMO_OPERATOR_TOKEN` -- generated per-environment exactly like
`INTERNAL_SERVICE_TOKEN` (`secrets.token_hex(32)`, never reused across
environments), never set on `frontend` as a build-time secret (the
frontend never sees this module's env var; the operator types the token
into the browser once and it's sent back as a request header on every
`/v1/demo/*` call -- see `apps/frontend/app/demo/layout.tsx`). This is
deliberately a coarser, weaker gate than real per-user auth: anyone
holding the token has full Demo Mode control (start/step/reset), and
there is no per-operator audit trail -- acceptable for a low-stakes
internal demo tool, not a pattern to reuse for anything customer-facing.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException

from app.internal_client import InternalServiceError, call_sports_intel_layer


def _require_demo_access(x_demo_operator_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DEMO_OPERATOR_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="Demo operator token not configured")
    if not x_demo_operator_token or not hmac.compare_digest(x_demo_operator_token, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing demo operator token")


#: `/login` is deliberately its own un-gated router -- it exists ONLY so
#: the frontend's one-time token-entry prompt can find out whether what
#: the operator typed is correct BEFORE storing it, without that check
#: doubling as a real proxy call. Every other route below requires the
#: same token via `_require_demo_access`.
login_router = APIRouter(prefix="/v1/demo", tags=["demo"])


@login_router.post("/login")
def login(x_demo_operator_token: str | None = Header(default=None)) -> dict:
    _require_demo_access(x_demo_operator_token)
    return {"ok": True}


router = APIRouter(prefix="/v1/demo", tags=["demo"], dependencies=[Depends(_require_demo_access)])


async def _proxy(method: str, path: str, *, json: dict | None = None) -> dict | list:
    try:
        response = await call_sports_intel_layer(method, path, json=json)
    except InternalServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.get("/scenarios")
async def list_scenarios() -> list:
    return await _proxy("GET", "/internal/demo/scenarios")


@router.get("/status")
async def get_status() -> dict:
    return await _proxy("GET", "/internal/demo/status")


@router.post("/scenarios/{name}/load")
async def load_scenario(name: str) -> dict:
    return await _proxy("POST", f"/internal/demo/scenarios/{name}/load")


@router.post("/step")
async def step() -> dict:
    return await _proxy("POST", "/internal/demo/step")


@router.post("/run-to-checkpoint")
async def run_to_checkpoint() -> dict:
    return await _proxy("POST", "/internal/demo/run-to-checkpoint")


@router.post("/run")
async def run_to_completion() -> dict:
    return await _proxy("POST", "/internal/demo/run")


@router.post("/reset")
async def reset() -> dict:
    return await _proxy("POST", "/internal/demo/reset")


@router.get("/games")
async def list_active_games() -> list:
    return await _proxy("GET", "/internal/demo/games")


@router.get("/games/{game_id}/intelligence")
async def get_game_intelligence(game_id: str) -> dict:
    return await _proxy("GET", f"/internal/demo/games/{game_id}/intelligence")
