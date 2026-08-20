"""Demo control/read routes (DEMO-4, Decision 3).

Thin wrappers only -- every handler below either delegates straight to
`app.demo.state.get_runner()`'s `ScenarioRunner` (DEMO-3) or to an
existing, unmodified persistence read helper (`app.persistence.games`,
`app.persistence.daily_game_intelligence`). No scenario/business logic is
implemented in this file; a handler with more than a few lines of its own
logic beyond request/response shaping would be a sign this module has
drifted from that boundary.

**Decision 4 -- do not trust route naming alone.** Every handler calls
`_require_demo_environment()` first, independently re-verifying
`RAILWAY_ENVIRONMENT_NAME`/`SUPABASE_URL` on every single request (not
just whether this router happens to be mounted) -- the same "checked
fresh on every call, never assumed from context" discipline
`app.demo.reset.assert_reset_is_safe` already established for the
destructive reset boundary, applied here to every demo route, read or
write. `app.main` additionally only mounts this router at all when
`RAILWAY_ENVIRONMENT_NAME == "demo"` (defense in depth, matching the
existing `/sentry-debug` dev-only conditional-mount convention) -- but
that mount-time check is deliberately not relied on as the only guard.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder

from app.demo import state
from app.demo.reset import DemoResetSafetyError, reset_demo_operational_data
from app.demo.runner import ScenarioRunnerError
from app.demo.scenarios import list_bundled_scenarios, load_bundled_scenario
from app.environment_safety import DemoIsolationError, assert_demo_isolation
from app.internal_auth import require_internal_token
from app.persistence.daily_game_intelligence import DailyGameIntelligenceError, read_daily_game_intelligence
from app.persistence.games import GamesQueryError, list_games_in_window

router = APIRouter(
    prefix="/internal/demo",
    tags=["demo"],
    dependencies=[Depends(require_internal_token)],
)

#: Wide enough to contain any bundled scenario's own scripted dates
#: (which are fixed calendar dates chosen at authoring time, not relative
#: to whenever this route happens to be called) without needing this
#: module to know a specific scenario's date range.
_GAMES_WINDOW_DAYS = 730


def _require_demo_environment() -> None:
    try:
        assert_demo_isolation(
            railway_environment_name=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev"),
            supabase_url=os.environ.get("SUPABASE_URL", ""),
        )
    except DemoIsolationError as exc:
        raise HTTPException(status_code=403, detail=f"refusing: not the isolated demo environment ({exc})") from exc


def _status_payload(runner) -> dict:
    return {
        "scenario_id": runner.scenario.scenario_id if runner.scenario else None,
        "title": runner.scenario.title if runner.scenario else None,
        "status": runner.status,
        "virtual_now": runner.virtual_now,
        "step_index": runner.step_index,
        "total_steps": len(runner.scenario.steps) if runner.scenario else 0,
        "is_finished": runner.is_finished,
        "outcomes": runner.outcomes,
        "checkpoints": runner.checkpoints,
        "errors": runner.errors,
    }


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    _require_demo_environment()
    return list_bundled_scenarios()


@router.get("/status")
def get_status() -> dict:
    _require_demo_environment()
    return jsonable_encoder(_status_payload(state.get_runner()))


@router.post("/scenarios/{name}/load")
def load_scenario_route(name: str) -> dict:
    _require_demo_environment()
    try:
        scenario = load_bundled_scenario(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    runner = state.get_runner()
    runner.load(scenario)
    return jsonable_encoder(_status_payload(runner))


@router.post("/step")
async def step() -> dict:
    _require_demo_environment()
    runner = state.get_runner()
    try:
        await runner.run_next_step()
    except ScenarioRunnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jsonable_encoder(_status_payload(runner))


@router.post("/run-to-checkpoint")
async def run_to_checkpoint() -> dict:
    _require_demo_environment()
    runner = state.get_runner()
    try:
        await runner.run_until_checkpoint()
    except ScenarioRunnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jsonable_encoder(_status_payload(runner))


@router.post("/run")
async def run_to_completion() -> dict:
    _require_demo_environment()
    runner = state.get_runner()
    try:
        await runner.run_to_completion()
    except ScenarioRunnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jsonable_encoder(_status_payload(runner))


@router.post("/reset")
async def reset() -> dict:
    """The one route on this router that reaches `app.demo.reset` --
    which independently re-checks isolation a SECOND time at its own
    boundary (Decision 4/DEMO-3's "do not rely only on the existing
    startup guard"), on top of this handler's own `_require_demo_environment()`
    call above. Two guards, neither trusting the other."""
    _require_demo_environment()
    railway_environment_name = os.environ.get("RAILWAY_ENVIRONMENT_NAME", "dev")
    supabase_url = os.environ.get("SUPABASE_URL", "")
    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        try:
            deleted_counts = await reset_demo_operational_data(
                client, state.auth_headers(),
                railway_environment_name=railway_environment_name,
                supabase_url=supabase_url,
            )
        except DemoResetSafetyError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    state.discard_runner()
    return {"reset": True, "deleted_counts": deleted_counts}


@router.get("/games")
async def list_active_games() -> list[dict]:
    _require_demo_environment()
    today = date.today()
    async with httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=10.0) as client:
        try:
            games = await list_games_in_window(
                client, state.auth_headers(),
                start=today - timedelta(days=_GAMES_WINDOW_DAYS),
                end=today + timedelta(days=_GAMES_WINDOW_DAYS),
            )
        except GamesQueryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return games


@router.get("/games/{game_id}/intelligence")
async def get_game_intelligence(game_id: str) -> dict:
    _require_demo_environment()
    async with httpx.AsyncClient(base_url=os.environ["SUPABASE_URL"], timeout=10.0) as client:
        try:
            dgi = await read_daily_game_intelligence(client, state.auth_headers(), game_id=game_id)
        except DailyGameIntelligenceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if dgi is None:
        raise HTTPException(status_code=404, detail=f"no daily_game_intelligence row for game {game_id}")
    return dgi
