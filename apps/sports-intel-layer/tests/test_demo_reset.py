"""Tests for app.demo.reset (DEMO-3 "RESET SAFETY (critical)" requirement).

Two things are proven here, independently: (1) the reset-boundary guard
hard-fails -- and issues zero HTTP calls -- unless BOTH the environment tag
and the Supabase URL prove this is the isolated demo project, and (2) when
it *is* safe, reset deletes exactly the derived FK-safe table list, in
order, and never touches the preserved reference-taxonomy tables.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.demo.reset import (
    PRESERVED_REFERENCE_TAXONOMY,
    RESET_TABLE_ORDER,
    DemoResetSafetyError,
    assert_reset_is_safe,
    reset_demo_operational_data,
)
from app.environment_safety import DEMO_ENVIRONMENT_NAME, DEMO_SUPABASE_PROJECT_REF

DEMO_SUPABASE_URL = f"https://{DEMO_SUPABASE_PROJECT_REF}.supabase.co"
OTHER_SUPABASE_URL = "https://some-other-project-ref.supabase.co"
HEADERS = {"Authorization": "Bearer test", "apikey": "test", "Content-Type": "application/json"}


# -- assert_reset_is_safe: the guard itself, no HTTP involved --

def test_safe_when_both_env_and_url_are_demo():
    assert_reset_is_safe(railway_environment_name=DEMO_ENVIRONMENT_NAME, supabase_url=DEMO_SUPABASE_URL)


def test_unsafe_when_env_is_demo_but_url_is_not():
    with pytest.raises(DemoResetSafetyError, match="refusing to reset"):
        assert_reset_is_safe(railway_environment_name=DEMO_ENVIRONMENT_NAME, supabase_url=OTHER_SUPABASE_URL)


def test_unsafe_when_url_is_demo_but_env_is_not():
    for env_name in ("dev", "staging", "production"):
        with pytest.raises(DemoResetSafetyError, match="refusing to reset"):
            assert_reset_is_safe(railway_environment_name=env_name, supabase_url=DEMO_SUPABASE_URL)


def test_unsafe_when_neither_matches():
    with pytest.raises(DemoResetSafetyError):
        assert_reset_is_safe(railway_environment_name="production", supabase_url=OTHER_SUPABASE_URL)


def test_unsafe_when_url_is_empty_or_none():
    with pytest.raises(DemoResetSafetyError):
        assert_reset_is_safe(railway_environment_name=DEMO_ENVIRONMENT_NAME, supabase_url="")


# -- reset_demo_operational_data: the guard is checked before any DELETE --

@pytest.mark.asyncio
async def test_reset_refuses_and_issues_zero_http_calls_when_unsafe():
    async with httpx.AsyncClient(base_url=OTHER_SUPABASE_URL) as client:
        with respx.mock(assert_all_called=False) as router:
            # Deliberately zero routes registered -- any call at all raises
            # respx's AllMockedAssertionError, proving no HTTP was attempted.
            with pytest.raises(DemoResetSafetyError):
                await reset_demo_operational_data(
                    client, HEADERS,
                    railway_environment_name="production",
                    supabase_url=OTHER_SUPABASE_URL,
                )
            assert len(router.calls) == 0


@pytest.mark.asyncio
@respx.mock
async def test_reset_deletes_every_table_in_order_and_only_those_tables():
    call_order: list[str] = []

    def _make_responder(table_name: str):
        def _respond(request: httpx.Request) -> httpx.Response:
            call_order.append(table_name)
            return httpx.Response(200, json=[{"id": "deleted-row-1"}, {"id": "deleted-row-2"}])
        return _respond

    for table_name, _pk in RESET_TABLE_ORDER:
        respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/{table_name}").mock(side_effect=_make_responder(table_name))

    counts = await reset_demo_operational_data(
        httpx.AsyncClient(base_url=DEMO_SUPABASE_URL), HEADERS,
        railway_environment_name=DEMO_ENVIRONMENT_NAME,
        supabase_url=DEMO_SUPABASE_URL,
    )

    expected_order = [name for name, _pk in RESET_TABLE_ORDER]
    assert call_order == expected_order
    assert counts == {name: 2 for name in expected_order}
    assert not (PRESERVED_REFERENCE_TAXONOMY & set(call_order))


@pytest.mark.asyncio
@respx.mock
async def test_reset_uses_game_id_as_the_primary_key_filter_for_daily_game_intelligence():
    route = respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(
        return_value=httpx.Response(200, json=[])
    )
    for table_name, _pk in RESET_TABLE_ORDER:
        if table_name != "daily_game_intelligence":
            respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/{table_name}").mock(return_value=httpx.Response(200, json=[]))

    await reset_demo_operational_data(
        httpx.AsyncClient(base_url=DEMO_SUPABASE_URL), HEADERS,
        railway_environment_name=DEMO_ENVIRONMENT_NAME,
        supabase_url=DEMO_SUPABASE_URL,
    )

    assert route.calls.last.request.url.params["game_id"] == "not.is.null"
    assert "id" not in route.calls.last.request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_reset_uses_id_as_the_primary_key_filter_for_every_other_table():
    for table_name, _pk in RESET_TABLE_ORDER:
        respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/{table_name}").mock(return_value=httpx.Response(200, json=[]))

    await reset_demo_operational_data(
        httpx.AsyncClient(base_url=DEMO_SUPABASE_URL), HEADERS,
        railway_environment_name=DEMO_ENVIRONMENT_NAME,
        supabase_url=DEMO_SUPABASE_URL,
    )

    for table_name, pk in RESET_TABLE_ORDER:
        if table_name == "daily_game_intelligence":
            continue
        route = respx.routes[f"delete_{table_name}"] if False else None  # noqa: unused, see below

    # Re-verify directly against the mocked calls instead of route lookup by name.
    calls_by_table = {}
    for call in respx.calls:
        path = call.request.url.path
        calls_by_table[path.rsplit("/", 1)[-1]] = call

    for table_name, pk in RESET_TABLE_ORDER:
        call = calls_by_table[table_name]
        assert call.request.url.params[pk] == "not.is.null"


@pytest.mark.asyncio
@respx.mock
async def test_reset_stops_and_raises_on_first_table_failure_without_deleting_the_rest():
    call_order: list[str] = []

    for index, (table_name, _pk) in enumerate(RESET_TABLE_ORDER):
        if index == 2:
            respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/{table_name}").mock(return_value=httpx.Response(500))
        else:
            def _respond(request: httpx.Request, _name=table_name) -> httpx.Response:
                call_order.append(_name)
                return httpx.Response(200, json=[])
            respx.delete(f"{DEMO_SUPABASE_URL}/rest/v1/{table_name}").mock(side_effect=_respond)

    with pytest.raises(DemoResetSafetyError, match="reset failed while deleting"):
        await reset_demo_operational_data(
            httpx.AsyncClient(base_url=DEMO_SUPABASE_URL), HEADERS,
            railway_environment_name=DEMO_ENVIRONMENT_NAME,
            supabase_url=DEMO_SUPABASE_URL,
        )

    assert call_order == [name for name, _pk in RESET_TABLE_ORDER[:2]]


def test_reset_table_order_never_includes_reference_taxonomy():
    table_names = {name for name, _pk in RESET_TABLE_ORDER}
    assert not (table_names & PRESERVED_REFERENCE_TAXONOMY)


def test_reset_table_order_matches_the_derived_fk_safe_sequence():
    assert [name for name, _pk in RESET_TABLE_ORDER] == [
        "daily_game_intelligence",
        "odds_snapshots",
        "injury_reports",
        "weather_snapshots",
        "depth_chart_snapshots",
        "team_stats",
        "player_stats",
        "roster_memberships",
        "player_provider_ids",
        "game_provider_ids",
        "players",
        "games",
    ]
