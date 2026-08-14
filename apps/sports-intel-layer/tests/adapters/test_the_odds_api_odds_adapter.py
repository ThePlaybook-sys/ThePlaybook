"""Scenario tests for TheOddsApiOddsAdapter / TheOddsApiPlayerPropsAdapter
(Phase 3B, fixture-first strategy approved 2026-08-11 -- see PROGRESS.md).

Every scenario Mac's approved plan named is covered here: multi-game,
moneyline/h2h, spreads, totals, player props, multiple sportsbooks,
missing/suspended markets, line movement, malformed data, 401, 429,
provider outage/timeouts, partial data, and cache/staleness (the last one
reuses 3A's already-built CachingAdapter/InMemoryCacheBackend, exercised
here against the real adapter instead of a fake).

All HTTP is intercepted by respx -- the adapter under test is the real,
production-shaped adapter, never a simplified stand-in.
"""
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
from app.adapters.models import AdapterResponse, OddsLine
from app.adapters.providers.the_odds_api import (
    TheOddsApiOddsAdapter,
    TheOddsApiPlayerPropsAdapter,
)
from tests.adapters.the_odds_api_fixtures import load

BASE_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{BASE_URL}/v4/sports/americanfootball_nfl/odds"

GAME_CHIEFS_RAVENS = "e912304de2b25f2879b0293fd6a48ef4"
GAME_COWBOYS_EAGLES = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
GAME_49ERS_BILLS = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL)


def _odds_adapter() -> TheOddsApiOddsAdapter:
    return TheOddsApiOddsAdapter(client=_client(), api_key="test-key")


def _props_adapter() -> TheOddsApiPlayerPropsAdapter:
    return TheOddsApiPlayerPropsAdapter(client=_client(), api_key="test-key")


# ---------------------------------------------------------------------------
# Multi-game, moneyline/h2h, spreads, totals, multiple sportsbooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_multi_game_multi_sportsbook_normalization():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds(
        [GAME_CHIEFS_RAVENS, GAME_COWBOYS_EAGLES, GAME_49ERS_BILLS]
    )

    assert isinstance(response, AdapterResponse)
    assert response.source == "the_odds_api"
    assert response.from_cache is False

    games_seen = {line.game_external_id for line in response.value}
    assert games_seen == {GAME_CHIEFS_RAVENS, GAME_COWBOYS_EAGLES, GAME_49ERS_BILLS}

    books_seen = {line.sportsbook for line in response.value}
    assert books_seen == {"draftkings", "fanduel", "betmgm"}

    market_types_seen = {line.market_type for line in response.value}
    assert market_types_seen == {"moneyline", "spread", "total"}

    chiefs_dk_h2h = next(
        line
        for line in response.value
        if line.game_external_id == GAME_CHIEFS_RAVENS
        and line.sportsbook == "draftkings"
        and line.market_type == "moneyline"
    )
    assert chiefs_dk_h2h.line_data["outcomes"][0]["price"] == -150

    # provider_reported_at reflects the latest bookmaker/market last_update
    # seen in the response, never fabricated.
    assert response.provider_reported_at is not None


@pytest.mark.asyncio
@respx.mock
async def test_home_away_team_and_commence_time_populated_from_event():
    """Phase 3E-4B: OddsLine carries the event's own home_team/away_team/
    commence_time -- the game-identity information the deterministic
    game-linking module (3E-4C) needs, previously discarded during parsing."""
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])

    line = response.value[0]
    assert line.home_team == "Kansas City Chiefs"
    assert line.away_team == "Baltimore Ravens"
    assert line.commence_time.isoformat() == "2026-09-14T17:00:00+00:00"


@pytest.mark.asyncio
@respx.mock
async def test_empty_game_external_ids_returns_every_event_unfiltered():
    """Phase 3E-4B/C discovery mode: a caller that doesn't yet know any
    The Odds API event ids (e.g. before the first deterministic-linking
    pass for newly Master-Refresh-created games) gets the full slate back,
    since the bulk endpoint always returns everything regardless of filter
    and costs the same either way."""
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds([])

    games_seen = {line.game_external_id for line in response.value}
    assert games_seen == {GAME_CHIEFS_RAVENS, GAME_COWBOYS_EAGLES, GAME_49ERS_BILLS}


@pytest.mark.asyncio
@respx.mock
async def test_only_requested_games_are_returned():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])
    assert {line.game_external_id for line in response.value} == {GAME_CHIEFS_RAVENS}


# ---------------------------------------------------------------------------
# Missing / suspended markets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_suspended_market_produces_no_lines_but_does_not_crash():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_missing_suspended_markets.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])

    # draftkings has one live market; betmgm's empty `markets: []` (suspended)
    # contributes nothing but doesn't raise.
    assert len(response.value) == 1
    assert response.value[0].sportsbook == "draftkings"


# ---------------------------------------------------------------------------
# Partial data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_partial_data_when_provider_omits_a_requested_game():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_partial_data.json"))
    )
    adapter = _odds_adapter()
    response = await adapter.fetch_odds([GAME_CHIEFS_RAVENS, GAME_COWBOYS_EAGLES])

    # Only the game the provider actually returned shows up -- no error,
    # no fabricated line for the missing one.
    assert {line.game_external_id for line in response.value} == {GAME_COWBOYS_EAGLES}


# ---------------------------------------------------------------------------
# Line movement between successive responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_line_movement_between_successive_calls():
    route = respx.get(ODDS_URL)
    route.side_effect = [
        httpx.Response(200, json=load("bulk_odds_line_movement_t1.json")),
        httpx.Response(200, json=load("bulk_odds_line_movement_t2.json")),
    ]
    adapter = _odds_adapter()

    first = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])
    second = await adapter.fetch_odds([GAME_CHIEFS_RAVENS])

    first_spread = first.value[0]
    second_spread = second.value[0]
    assert first_spread.line_data["outcomes"][0]["point"] == -3.0
    assert second_spread.line_data["outcomes"][0]["point"] == -3.5
    assert first.provider_reported_at < second.provider_reported_at


# ---------------------------------------------------------------------------
# Malformed payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_malformed_payload_raises_provider_data_error_not_a_crash():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("malformed_payload.json"))
    )
    adapter = _odds_adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_provider_data_error():
    respx.get(ODDS_URL).mock(return_value=httpx.Response(200, text="not json"))
    adapter = _odds_adapter()
    with pytest.raises(ProviderDataError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


# ---------------------------------------------------------------------------
# Auth failure / rate limiting / outage — real ProviderError subclasses,
# never a raw httpx/vendor exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_provider_auth_error():
    respx.get(ODDS_URL).mock(return_value=httpx.Response(401, json=load("error_401.json")))
    adapter = _odds_adapter()
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


@pytest.mark.asyncio
@respx.mock
async def test_429_raises_provider_rate_limit_error():
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(
            429, json=load("error_429.json"), headers={"Retry-After": "30"}
        )
    )
    adapter = _odds_adapter()
    with pytest.raises(ProviderRateLimitError) as exc_info:
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])
    assert exc_info.value.retry_after_seconds == 30.0


@pytest.mark.asyncio
@respx.mock
async def test_5xx_raises_provider_unavailable_error():
    respx.get(ODDS_URL).mock(return_value=httpx.Response(503, text="Service Unavailable"))
    adapter = _odds_adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


@pytest.mark.asyncio
@respx.mock
async def test_timeout_raises_provider_unavailable_error_not_httpx_exception():
    respx.get(ODDS_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    adapter = _odds_adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_unavailable_error():
    respx.get(ODDS_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    adapter = _odds_adapter()
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_odds([GAME_CHIEFS_RAVENS])


# ---------------------------------------------------------------------------
# Player props
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_player_props_multi_sportsbook_grouping():
    event_url = f"{BASE_URL}/v4/sports/americanfootball_nfl/events/{GAME_CHIEFS_RAVENS}/odds"
    respx.get(event_url).mock(
        return_value=httpx.Response(200, json=load("player_props_event.json"))
    )
    adapter = _props_adapter()
    response = await adapter.fetch_player_props([GAME_CHIEFS_RAVENS])

    assert response.source == "the_odds_api"
    books = {prop.sportsbook for prop in response.value}
    assert books == {"draftkings", "fanduel"}

    dk_mahomes_tds = next(
        p
        for p in response.value
        if p.sportsbook == "draftkings" and p.prop_type == "player_pass_tds"
    )
    assert dk_mahomes_tds.player_name == "Patrick Mahomes"
    assert dk_mahomes_tds.line == 2.5
    assert dk_mahomes_tds.over_odds == -120
    assert dk_mahomes_tds.under_odds == 100

    fd_kelce_receptions = next(
        p for p in response.value if p.player_name == "Travis Kelce"
    )
    assert fd_kelce_receptions.over_odds == -110

    # Phase 3E-4B: every prop from this event carries the same game-identity
    # fields the deterministic game-linking module needs.
    assert dk_mahomes_tds.home_team == "Kansas City Chiefs"
    assert dk_mahomes_tds.away_team == "Baltimore Ravens"
    assert dk_mahomes_tds.commence_time.isoformat() == "2026-09-14T17:00:00+00:00"
    assert fd_kelce_receptions.under_odds == -110


@pytest.mark.asyncio
@respx.mock
async def test_player_props_missing_market_produces_no_props_not_a_crash():
    event_url = f"{BASE_URL}/v4/sports/americanfootball_nfl/events/{GAME_49ERS_BILLS}/odds"
    respx.get(event_url).mock(
        return_value=httpx.Response(200, json=load("player_props_missing_market.json"))
    )
    adapter = _props_adapter()
    response = await adapter.fetch_player_props([GAME_49ERS_BILLS])
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_player_props_calls_once_per_game_matching_confirmed_cost_model():
    """CONFIRMED (2026-08-10 credit research): the event-specific endpoint is
    billed per game, per call -- this test proves the adapter actually issues
    one call per game rather than accidentally batching or re-fetching."""
    route_a = respx.get(
        f"{BASE_URL}/v4/sports/americanfootball_nfl/events/{GAME_CHIEFS_RAVENS}/odds"
    ).mock(return_value=httpx.Response(200, json=load("player_props_event.json")))
    route_b = respx.get(
        f"{BASE_URL}/v4/sports/americanfootball_nfl/events/{GAME_49ERS_BILLS}/odds"
    ).mock(return_value=httpx.Response(200, json=load("player_props_missing_market.json")))

    adapter = _props_adapter()
    await adapter.fetch_player_props([GAME_CHIEFS_RAVENS, GAME_49ERS_BILLS])

    assert route_a.call_count == 1
    assert route_b.call_count == 1


# ---------------------------------------------------------------------------
# Cache / staleness behavior — reuses 3A's CachingAdapter/InMemoryCacheBackend
# against the real adapter (not a fake), proving the boundary already built
# in Phase 3A works unchanged for a real vendor implementation.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_avoids_a_second_http_call():
    route = respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=30)

    first = await caching.call(
        "fetch_odds", [GAME_CHIEFS_RAVENS], response_model=AdapterResponse[list[OddsLine]]
    )
    second = await caching.call(
        "fetch_odds", [GAME_CHIEFS_RAVENS], response_model=AdapterResponse[list[OddsLine]]
    )

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True


@pytest.mark.asyncio
@respx.mock
async def test_cache_expiry_triggers_a_fresh_call():
    route = respx.get(ODDS_URL).mock(
        return_value=httpx.Response(200, json=load("bulk_odds_multi_game.json"))
    )
    adapter = _odds_adapter()
    clock = {"t": 0.0}
    backend = InMemoryCacheBackend(clock=lambda: clock["t"])
    caching = CachingAdapter(adapter, backend, ttl_seconds=30)

    await caching.call(
        "fetch_odds", [GAME_CHIEFS_RAVENS], response_model=AdapterResponse[list[OddsLine]]
    )
    clock["t"] += 31  # past the TTL — odds data needs near-real-time freshness (Volume 2 §8)
    third = await caching.call(
        "fetch_odds", [GAME_CHIEFS_RAVENS], response_model=AdapterResponse[list[OddsLine]]
    )

    assert route.call_count == 2
    assert third.from_cache is False
