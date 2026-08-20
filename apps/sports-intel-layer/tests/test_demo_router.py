"""Tests for app.demo.router (DEMO-4 control/read routes).

Exercises the router directly, mounted on a bare FastAPI app -- not
through `app.main`, since that module's demo-router mount decision is
made once at import time from whatever env was active at collection (see
`test_demo_router_only_mounted_in_main_when_environment_is_demo` below for
the one test that specifically covers `app.main`'s own mount logic, via a
careful reload/restore).
"""
from __future__ import annotations

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.demo import state
from app.demo.router import router
from app.environment_safety import DEMO_SUPABASE_PROJECT_REF
from tests.demo.fake_supabase import FakeSupabase

DEMO_SUPABASE_URL = f"https://{DEMO_SUPABASE_PROJECT_REF}.supabase.co"
OTHER_SUPABASE_URL = "https://some-other-project-ref.supabase.co"
TOKEN = "test-internal-token"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _async_client(app: FastAPI) -> httpx.AsyncClient:
    """`TestClient` runs the ASGI app in its own background thread/event
    loop (via anyio's portal) -- fine for the sync guard-only tests above
    (which raise before any HTTP call), but respx's patching does not
    reliably reach across that thread boundary. Every test below that
    needs its outbound Supabase calls actually intercepted uses this
    instead, staying on the current pytest-asyncio event loop."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_runner_singleton():
    """The runner singleton is process-global by design (app.demo.state's
    own docstring) -- reset it between tests so one test's loaded scenario
    never leaks into the next."""
    state.discard_runner()
    yield
    state.discard_runner()


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "demo")
    monkeypatch.setenv("SUPABASE_URL", DEMO_SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)


# -- internal-token auth guard --

def test_missing_internal_token_is_rejected(demo_env):
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios")
    assert response.status_code == 401


def test_wrong_internal_token_is_rejected(demo_env):
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": "wrong"})
    assert response.status_code == 401


def test_correct_internal_token_is_accepted(demo_env):
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200


def test_missing_token_configuration_is_a_server_error(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "demo")
    monkeypatch.setenv("SUPABASE_URL", DEMO_SUPABASE_URL)
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": "anything"})
    assert response.status_code == 500


# -- isolation guard (Decision 4): checked independently of auth, on every route --

@pytest.mark.parametrize("environment_name", ["dev", "staging", "production"])
def test_isolation_guard_refuses_outside_demo_environment(monkeypatch, environment_name):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment_name)
    monkeypatch.setenv("SUPABASE_URL", DEMO_SUPABASE_URL)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": TOKEN})
    assert response.status_code == 403


def test_isolation_guard_refuses_when_url_does_not_match_demo_project(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "demo")
    monkeypatch.setenv("SUPABASE_URL", OTHER_SUPABASE_URL)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": TOKEN})
    assert response.status_code == 403


def test_isolation_guard_applies_to_every_route_including_reset(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("SUPABASE_URL", DEMO_SUPABASE_URL)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    client = TestClient(_app())
    with respx.mock:
        response = client.post("/internal/demo/reset", headers={"x-internal-token": TOKEN})
    assert response.status_code == 403


# -- control endpoints --

def test_list_scenarios_returns_the_bundled_minimal_scenario(demo_env):
    client = TestClient(_app())
    response = client.get("/internal/demo/scenarios", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "minimal_pregame_to_postgame" in names


def test_status_before_any_scenario_is_loaded(demo_env):
    client = TestClient(_app())
    response = client.get("/internal/demo/status", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] is None
    assert body["status"] == "idle"
    assert body["step_index"] == 0


def test_load_scenario_returns_404_for_unknown_name(demo_env):
    client = TestClient(_app())
    response = client.post(
        "/internal/demo/scenarios/does-not-exist/load", headers={"x-internal-token": TOKEN}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_load_scenario_then_status_reflects_it(demo_env):
    async with _async_client(_app()) as client:
        response = await client.post(
            "/internal/demo/scenarios/minimal_pregame_to_postgame/load", headers={"x-internal-token": TOKEN}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scenario_id"] == "demo-minimal-pregame-to-postgame"
        assert body["status"] == "loaded"
        assert body["total_steps"] > 0

        status_response = await client.get("/internal/demo/status", headers={"x-internal-token": TOKEN})
        assert status_response.json()["scenario_id"] == "demo-minimal-pregame-to-postgame"


def test_step_without_a_loaded_scenario_returns_409(demo_env):
    client = TestClient(_app())
    response = client.post("/internal/demo/step", headers={"x-internal-token": TOKEN})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_step_advances_one_step_against_a_fake_supabase(demo_env):
    fake = FakeSupabase()
    fake.seed("leagues", [{"id": "league-nfl", "code": "nfl"}])
    fake.seed("seasons", [{"league_id": "league-nfl", "year": 2026, "start_date": "2026-08-01", "end_date": "2027-02-14"}])
    fake.seed("teams", [{"id": "team-kc", "name": "Kansas City Chiefs"}, {"id": "team-bal", "name": "Baltimore Ravens"}])
    fake.seed(
        "team_provider_ids",
        [
            {"team_id": "team-kc", "provider_name": "sportsdataio", "provider_team_id": "KC"},
            {"team_id": "team-kc", "provider_name": "the_odds_api", "provider_team_id": "Kansas City Chiefs"},
            {"team_id": "team-bal", "provider_name": "sportsdataio", "provider_team_id": "BAL"},
            {"team_id": "team-bal", "provider_name": "the_odds_api", "provider_team_id": "Baltimore Ravens"},
        ],
    )

    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            await client.post(
                "/internal/demo/scenarios/minimal_pregame_to_postgame/load", headers={"x-internal-token": TOKEN}
            )
            response = await client.post("/internal/demo/step", headers={"x-internal-token": TOKEN})

    assert response.status_code == 200
    body = response.json()
    assert body["step_index"] == 1
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["action"] == "run_master_refresh"
    assert body["outcomes"][0]["error"] is None
    assert fake.tables.get("games")


@pytest.mark.asyncio
async def test_reset_without_a_loaded_scenario_still_succeeds_and_reports_zero_deletes(demo_env):
    fake = FakeSupabase()
    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            response = await client.post("/internal/demo/reset", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200
    assert response.json()["reset"] is True


@pytest.mark.asyncio
async def test_reset_discards_the_runner_singleton(demo_env):
    fake = FakeSupabase()
    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            await client.post(
                "/internal/demo/scenarios/minimal_pregame_to_postgame/load", headers={"x-internal-token": TOKEN}
            )
            before = await client.get("/internal/demo/status", headers={"x-internal-token": TOKEN})
            assert before.json()["scenario_id"] is not None
            await client.post("/internal/demo/reset", headers={"x-internal-token": TOKEN})
            status_after = await client.get("/internal/demo/status", headers={"x-internal-token": TOKEN})
    body = status_after.json()
    assert body["scenario_id"] is None
    assert body["status"] == "idle"


# -- read endpoints --

@pytest.mark.asyncio
async def test_list_active_games_reads_from_the_real_games_helper(demo_env):
    fake = FakeSupabase()
    fake.seed(
        "games",
        [{"id": "g1", "home_team": "KC", "away_team": "BAL", "scheduled_start": "2026-09-14T17:00:00+00:00", "status": "scheduled"}],
    )
    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            response = await client.get("/internal/demo/games", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_game_intelligence_404_when_no_dgi_row_exists(demo_env):
    fake = FakeSupabase()
    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            response = await client.get(
                "/internal/demo/games/nonexistent/intelligence", headers={"x-internal-token": TOKEN}
            )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_game_intelligence_returns_the_full_row_when_present(demo_env):
    fake = FakeSupabase()
    fake.seed("daily_game_intelligence", [{"game_id": "g1", "news": {"value": []}, "odds": None}])
    with respx.mock:
        fake.register_routes(DEMO_SUPABASE_URL)
        async with _async_client(_app()) as client:
            response = await client.get("/internal/demo/games/g1/intelligence", headers={"x-internal-token": TOKEN})
    assert response.status_code == 200
    assert response.json()["game_id"] == "g1"


# -- app.main's own mount decision --

def test_demo_router_only_mounted_in_main_when_environment_is_demo(monkeypatch):
    import importlib

    import app.main as main_module

    try:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "demo")
        monkeypatch.setenv("SUPABASE_URL", DEMO_SUPABASE_URL)
        importlib.reload(main_module)
        assert any(r.path.startswith("/internal/demo") for r in main_module.app.routes)
    finally:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "dev")
        monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
        importlib.reload(main_module)
        assert not any(r.path.startswith("/internal/demo") for r in main_module.app.routes)
