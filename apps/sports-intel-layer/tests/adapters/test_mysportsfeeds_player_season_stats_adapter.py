"""Tests for MySportsFeedsPlayerSeasonStatsAdapter (Phase 8.3D, 2026-09-08).

Every test uses the real, committed Phase 8.3C fixture
(`docs/ops/fixtures/phase-8.3c-msf-player-stats-totals-ne-2025-2026-
partial-2026-09-08.json`) as the respx-mocked response body -- NO live
MySportsFeeds calls, per HQ's explicit "no external provider call"
instruction for this pass. The fixture is real, confirmed-live data
(HTTP 200, team=NE, season=2025-2026-regular, 43 real player entries),
not synthetic -- these tests prove the adapter correctly parses the
exact real shape MySportsFeeds actually returned.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.providers.mysportsfeeds import MySportsFeedsPlayerSeasonStatsAdapter

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "ops"
    / "fixtures"
    / "phase-8.3c-msf-player-stats-totals-ne-2025-2026-partial-2026-09-08.json"
)

MSF_BASE_URL = "https://api.mysportsfeeds.com/v2.1/pull"
SEASON = "2025-2026-regular"
TEAM = "NE"


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=MSF_BASE_URL, timeout=5.0)


@pytest.mark.asyncio
@respx.mock
async def test_parses_the_real_fixture_into_player_season_stat_lines():
    fixture = _load_fixture()
    route = respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, json=fixture)
    )

    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        result = await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)

    assert route.call_count == 1
    assert result.source == "mysportsfeeds"
    # Real fixture count -- 43 complete player entries recovered in Phase 8.3C.
    assert len(result.value) == 43

    julian_ashby = next(line for line in result.value if line.player == "166956")
    assert julian_ashby.stats["gamesPlayed"] == 17
    assert "snapCounts" in julian_ashby.stats
    assert "miscellaneous" in julian_ashby.stats

    # Not every real player entry carries every category (e.g. a long
    # snapper's real payload has no 'passing' block) -- confirmed only
    # for players who actually have it, never assumed universal.
    joshua_dobbs = next(line for line in result.value if line.player == "13191")
    assert "passing" in joshua_dobbs.stats
    assert joshua_dobbs.stats["passing"]["passAttempts"] == 10


@pytest.mark.asyncio
@respx.mock
async def test_sends_the_real_team_and_season_scoped_request():
    fixture = _load_fixture()
    route = respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, json=fixture)
    )

    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)

    request = route.calls.last.request
    assert request.url.params["team"] == TEAM
    assert "Authorization" in request.headers


@pytest.mark.asyncio
@respx.mock
async def test_stats_dict_is_preserved_verbatim_not_reshaped():
    """The whole point of the provider-neutral contract: this adapter
    must not rename, drop, or reinterpret any field -- including
    gamesStarted, which HQ's directive explicitly requires be preserved
    raw, never treated as trustworthy."""
    fixture = _load_fixture()
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, json=fixture)
    )

    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        result = await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)

    hunter_henry = next(line for line in result.value if line.player == "9999")
    source_entry = next(e for e in fixture["playerStatsTotals"] if e["player"]["id"] == 9999)
    assert hunter_henry.stats == source_entry["stats"]
    assert hunter_henry.stats["miscellaneous"]["gamesStarted"] == 0
    assert hunter_henry.stats["receiving"]["receptions"] == 60


@pytest.mark.asyncio
@respx.mock
async def test_lastupdatedon_becomes_provider_reported_at():
    fixture = _load_fixture()
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, json=fixture)
    )

    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        result = await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)

    assert result.provider_reported_at is not None
    assert result.provider_reported_at.year == 2026


@pytest.mark.asyncio
@respx.mock
async def test_malformed_row_is_skipped_not_guessed():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "lastUpdatedOn": "2026-09-08T17:58:23.195Z",
                "playerStatsTotals": [
                    {"player": {"id": 1}, "stats": {"gamesPlayed": 5}},
                    {"player": {}, "stats": {"gamesPlayed": 1}},  # missing id -- malformed
                    {"player": {"id": 2}, "stats": "not-a-dict"},  # malformed stats
                ],
            },
        )
    )

    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        result = await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)

    assert len(result.value) == 1
    assert result.value[0].player == "1"


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(return_value=httpx.Response(401))
    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="bad-key")
        with pytest.raises(ProviderAuthError):
            await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(return_value=httpx.Response(429))
    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        with pytest.raises(ProviderRateLimitError):
            await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(return_value=httpx.Response(503))
    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        with pytest.raises(ProviderUnavailableError):
            await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)


@pytest.mark.asyncio
@respx.mock
async def test_unexpected_shape_raises_provider_data_error():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        with pytest.raises(ProviderDataError):
            await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_raises_provider_data_error():
    respx.get(f"{MSF_BASE_URL}/nfl/{SEASON}/player_stats_totals.json").mock(
        return_value=httpx.Response(200, content=b"not json")
    )
    async with _client() as client:
        adapter = MySportsFeedsPlayerSeasonStatsAdapter(client=client, api_key="test-key")
        with pytest.raises(ProviderDataError):
            await adapter.fetch_player_season_stats(team=TEAM, season=SEASON)
