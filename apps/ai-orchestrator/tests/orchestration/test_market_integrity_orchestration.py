"""Tests for app.orchestration.market_integrity (Milestone 7.1) -- the
per-game assessment orchestration: game/odds-history gating, evidence
gathering, and qualifying-event persistence, all against a mocked
PostgREST. Fixture-first, per this milestone's own explicit instruction
(DEV has no real correlatable odds/evidence history to validate against
-- Milestone 7.0's audit, reconfirmed unchanged 2026-09-04)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.orchestration.market_integrity import assess_game_market_integrity

SUPABASE_URL = "https://test-project.supabase.co"

_GAME = {
    "id": "game-1",
    "status": "scheduled",
    "home_team": "Buffalo Bills",
    "away_team": "Kansas City Chiefs",
    "final_score": None,
    "finalized_at": None,
}

_TEAMS = [{"id": "team-buf", "name": "Buffalo Bills"}, {"id": "team-kc", "name": "Kansas City Chiefs"}]


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _snapshot(sportsbook: str, market_type: str, outcomes: list[dict], captured_at: str) -> dict:
    return {"sportsbook": sportsbook, "market_type": market_type, "line_data": {"outcomes": outcomes}, "captured_at": captured_at}


def _mock_common(
    *,
    snapshots: list[dict],
    injury_reports: list[dict] | None = None,
    weather_snapshots: list[dict] | None = None,
    depth_chart_snapshots: list[dict] | None = None,
    news_articles: list[dict] | None = None,
    game: dict | None = None,
):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game or _GAME]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=snapshots))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=injury_reports or []))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=weather_snapshots or []))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=_TEAMS))
    respx.get(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(200, json=depth_chart_snapshots or []))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=news_articles or []))
    return respx.post(f"{SUPABASE_URL}/rest/v1/market_monitoring_events").mock(return_value=httpx.Response(201, json=[{"id": "mme-1"}]))


@pytest.mark.asyncio
@respx.mock
async def test_game_not_found_returns_named_status_not_an_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="missing")
    assert result.status == "game_not_found"
    assert result.assessments == []


@pytest.mark.asyncio
@respx.mock
async def test_no_odds_history_returns_named_status_not_an_error():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_GAME]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assert result.status == "no_odds_history"


@pytest.mark.asyncio
@respx.mock
async def test_normal_movement_produces_no_market_monitoring_events_write():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T10:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T14:00:00+00:00"),
    ]
    post_route = _mock_common(snapshots=snapshots)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assert result.status == "assessed"
    assert len(result.assessments) == 1
    assert result.assessments[0].classification.classification == "NORMAL"
    assert result.assessments[0].signal is None
    assert result.written_event_ids == []
    assert post_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_qualifying_movement_with_evidence_writes_explained_event():
    # -3.5 -> -6.0 is a 2.5-point move -- ELEVATED.
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T10:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -6.0}], "2026-09-20T14:00:00+00:00"),
    ]
    injury_reports = [{"id": "inj-1", "captured_at": "2026-09-20T12:00:00+00:00"}]
    post_route = _mock_common(snapshots=snapshots, injury_reports=injury_reports)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assert result.status == "assessed"
    assessment = result.assessments[0]
    assert assessment.classification.classification == "ELEVATED"
    assert assessment.signal == "EXPLAINED_MARKET_MOVEMENT"
    assert result.written_event_ids == ["mme-1"]
    assert post_route.call_count == 1
    payload = post_route.calls[0].request.content.decode()
    assert '"action_taken": "none"' in payload
    assert '"classification": "ELEVATED"' in payload


@pytest.mark.asyncio
@respx.mock
async def test_qualifying_movement_with_no_evidence_writes_unexplained_event():
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T10:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -6.0}], "2026-09-20T14:00:00+00:00"),
    ]
    post_route = _mock_common(snapshots=snapshots)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assessment = result.assessments[0]
    assert assessment.signal == "UNEXPLAINED_MARKET_MOVEMENT"
    assert post_route.call_count == 1
    payload = post_route.calls[0].request.content.decode()
    assert '"signal": "UNEXPLAINED_MARKET_MOVEMENT"' in payload


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_team_name_degrades_safely_not_fatal():
    # A team name with no `teams` row match -- lineup/news evidence for
    # that team is simply unavailable, never a crash or a fabricated match.
    snapshots = [
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T10:00:00+00:00"),
        _snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -6.0}], "2026-09-20T14:00:00+00:00"),
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[_GAME]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=snapshots))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=[]))  # nothing resolves
    respx.get(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/market_monitoring_events").mock(return_value=httpx.Response(201, json=[{"id": "mme-1"}]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assert result.status == "assessed"
    assert result.assessments[0].signal == "UNEXPLAINED_MARKET_MOVEMENT"


@pytest.mark.asyncio
@respx.mock
async def test_insufficient_history_group_produces_no_write():
    snapshots = [_snapshot("DraftKings", "spread", [{"name": "Buffalo Bills", "price": -150, "point": -3.5}], "2026-09-20T10:00:00+00:00")]
    post_route = _mock_common(snapshots=snapshots)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await assess_game_market_integrity(client, _headers(), game_id="game-1")
    assert result.assessments[0].classification.classification == "INSUFFICIENT_HISTORY"
    assert result.assessments[0].signal is None
    assert post_route.call_count == 0
