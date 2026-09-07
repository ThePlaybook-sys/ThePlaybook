"""Scenario tests for BallDontLieInjuryAdapter (Phase 8.0.5, Data
Activation Pass 1, 2026-09-07)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, InjuryReport
from app.adapters.providers.balldontlie import BallDontLieInjuryAdapter

BASE_URL = "https://api.balldontlie.io"
INJURIES_URL = f"{BASE_URL}/nfl/v1/player_injuries"
RESPONSE_MODEL = AdapterResponse[list[InjuryReport]]

_INJURIES_NORMAL = {
    "data": [
        {
            "player": {
                "id": 501,
                "first_name": "Sam",
                "last_name": "Example",
                "position": "WR",
                "team": {"id": 31, "abbreviation": "SEA", "full_name": "Seattle Seahawks"},
            },
            "status": "Questionable",
            "comment": "Ankle",
            "date": "2026-09-06",
        },
        {
            "player": {
                "id": 502,
                "first_name": "Alex",
                "last_name": "Sample",
                "position": "LB",
                "team": {"id": 1, "abbreviation": "NE", "full_name": "New England Patriots"},
            },
            "status": "Out",
            "comment": None,
            "date": "2026-09-06",
        },
    ],
    "meta": {"per_page": 100},
}

_INJURIES_UNMAPPED_TEAM = {
    "data": [
        {
            "player": {
                "id": 900,
                "first_name": "Bye",
                "last_name": "Week",
                "position": "RB",
                "team": {"id": 999, "abbreviation": "ZZ", "full_name": "Not Tracked This Cycle"},
            },
            "status": "Out",
            "comment": None,
            "date": "2026-09-06",
        }
    ],
}

_INJURIES_MALFORMED = {"data": [{"status": "Out"}]}  # missing "player" entirely


def _game_resolver(mapping: dict[int, str]):
    return lambda team_id: mapping.get(team_id)


def _adapter(*, team_ids: list[int], resolver) -> BallDontLieInjuryAdapter:
    return BallDontLieInjuryAdapter(
        client=httpx.AsyncClient(base_url=BASE_URL),
        api_key="test-key",
        team_ids=team_ids,
        game_external_id_for_team_id=resolver,
    )


@pytest.mark.asyncio
@respx.mock
async def test_real_rows_map_to_the_correct_game_via_injected_resolver():
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, json=_INJURIES_NORMAL))
    adapter = _adapter(team_ids=[31, 1], resolver=_game_resolver({31: "game-sea-ne", 1: "game-sea-ne"}))
    response = await adapter.fetch_injuries()

    assert response.source == "balldontlie"
    assert len(response.value) == 2
    assert {r.game_external_id for r in response.value} == {"game-sea-ne"}
    seahawks_report = next(r for r in response.value if r.team == "SEA")
    assert seahawks_report.player_name == "Sam Example"
    assert seahawks_report.status == "Questionable"
    assert seahawks_report.description == "Ankle"


@pytest.mark.asyncio
@respx.mock
async def test_team_with_no_resolvable_game_is_dropped_not_guessed():
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, json=_INJURIES_UNMAPPED_TEAM))
    adapter = _adapter(team_ids=[999], resolver=_game_resolver({}))
    response = await adapter.fetch_injuries()
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_malformed_row_is_isolated_not_fatal():
    combined = {"data": _INJURIES_NORMAL["data"] + _INJURIES_MALFORMED["data"]}
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, json=combined))
    adapter = _adapter(team_ids=[31, 1], resolver=_game_resolver({31: "game-sea-ne", 1: "game-sea-ne"}))
    response = await adapter.fetch_injuries()
    # The 2 well-formed rows survive; the malformed one is skipped, logged.
    assert len(response.value) == 2


@pytest.mark.asyncio
@respx.mock
async def test_team_ids_sent_as_list_params():
    route = respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    adapter = _adapter(team_ids=[31, 1], resolver=_game_resolver({}))
    await adapter.fetch_injuries()
    request = route.calls[0].request
    assert request.url.params.get_list("team_ids[]") == ["31", "1"]


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, text="not json"))
    adapter = _adapter(team_ids=[31], resolver=_game_resolver({}))
    with pytest.raises(ProviderDataError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(401))
    adapter = _adapter(team_ids=[31], resolver=_game_resolver({}))
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    # CONFIRMED: BALLDONTLIE's real 5 requests/minute limit (2026-09-03 bake-off).
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(429))
    adapter = _adapter(team_ids=[31], resolver=_game_resolver({}))
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(INJURIES_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter(team_ids=[31], resolver=_game_resolver({}))
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_unavailable_error():
    respx.get(INJURIES_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    adapter = _adapter(team_ids=[31], resolver=_game_resolver({}))
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_avoids_a_second_http_call():
    route = respx.get(INJURIES_URL).mock(return_value=httpx.Response(200, json=_INJURIES_NORMAL))
    adapter = _adapter(team_ids=[31, 1], resolver=_game_resolver({31: "game-sea-ne", 1: "game-sea-ne"}))
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=900)

    first = await caching.call("fetch_injuries", response_model=RESPONSE_MODEL)
    second = await caching.call("fetch_injuries", response_model=RESPONSE_MODEL)

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True
