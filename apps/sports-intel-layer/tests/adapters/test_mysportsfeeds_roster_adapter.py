"""Scenario tests for MySportsFeedsRosterAdapter (Phase 8.2 Player/
Roster/Depth Activation, 2026-09-08). Fixture shapes mirror the real
payload captured live by the Phase 8.2 diagnostics (`docs/ops/phase-8.2-
mysportsfeeds-players-diagnostic-2-2026-09-08.md`), not invented."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, RosterEntry
from app.adapters.providers.mysportsfeeds import MySportsFeedsRosterAdapter

BASE_URL = "https://api.mysportsfeeds.com/v2.1/pull"
PLAYERS_URL = f"{BASE_URL}/nfl/players.json"
RESPONSE_MODEL = AdapterResponse[list[RosterEntry]]

# Real shape, real values -- Hunter Henry (MSF id 9999, real, previously
# flagged and resolved in Phase 8.2 diagnostic #2), plus one SEA player
# and one player on an untracked team, all real field names/values as
# observed live.
_PLAYERS_NORMAL = {
    "lastUpdatedOn": "2026-09-08T14:49:00.000Z",
    "players": [
        {
            "player": {
                "id": 9999,
                "firstName": "Hunter",
                "lastName": "Henry",
                "primaryPosition": "TE",
                "alternatePositions": [],
                "jerseyNumber": 85,
                "currentTeam": {"id": 50, "abbreviation": "NE"},
                "currentRosterStatus": "ROSTER",
                "college": "Arkansas",
            },
            "teamAsOfDate": {"id": 50, "abbreviation": "NE"},
        },
        {
            "player": {
                "id": 39182,
                "firstName": "Chris",
                "lastName": "Paul Jr.",
                "primaryPosition": "ILB",
                "alternatePositions": [],
                "jerseyNumber": 49,
                "currentTeam": {"id": 79, "abbreviation": "SEA"},
                "currentRosterStatus": "ROSTER",
                "college": "Mississippi",
            },
            "teamAsOfDate": {"id": 79, "abbreviation": "SEA"},
        },
        {
            "player": {
                "id": 6826,
                "firstName": "Ameer",
                "lastName": "Abdullah",
                "primaryPosition": "RB",
                "alternatePositions": [],
                "jerseyNumber": 43,
                "currentTeam": {"id": 66, "abbreviation": "JAX"},
                "currentRosterStatus": "ROSTER",
                "college": "Nebraska",
            },
            "teamAsOfDate": {"id": 66, "abbreviation": "JAX"},
        },
    ],
    "references": {},
}

_PLAYERS_MALFORMED = {
    "lastUpdatedOn": "2026-09-08T14:49:00.000Z",
    "players": [
        {"player": {"id": 1, "currentTeam": {"abbreviation": "NE"}}},  # missing firstName/lastName/primaryPosition
    ],
    "references": {},
}


def _adapter() -> MySportsFeedsRosterAdapter:
    return MySportsFeedsRosterAdapter(client=httpx.AsyncClient(base_url=BASE_URL), api_key="test-key")


@pytest.mark.asyncio
@respx.mock
async def test_real_shape_filters_to_the_requested_team_and_never_sets_depth_rank():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    response = await _adapter().fetch_roster("NE")

    assert response.source == "mysportsfeeds"
    assert len(response.value) == 1
    henry = response.value[0]
    assert henry.player_external_id == "9999"
    assert henry.player_name == "Hunter Henry"
    assert henry.position == "TE"
    assert henry.team == "NE"
    # This feed carries no depth data -- never invented.
    assert henry.depth_chart_rank is None


@pytest.mark.asyncio
@respx.mock
async def test_a_different_team_filter_returns_a_different_real_player():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    response = await _adapter().fetch_roster("SEA")

    assert len(response.value) == 1
    assert response.value[0].player_external_id == "39182"
    assert response.value[0].player_name == "Chris Paul Jr."
    assert response.value[0].position == "ILB"


@pytest.mark.asyncio
@respx.mock
async def test_untracked_team_returns_empty_not_an_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    response = await _adapter().fetch_roster("ZZ")
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_provider_reported_at_parses_the_real_lastupdatedon_timestamp():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    response = await _adapter().fetch_roster("NE")
    assert response.provider_reported_at is not None
    assert response.provider_reported_at.year == 2026


@pytest.mark.asyncio
@respx.mock
async def test_malformed_row_is_isolated_not_fatal():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_MALFORMED))
    response = await _adapter().fetch_roster("NE")
    assert response.value == []  # the one row is malformed and skipped, not raised


@pytest.mark.asyncio
@respx.mock
async def test_force_param_sent_matching_real_sdk_default_behavior():
    route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    await _adapter().fetch_roster("NE")
    assert route.calls[0].request.url.params.get("force") == "false"


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, text="not json"))
    with pytest.raises(ProviderDataError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_missing_players_key_raises_provider_data_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json={"lastUpdatedOn": None}))
    with pytest.raises(ProviderDataError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderAuthError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(ProviderRateLimitError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderUnavailableError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_unavailable_error():
    respx.get(PLAYERS_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(ProviderUnavailableError):
        await _adapter().fetch_roster("NE")


@pytest.mark.asyncio
@respx.mock
async def test_basic_auth_header_matches_confirmed_sdk_scheme():
    import base64

    route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=_PLAYERS_NORMAL))
    await _adapter().fetch_roster("NE")
    expected = "Basic " + base64.b64encode(b"test-key:MYSPORTSFEEDS").decode()
    assert route.calls[0].request.headers["Authorization"] == expected
