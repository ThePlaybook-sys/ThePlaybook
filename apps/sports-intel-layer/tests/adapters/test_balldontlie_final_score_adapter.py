"""BallDontLieFinalScoreAdapter (2026-09-18).

The payload below is not invented. It is the real shape of the 2026-09-11
`nfl/v1/games` response persisted in dev's `game_events` (provider
`balldontlie`, `seasons[]=2026`, `weeks[]=1`, HTTP 200, 16 games) -- the same
capture that proves 2026 support, the score fields, and the three
`status_state` values. Three of its real rows are reproduced verbatim,
including the one that matters most: SF @ LAR carrying a genuine 3-0 while
still `in_progress`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.providers.balldontlie import BallDontLieFinalScoreAdapter

BASE = "https://api.balldontlie.io"
GAMES_URL = f"{BASE}/nfl/v1/games"


def _row(**overrides) -> dict:
    row = {
        "id": 1392216,
        "date": "2026-09-10T00:20:00.000Z",
        "season": 2026,
        "week": 1,
        "postseason": False,
        "status": "Final",
        "status_state": "final",
        "summary": None,
        "venue": "Lumen Field",
        "home_team": {"id": 31, "abbreviation": "SEA"},
        "visitor_team": {"id": 1, "abbreviation": "NE"},
        "home_team_score": 13,
        "visitor_team_score": 10,
        "home_team_q1": 3,
        "visitor_team_q1": 0,
        "home_team_ot": None,
        "visitor_team_ot": None,
    }
    row.update(overrides)
    return row


REAL_ROWS = [
    _row(),  # final
    _row(
        id=1392217,
        date="2026-09-11T00:35:00.000Z",
        status="1:31 - 1st",
        status_state="in_progress",
        home_team={"id": 14, "abbreviation": "LAR"},
        visitor_team={"id": 25, "abbreviation": "SF"},
        home_team_score=0,
        visitor_team_score=3,
    ),
    _row(
        id=1392219,
        date="2026-09-13T17:00:00.000Z",
        status="9/13 - 1:00 PM EDT",
        status_state="scheduled",
        home_team={"id": 8, "abbreviation": "DET"},
        visitor_team={"id": 24, "abbreviation": "NO"},
        home_team_score=None,
        visitor_team_score=None,
    ),
]


def _body(rows=None, meta=None) -> dict:
    return {"data": rows if rows is not None else REAL_ROWS, "meta": meta or {"per_page": 25}}


async def _fetch(**kwargs):
    async with httpx.AsyncClient(base_url=BASE) as client:
        adapter = BallDontLieFinalScoreAdapter(client=client, api_key="test-key")
        return await adapter.fetch_week_final_scores(season=2026, week=1, **kwargs)


@pytest.mark.asyncio
@respx.mock
async def test_parses_the_real_captured_payload():
    respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=_body()))
    response = await _fetch()

    assert len(response.value) == 3
    final, in_progress, scheduled = response.value

    assert final.is_final is True
    assert (final.home_team, final.away_team) == ("SEA", "NE")
    assert (final.home_score, final.away_score) == (13, 10)
    assert final.scheduled_start == datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
    assert final.provider_game_id == "1392216"

    # The safety case, from real captured data.
    assert in_progress.is_final is False
    assert (in_progress.home_score, in_progress.away_score) == (0, 3)
    assert in_progress.provider_status == "1:31 - 1st"

    assert scheduled.is_final is False
    assert scheduled.home_score is None


@pytest.mark.asyncio
@respx.mock
async def test_is_final_branches_on_status_state_not_the_display_string():
    """`status` is a human string and must never gate a write."""
    rows = [_row(status="Final/OT", status_state="final"), _row(id=2, status="Final", status_state="in_progress")]
    respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=_body(rows)))
    lines = (await _fetch()).value

    assert lines[0].is_final is True
    assert lines[1].is_final is False


@pytest.mark.asyncio
@respx.mock
async def test_quarter_splits_are_never_summed_into_a_score():
    """A final game whose whole-game score is null stays null, even though
    quarter fields are present -- the bake-off recorded quarter nulls on real
    Final games, so summing them invents results."""
    rows = [_row(home_team_score=None, visitor_team_score=None, home_team_q1=7, visitor_team_q1=3)]
    respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=_body(rows)))
    line = (await _fetch()).value[0]

    assert line.is_final is True
    assert line.home_score is None and line.away_score is None


@pytest.mark.asyncio
@respx.mock
async def test_request_is_bulk_by_season_and_week():
    route = respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=_body()))
    await _fetch()

    params = route.calls[0].request.url.params
    assert params.get_list("seasons[]") == ["2026"]
    assert params.get_list("weeks[]") == ["1"]
    assert params["per_page"] == "100"
    assert route.calls[0].request.headers["Authorization"] == "test-key"


@pytest.mark.asyncio
@respx.mock
async def test_unexpected_pagination_refuses_a_partial_week():
    """Silently returning 25 of 32 games would read to a caller as "these are
    all the games in this week"."""
    respx.get(GAMES_URL).mock(
        return_value=httpx.Response(200, json=_body(meta={"per_page": 100, "next_cursor": 26}))
    )
    with pytest.raises(ProviderDataError, match="paginated unexpectedly"):
        await _fetch()


@pytest.mark.asyncio
@respx.mock
async def test_malformed_row_is_skipped_not_fatal():
    rows = [{"id": 9, "date": "2026-09-10T00:20:00.000Z"}, _row()]
    respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=_body(rows)))
    lines = (await _fetch()).value

    assert len(lines) == 1
    assert lines[0].provider_game_id == "1392216"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "status,exc",
    [
        (401, ProviderAuthError),
        (429, ProviderRateLimitError),
        (503, ProviderUnavailableError),
        (418, ProviderDataError),
    ],
)
async def test_http_failures_map_to_typed_provider_errors(status, exc):
    respx.get(GAMES_URL).mock(return_value=httpx.Response(status, json={}))
    with pytest.raises(exc):
        await _fetch()


@pytest.mark.asyncio
@respx.mock
async def test_non_object_body_is_a_data_error_not_a_crash():
    respx.get(GAMES_URL).mock(return_value=httpx.Response(200, json=[1, 2, 3]))
    with pytest.raises(ProviderDataError):
        await _fetch()
