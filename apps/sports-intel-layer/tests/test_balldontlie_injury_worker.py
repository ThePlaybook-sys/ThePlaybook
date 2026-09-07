"""Orchestration tests for app.workers.balldontlie_injury_worker (Phase
8.0.5, Data Activation Pass 1, 2026-09-07).

Every HTTP boundary -- Supabase and BALLDONTLIE both -- is respx-mocked;
zero real network. Covers: end-to-end real-shape resolution (candidate
game -> balldontlie game link -> team links -> injuries fetch ->
persistence), games with no balldontlie link excluded, teams with no
balldontlie mapping excluded, empty candidate window, and a genuine
provider failure.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.workers.balldontlie_injury_worker import run_balldontlie_injury_worker

SUPABASE_URL = "https://test-project.supabase.co"
BALLDONTLIE_URL = "https://api.balldontlie.io"
INJURIES_URL = f"{BALLDONTLIE_URL}/nfl/v1/player_injuries"

GAME_SEA_NE = "game-sea-ne"
GAME_LV_MIA = "game-lv-mia"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _game_row(*, game_id: str, home: str, away: str) -> dict:
    return {
        "id": game_id,
        "home_team": home,
        "away_team": away,
        "scheduled_start": "2026-09-13T20:25:00Z",
        "week": 1,
    }


def _mock_games(games: list[dict]):
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))


def _mock_game_provider_ids(linked: dict[str, str]):
    """linked: internal game_id -> balldontlie provider_game_id. Serves
    both directions real callers use against this table: this worker's
    own reverse lookup (filtered by `game_id`) and `persist_injury_reports`'
    forward lookup, via `resolve_game_ids` (filtered by
    `provider_game_id`)."""

    def _respond(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if "game_id" in params:
            requested = params["game_id"].removeprefix("in.(").removesuffix(")").split(",")
            rows = [{"game_id": gid, "provider_game_id": pid} for gid, pid in linked.items() if gid in requested]
        else:
            requested = params["provider_game_id"].removeprefix("in.(").removesuffix(")").split(",")
            rows = [{"game_id": gid, "provider_game_id": pid} for gid, pid in linked.items() if pid in requested]
        return httpx.Response(200, json=rows)

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_respond)


def _mock_team_provider_ids(sportsdataio: dict[str, str], balldontlie: dict[str, str]):
    """sportsdataio: abbreviation -> internal team_id. balldontlie:
    internal team_id -> balldontlie numeric id (as a string)."""

    def _respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        if provider_name == "eq.sportsdataio":
            requested = request.url.params["provider_team_id"].removeprefix("in.(").removesuffix(")").split(",")
            rows = [{"team_id": tid, "provider_team_id": abbr} for abbr, tid in sportsdataio.items() if abbr in requested]
            return httpx.Response(200, json=rows)
        if provider_name == "eq.balldontlie":
            requested = request.url.params["team_id"].removeprefix("in.(").removesuffix(")").split(",")
            rows = [{"team_id": tid, "provider_team_id": bid} for tid, bid in balldontlie.items() if tid in requested]
            return httpx.Response(200, json=rows)
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_respond)


def _injuries_response(rows: list[dict]) -> dict:
    return {"data": rows}


def _injury_row(*, player_id: int, first: str, last: str, team_id: int, abbrev: str, status: str) -> dict:
    return {
        "player": {
            "id": player_id,
            "first_name": first,
            "last_name": last,
            "position": "WR",
            "team": {"id": team_id, "abbreviation": abbrev, "full_name": abbrev},
        },
        "status": status,
        "comment": None,
        "date": "2026-09-06",
    }


async def _run(monkeypatch) -> "run_balldontlie_injury_worker":
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(
        base_url=BALLDONTLIE_URL
    ) as balldontlie_client:
        return await run_balldontlie_injury_worker(
            supabase_client=supabase_client,
            balldontlie_client=balldontlie_client,
            balldontlie_api_key="test-key",
        )


@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_real_shape_resolution_and_persistence(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=GAME_SEA_NE, home="SEA", away="NE")])
    _mock_game_provider_ids({GAME_SEA_NE: "1392216"})
    _mock_team_provider_ids(
        sportsdataio={"SEA": "team-sea", "NE": "team-ne"},
        balldontlie={"team-sea": "31", "team-ne": "1"},
    )
    injuries_route = respx.get(INJURIES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_injuries_response(
                [
                    _injury_row(player_id=501, first="Sam", last="Example", team_id=31, abbrev="SEA", status="Questionable"),
                    _injury_row(player_id=502, first="Alex", last="Sample", team_id=1, abbrev="NE", status="Out"),
                ]
            ),
        )
    )
    persist_route = respx.post(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(201))

    result = await _run(monkeypatch)

    assert result.status == "success"
    assert result.games_considered == 1
    assert result.games_linked == 1
    assert result.teams_resolved == 2
    assert result.reports_fetched == 2
    assert result.reports_persisted == 2
    assert injuries_route.called
    assert persist_route.called
    # team_ids[] sent to BALLDONTLIE reflects both real resolved teams.
    sent_team_ids = set(injuries_route.calls[0].request.url.params.get_list("team_ids[]"))
    assert sent_team_ids == {"31", "1"}


@pytest.mark.asyncio
@respx.mock
async def test_game_with_no_balldontlie_link_is_excluded(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=GAME_SEA_NE, home="SEA", away="NE")])
    _mock_game_provider_ids({})  # no real link yet for this game
    result = await _run(monkeypatch)
    assert result.status == "success"
    assert result.games_considered == 1
    assert result.games_linked == 0


@pytest.mark.asyncio
@respx.mock
async def test_team_with_no_balldontlie_mapping_is_excluded(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=GAME_SEA_NE, home="SEA", away="NE")])
    _mock_game_provider_ids({GAME_SEA_NE: "1392216"})
    # sportsdataio resolves both teams, but neither has a balldontlie row.
    _mock_team_provider_ids(sportsdataio={"SEA": "team-sea", "NE": "team-ne"}, balldontlie={})
    result = await _run(monkeypatch)
    assert result.status == "success"
    assert result.games_linked == 1
    assert result.teams_resolved == 0


@pytest.mark.asyncio
@respx.mock
async def test_empty_candidate_window(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([])
    result = await _run(monkeypatch)
    assert result.status == "success"
    assert result.games_considered == 0


@pytest.mark.asyncio
@respx.mock
async def test_provider_failure_is_reported_not_raised(monkeypatch):
    _headers_env(monkeypatch)
    _mock_games([_game_row(game_id=GAME_SEA_NE, home="SEA", away="NE")])
    _mock_game_provider_ids({GAME_SEA_NE: "1392216"})
    _mock_team_provider_ids(sportsdataio={"SEA": "team-sea", "NE": "team-ne"}, balldontlie={"team-sea": "31", "team-ne": "1"})
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(503))

    result = await _run(monkeypatch)
    assert result.status == "failed"
    assert result.error is not None
