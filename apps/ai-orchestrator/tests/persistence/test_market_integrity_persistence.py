"""Tests for app.persistence.market_integrity (Milestone 7.1), proven
against a mocked PostgREST -- same discipline as
test_postgame_grading_persistence.py."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.persistence.market_integrity import (
    MarketIntegrityReadError,
    MarketIntegrityWriteError,
    read_depth_chart_snapshots,
    read_injury_reports,
    read_news_article_history_for_teams,
    read_weather_snapshots,
    resolve_team_ids_by_name,
    write_market_monitoring_event,
)

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_read_injury_reports_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(
        return_value=httpx.Response(200, json=[{"id": "inj-1", "captured_at": "2026-09-20T10:00:00+00:00"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_injury_reports(client, _headers(), game_id="game-1")
    assert rows == [{"id": "inj-1", "captured_at": "2026-09-20T10:00:00+00:00"}]


@pytest.mark.asyncio
@respx.mock
async def test_read_injury_reports_raises_on_non_200():
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MarketIntegrityReadError):
            await read_injury_reports(client, _headers(), game_id="game-1")


@pytest.mark.asyncio
@respx.mock
async def test_read_weather_snapshots_returns_rows():
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "w-1", "captured_at": "2026-09-20T10:00:00+00:00"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_weather_snapshots(client, _headers(), game_id="game-1")
    assert rows == [{"id": "w-1", "captured_at": "2026-09-20T10:00:00+00:00"}]


@pytest.mark.asyncio
@respx.mock
async def test_resolve_team_ids_by_name_maps_names_to_ids():
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(
        return_value=httpx.Response(200, json=[{"id": "team-1", "name": "Buffalo Bills"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_team_ids_by_name(client, _headers(), team_names=["Buffalo Bills", "Kansas City Chiefs"])
    # Kansas City Chiefs absent -- unresolved, not fabricated
    assert result == {"Buffalo Bills": "team-1"}


@pytest.mark.asyncio
async def test_resolve_team_ids_by_name_empty_input_makes_no_request():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await resolve_team_ids_by_name(client, _headers(), team_names=[])
    assert result == {}


@pytest.mark.asyncio
@respx.mock
async def test_read_depth_chart_snapshots_filters_by_team_ids():
    route = respx.get(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "dc-1", "team_id": "team-1", "captured_at": "2026-09-20T09:00:00+00:00"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_depth_chart_snapshots(client, _headers(), team_ids=["team-1"])
    assert rows[0]["id"] == "dc-1"
    assert route.calls[0].request.url.params["team_id"] == "in.(team-1)"


@pytest.mark.asyncio
async def test_read_depth_chart_snapshots_empty_team_ids_makes_no_request():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_depth_chart_snapshots(client, _headers(), team_ids=[])
    assert rows == []


@pytest.mark.asyncio
@respx.mock
async def test_read_news_article_history_for_teams_filters_by_related_team_ids():
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "n-1", "related_team_ids": ["team-1"], "ingested_at": "2026-09-20T09:00:00+00:00"},
                {"id": "n-2", "related_team_ids": ["team-9"], "ingested_at": "2026-09-20T09:00:00+00:00"},
                {"id": "n-3", "related_team_ids": None, "ingested_at": "2026-09-20T09:00:00+00:00"},
            ],
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_news_article_history_for_teams(client, _headers(), team_ids=["team-1"])
    assert [r["id"] for r in rows] == ["n-1"]


@pytest.mark.asyncio
async def test_read_news_article_history_for_teams_empty_team_ids_makes_no_request():
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        rows = await read_news_article_history_for_teams(client, _headers(), team_ids=[])
    assert rows == []


@pytest.mark.asyncio
@respx.mock
async def test_write_market_monitoring_event_inserts_and_returns_id():
    post_route = respx.post(f"{SUPABASE_URL}/rest/v1/market_monitoring_events").mock(
        return_value=httpx.Response(201, json=[{"id": "mme-1"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        event_id = await write_market_monitoring_event(
            client, _headers(), game_id="game-1", event_type="line_movement", event_data={"classification": "WATCH"}
        )
    assert event_id == "mme-1"
    body = post_route.calls[0].request.content
    assert b'"action_taken": "none"' in body


@pytest.mark.asyncio
@respx.mock
async def test_write_market_monitoring_event_raises_on_failure():
    respx.post(f"{SUPABASE_URL}/rest/v1/market_monitoring_events").mock(return_value=httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(MarketIntegrityWriteError):
            await write_market_monitoring_event(
                client, _headers(), game_id="game-1", event_type="line_movement", event_data={}
            )
