"""End-to-end test for app.context_intelligence.engine.
build_contextual_intelligence (Phase 8.1 Foundation Pass) -- every real
Supabase boundary respx-mocked, matching this package's own established
convention. Proves the full 10-dimension result shape assembles
correctly from real I/O, not just from the pure per-dimension functions
already covered by their own dedicated test files."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.context_intelligence.context_package import assemble_context_package
from app.context_intelligence.engine import SUPPORTED_DIMENSIONS, build_contextual_intelligence
from app.context_intelligence.unsupported import UNSUPPORTED_DIMENSIONS

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _mock_all_empty():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.asyncio
@respx.mock
async def test_result_always_covers_all_ten_dimensions_even_with_zero_real_data():
    _mock_all_empty()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")

    expected = set(SUPPORTED_DIMENSIONS) | set(UNSUPPORTED_DIMENSIONS)
    assert set(result.dimensions.keys()) == expected
    assert result.game_id == "g1"
    # Every supported dimension is honestly insufficient-evidence when
    # nothing real exists for this game.
    for name in SUPPORTED_DIMENSIONS:
        assert result.dimensions[name].insufficient_evidence is True
    # Every unsupported dimension is present too -- never silently omitted.
    for name in UNSUPPORTED_DIMENSIONS:
        assert result.dimensions[name].insufficient_evidence is True


@pytest.mark.asyncio
@respx.mock
async def test_result_serializes_to_json_cleanly():
    _mock_all_empty()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")
    payload = result.to_json()
    assert payload["game_id"] == "g1"
    assert set(payload["dimensions"].keys()) == set(SUPPORTED_DIMENSIONS) | set(UNSUPPORTED_DIMENSIONS)
    assert isinstance(payload["dimensions"]["weather"]["confounders"], list)


@pytest.mark.asyncio
@respx.mock
async def test_missing_weather_still_produces_full_result_for_other_dimensions():
    """A real game with real odds history but zero weather rows must
    still produce a complete result -- weather insufficient, market
    still computed from what's real."""
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "g1", "home_team": "SEA", "away_team": "NE", "venue_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "game_id": "g1",
                    "sportsbook": "draftkings",
                    "market_type": "spread",
                    "line_data": {"outcomes": [{"name": "Home", "point": 3.0, "price": -110}]},
                    "captured_at": "2026-09-07T00:00:00Z",
                },
                {
                    "game_id": "g1",
                    "sportsbook": "draftkings",
                    "market_type": "spread",
                    "line_data": {"outcomes": [{"name": "Home", "point": 1.0, "price": -110}]},
                    "captured_at": "2026-09-08T00:00:00Z",
                },
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(
        return_value=httpx.Response(200, json=[{"id": "t1", "name": "SEA"}, {"id": "t2", "name": "NE"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")

    assert result.dimensions["weather"].insufficient_evidence is True
    assert result.dimensions["venue"].insufficient_evidence is True  # no venue_id resolved
    # Market has real target history -- not a crash, a real (if
    # sample-limited) result reflecting genuinely zero comparable games.
    assert result.dimensions["market"].facts != {}


# --------------------------------------------------------------------------
# player_performance -- real engine registration proof (Player Performance
# Engine Integration pass, 2026-09-15). Every Supabase boundary this
# dimension touches is respx-mocked with the exact real DEV values queried
# 2026-09-15 for the JSN/SEA@NE proof (player_stats, games, players,
# game_events, team_provider_ids, teams) -- the same values
# test_player_performance.py's own real-proof class uses, run here through
# the ACTUAL engine entry point instead of calling the compute functions
# directly.
# --------------------------------------------------------------------------

JSN_PLAYER_ID = "c9b7de10-b380-45e4-90a3-f98444dce258"
SEA_NE_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
SEATTLE_TEAM_ID = "3ca09e7e-f92a-4fc8-9ba2-3c3144d58207"
NEW_ENGLAND_TEAM_ID = "918a529e-f9e7-4bf5-8957-de5f39af5ad2"

JSN_STATS = {
    "receiving": {"recTD": 1, "recLng": 45, "targets": 11, "recYards": 122, "rec20Plus": 2, "rec40Plus": 1, "recAverage": 15.2, "recFumbles": 0, "receptions": 8, "rec1stDowns": 5},
    "_unreliable_fields": ["snapCounts"],
    "_unreliable_fields_reason": "test: snapCounts flagged unreliable by source pipeline",
}

JSN_SEA_NE_RAW_ROWS = [
    {
        "id": "4026f70f-5b08-483d-88ba-c6a6bb07f07c",
        "player_id": JSN_PLAYER_ID,
        "game_id": SEA_NE_GAME_ID,
        "created_at": "2026-09-10T20:38:42.113431+00:00",
        "stats": {**JSN_STATS, "snapCounts": {"offenseSnaps": 0}},
    },
    {
        "id": "4ee8eae8-e213-4533-b099-3945d0d3fd41",
        "player_id": JSN_PLAYER_ID,
        "game_id": SEA_NE_GAME_ID,
        "created_at": "2026-09-14T23:02:03.657231+00:00",
        "stats": {**JSN_STATS, "snapCounts": {"offenseSnaps": 45}},
    },
]

SEA_NE_RAW_GAME_EVENT_PAYLOAD = {
    "body": {"game": {"id": 163541, "homeTeam": {"id": 79, "abbreviation": "SEA"}, "awayTeam": {"id": 50, "abbreviation": "NE"}}}
}

PROOF_NOW = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)


def _games_route(request: httpx.Request) -> httpx.Response:
    """Real `/rest/v1/games` gets two structurally different calls in the
    same engine run (`read_game_venue_context`'s single `id=eq.` lookup
    vs. `read_games_by_ids`'s batch `id=in.` lookup) -- routed by
    inspecting the real query param respx hands the callback, exactly the
    two shapes those two functions really send."""
    id_param = request.url.params.get("id", "")
    if id_param.startswith("eq."):
        return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "venue_id": None}])
    return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"}])


def _teams_route(request: httpx.Request) -> httpx.Response:
    """Real `/rest/v1/teams` gets two structurally different calls
    (`resolve_team_ids_by_name`'s news-dimension `name=in.` lookup vs.
    `read_team_provider_ids`'s identity-chain `id=in.` lookup)."""
    if "name" in request.url.params:
        return httpx.Response(200, json=[])
    return httpx.Response(200, json=[{"id": SEATTLE_TEAM_ID, "name": "Seattle Seahawks"}, {"id": NEW_ENGLAND_TEAM_ID, "name": "New England Patriots"}])


def _mock_jsn_sea_ne_player_performance_boundaries():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(side_effect=_teams_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(200, json=[{"id": JSN_PLAYER_ID, "name": "Jaxon Smith-Njigba", "position": "WR", "team_id": SEATTLE_TEAM_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=JSN_SEA_NE_RAW_ROWS))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(200, json=[{"game_id": SEA_NE_GAME_ID, "raw_payload": SEA_NE_RAW_GAME_EVENT_PAYLOAD}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": SEATTLE_TEAM_ID, "provider_team_id": "79"},
                {"team_id": NEW_ENGLAND_TEAM_ID, "provider_team_id": "50"},
            ],
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_player_performance_is_a_registered_supported_dimension():
    assert "player_performance" in SUPPORTED_DIMENSIONS
    assert "player_performance" not in UNSUPPORTED_DIMENSIONS


@pytest.mark.asyncio
@respx.mock
async def test_no_player_id_never_triggers_the_new_reads():
    """The cost/boundary guarantee: a caller that never asks about a
    player pays zero extra cost -- no player_stats/players/game_events/
    team_provider_ids call fires at all. Deliberately NOT mocking any of
    those four endpoints: respx raises its own unmocked-request error if
    the engine ever calls one, which is itself part of this proof."""
    _mock_all_empty()
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(client, _headers(), game_id="g1")
    assert result.dimensions["player_performance"].data_completeness == "unavailable"
    assert result.dimensions["player_performance"].insufficient_evidence is True


@pytest.mark.asyncio
@respx.mock
async def test_jsn_sea_ne_real_engine_proof():
    """Directive Section 4 -- run JSN/SEA@NE through the ACTUAL engine
    path (`build_contextual_intelligence`, not the compute functions
    directly) and prove every required fact."""
    _mock_jsn_sea_ne_player_performance_boundaries()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(
            client, _headers(), game_id=SEA_NE_GAME_ID, player_id=JSN_PLAYER_ID, now=PROOF_NOW,
        )

    dim = result.dimensions["player_performance"]

    # player_performance as supported
    assert "player_performance" in SUPPORTED_DIMENSIONS
    assert dim.dimension == "player_performance"

    # exactly one game observation
    assert dim.sample_size == 1
    assert dim.facts["game_count"] == 1
    observations = dim.facts["observations"]
    assert len(observations) == 1
    obs = observations[0]
    assert obs["game_id"] == SEA_NE_GAME_ID

    # 11 targets, 8 receptions, 122 receiving yards, 1 receiving TD
    assert obs["role_usage_signals"]["receiving"] == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}

    # resolved opponent identity (real provider-identity chain, not text matching)
    assert obs["opponent"] == "New England Patriots"
    assert obs["home_or_away"] == "home"

    # correct provenance
    assert obs["provenance"][0]["table"] == "player_stats"
    assert obs["provenance"][0]["row_count"] == 2  # both real rows disclosed

    # no duplicate inflation
    assert dim.sample_size == 1  # not 2, despite 2 real raw rows
    assert obs["duplicate_raw_row_count"] == 2
    assert obs["canonical_row_id"] == "4ee8eae8-e213-4533-b099-3945d0d3fd41"

    # honest point-in-time limitation
    from app.context_intelligence.player_performance import PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION
    assert PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION in obs["reliability_limitations"]

    # data_completeness separate from confidence
    assert dim.data_completeness == "joined"
    assert dim.confidence is None
    assert dim.insufficient_evidence is True  # honest: one game, below the trend floor


@pytest.mark.asyncio
@respx.mock
async def test_engine_accepts_multiple_distinct_games_as_separate_observations():
    """Directive Section 5 -- multi-game architecture proof. SYNTHETIC
    fixtures (a second invented game alongside the real SEA@NE row) used
    ONLY to prove the engine's own wiring accepts >1 real-shaped game
    correctly; not presented as real MANSA evidence (no such second real
    game exists yet -- see the 2026-09-15 readiness reassessment)."""
    second_game_id = "synthetic-game-2"
    rows = JSN_SEA_NE_RAW_ROWS + [
        {
            "id": "synthetic-row-2",
            "player_id": JSN_PLAYER_ID,
            "game_id": second_game_id,
            "created_at": "2026-09-13T20:00:00+00:00",
            "stats": {"receiving": {"targets": 6, "receptions": 4, "recYards": 50, "recTD": 0}},
        }
    ]

    def _games_route_multi(request: httpx.Request) -> httpx.Response:
        id_param = request.url.params.get("id", "")
        if id_param.startswith("eq."):
            return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "home_team": "SEA", "away_team": "NE", "scheduled_start": "2026-09-10T00:20:00+00:00", "venue_id": None}])
        return httpx.Response(
            200,
            json=[
                {"id": SEA_NE_GAME_ID, "scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"},
                {"id": second_game_id, "scheduled_start": "2026-09-13T17:00:00+00:00", "home_team": "SEA", "away_team": "DEN"},
            ],
        )

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_route_multi)
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(side_effect=_teams_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(200, json=[{"id": JSN_PLAYER_ID, "name": "Jaxon Smith-Njigba", "position": "WR", "team_id": SEATTLE_TEAM_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=rows))
    # No real game_events/team_provider_ids row for the synthetic second game -- opponent stays
    # honestly unresolved for it, proving the engine doesn't require full identity resolution to
    # still return a correct, separate observation.
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(200, json=[{"game_id": SEA_NE_GAME_ID, "raw_payload": SEA_NE_RAW_GAME_EVENT_PAYLOAD}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": SEATTLE_TEAM_ID, "provider_team_id": "79"},
                {"team_id": NEW_ENGLAND_TEAM_ID, "provider_team_id": "50"},
            ],
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await build_contextual_intelligence(
            client, _headers(), game_id=SEA_NE_GAME_ID, player_id=JSN_PLAYER_ID, now=PROOF_NOW,
        )

    dim = result.dimensions["player_performance"]
    assert dim.sample_size == 2  # two distinct real-shaped games -> two observations
    observations = dim.facts["observations"]
    assert [obs["game_id"] for obs in observations] == [SEA_NE_GAME_ID, second_game_id]
    # The SEA@NE observation still correctly collapses its own two correction rows.
    assert observations[0]["duplicate_raw_row_count"] == 2
    assert observations[1]["duplicate_raw_row_count"] == 1
    # Crossing the sample floor with 2 real-shaped games flips insufficient_evidence off.
    assert dim.insufficient_evidence is False


# --------------------------------------------------------------------------
# Full real historical Context Package proof (Historical Context Assembly
# V1 pass, 2026-09-15) -- JSN / SEA@NE, every dimension. Every value below
# is real, queried live against DEV on 2026-09-15: the real venue
# (Lumen Field, 0 other real games sharing it), the real weather
# observation for SEA@NE plus its one real same-dome-bucket comparable
# (PHI@WAS), and real opening/closing spread lines for SEA@NE plus two
# real comparable games (LV@MIA, LAC@ARI) -- a genuine but reduced real
# sample (2 games, not all 4-5 real comparables SQL confirmed exist) that
# already crosses the same INSUFFICIENT_SAMPLE_FLOOR=2 the full real
# dataset also crosses, so the classification this proves (market =
# JOINED) matches what the full real table would also produce.
# --------------------------------------------------------------------------

SEA_NE_VENUE_ID = "ebe8bbcc-23b4-453e-98d9-8b7eee1e0dc3"

SEA_NE_WEATHER_ROW = {
    "game_id": SEA_NE_GAME_ID,
    "weather_data": {"source": "weatherapi", "is_dome": False, "wind_mph": 0.9, "conditions": "Overcast", "observed_at": "2026-09-09T23:00:00+00:00", "temperature_f": 63.1, "precipitation_pct": 15.0},
    "captured_at": "2026-09-07T23:10:25.507456+00:00",
}
PHI_WAS_GAME_ID = "cd0f612b-6ff3-48c3-b9ef-55da1ac38226"
PHI_WAS_WEATHER_ROW = {
    "game_id": PHI_WAS_GAME_ID,
    "weather_data": {"source": "weatherapi", "is_dome": False, "wind_mph": 11.4, "conditions": "Cloudy", "observed_at": "2026-09-09T23:00:00+00:00", "temperature_f": 76.5, "precipitation_pct": 7},
    "captured_at": "2026-09-07T23:10:25.507456+00:00",
}

SEA_NE_SPREAD_OPEN = {"game_id": SEA_NE_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "New England Patriots", "point": 3.5, "price": -115}, {"name": "Seattle Seahawks", "point": -3.5, "price": -105}]}, "captured_at": "2026-09-07T02:30:55.267463+00:00"}
SEA_NE_SPREAD_LATEST = {"game_id": SEA_NE_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "New England Patriots", "point": 3, "price": -102}, {"name": "Seattle Seahawks", "point": -3, "price": -118}]}, "captured_at": "2026-09-10T00:17:07.104582+00:00"}
LV_MIA_GAME_ID = "42eae7bd-08ca-4bfc-a83b-3bfac35f8b92"
LV_MIA_SPREAD_OPEN = {"game_id": LV_MIA_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Las Vegas Raiders", "point": -3.5, "price": -105}, {"name": "Miami Dolphins", "point": 3.5, "price": -115}]}, "captured_at": "2026-09-07T18:03:29.355010+00:00"}
LV_MIA_SPREAD_LATEST = {"game_id": LV_MIA_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Las Vegas Raiders", "point": -3, "price": -110}, {"name": "Miami Dolphins", "point": 3, "price": -110}]}, "captured_at": "2026-09-13T20:15:54.296273+00:00"}
LAC_ARI_GAME_ID = "57316028-d864-48e5-bbeb-df37618a1b27"
LAC_ARI_SPREAD_OPEN = {"game_id": LAC_ARI_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Arizona Cardinals", "point": 10, "price": -115}, {"name": "Los Angeles Chargers", "point": -10, "price": -105}]}, "captured_at": "2026-09-07T18:03:29.355010+00:00"}
LAC_ARI_SPREAD_LATEST = {"game_id": LAC_ARI_GAME_ID, "sportsbook": "draftkings", "market_type": "spread", "line_data": {"outcomes": [{"name": "Arizona Cardinals", "point": 8.5, "price": -102}, {"name": "Los Angeles Chargers", "point": -8.5, "price": -118}]}, "captured_at": "2026-09-13T20:15:54.296273+00:00"}

ALL_REAL_ODDS_ROWS = [SEA_NE_SPREAD_OPEN, SEA_NE_SPREAD_LATEST, LV_MIA_SPREAD_OPEN, LV_MIA_SPREAD_LATEST, LAC_ARI_SPREAD_OPEN, LAC_ARI_SPREAD_LATEST]


def _odds_route(request: httpx.Request) -> httpx.Response:
    """Real `/rest/v1/odds_snapshots` gets two structurally different
    calls (`read_odds_snapshots`'s target-game `game_id=eq.` lookup vs.
    `read_all_odds_snapshots`'s table-wide, no-`game_id`-param read)."""
    if "game_id" in request.url.params:
        return httpx.Response(200, json=[SEA_NE_SPREAD_OPEN, SEA_NE_SPREAD_LATEST])
    return httpx.Response(200, json=ALL_REAL_ODDS_ROWS)


def _games_route_full_package(request: httpx.Request) -> httpx.Response:
    """Real `/rest/v1/games` gets THREE structurally different calls once
    a real `venue_id` is involved: the single `id=eq.` venue-context
    lookup, the batch `id=in.` referenced-games lookup (player_
    performance), and `read_games_sharing_venue`'s `venue_id=eq.&id=neq.`
    lookup -- routed by inspecting which real params respx hands the
    callback. `venue_id=eq.` is checked first since that query also
    carries an `id=neq.` param that would otherwise be misread as the
    batch-lookup shape."""
    params = request.url.params
    if "venue_id" in params:
        return httpx.Response(200, json=[])  # real, live-confirmed: 0 other games share Lumen Field
    id_param = params.get("id", "")
    if id_param.startswith("eq."):
        return httpx.Response(
            200,
            json=[{
                "id": SEA_NE_GAME_ID, "home_team": "SEA", "away_team": "NE",
                "scheduled_start": "2026-09-10T00:20:00+00:00", "venue_id": SEA_NE_VENUE_ID,
                "venue_lat": 47.595097, "venue_long": -122.332245, "venue_type": "outdoor", "stadium": "Lumen Field",
            }],
        )
    return httpx.Response(200, json=[{"id": SEA_NE_GAME_ID, "scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"}])


def _mock_jsn_sea_ne_full_package_boundaries():
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_route_full_package)
    respx.get(f"{SUPABASE_URL}/rest/v1/teams").mock(side_effect=_teams_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(side_effect=_odds_route)
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[SEA_NE_WEATHER_ROW, PHI_WAS_WEATHER_ROW]))
    respx.get(f"{SUPABASE_URL}/rest/v1/venues").mock(return_value=httpx.Response(200, json=[{"id": SEA_NE_VENUE_ID, "name": "Lumen Field", "city": "Seattle", "state": "WA", "venue_type": "outdoor"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/news_article_history").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(200, json=[{"id": JSN_PLAYER_ID, "name": "Jaxon Smith-Njigba", "position": "WR", "team_id": SEATTLE_TEAM_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=JSN_SEA_NE_RAW_ROWS))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(200, json=[{"game_id": SEA_NE_GAME_ID, "raw_payload": SEA_NE_RAW_GAME_EVENT_PAYLOAD}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"team_id": SEATTLE_TEAM_ID, "provider_team_id": "79"},
                {"team_id": NEW_ENGLAND_TEAM_ID, "provider_team_id": "50"},
            ],
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_jsn_sea_ne_real_historical_context_package():
    """Directive Section 5 -- the real Context Package MANSA can assemble
    today for JSN/SEA@NE, through the real engine path AND the real
    assembly layer together. A ONE-GAME historical proof, not the final
    multi-game Context Assembly Proof."""
    _mock_jsn_sea_ne_full_package_boundaries()

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        intelligence = await build_contextual_intelligence(
            client, _headers(), game_id=SEA_NE_GAME_ID, player_id=JSN_PLAYER_ID, now=PROOF_NOW,
        )
    package = assemble_context_package(
        intelligence, player_id=JSN_PLAYER_ID, target_event_timestamp=PROOF_NOW.isoformat(),
    )

    # Real, live-confirmed classification matrix.
    assert set(package.joined_dimensions) == {"player_performance", "market"}
    assert set(package.partial_dimensions) == {"weather", "venue"}
    assert set(package.unavailable_dimensions) == {"news", "injuries", "roster_role", "team_performance", "depth_lineup", "game_state_pbp"}
    # No dimension silently omitted -- all ten present exactly once.
    all_classified = set(package.joined_dimensions) | set(package.partial_dimensions) | set(package.unavailable_dimensions)
    assert all_classified == set(SUPPORTED_DIMENSIONS) | set(UNSUPPORTED_DIMENSIONS)

    # player_performance: no duplicate inflation, real values intact.
    pp = package.dimension_completeness["player_performance"]
    assert pp.sample_size == 1
    obs = intelligence.dimensions["player_performance"].facts["observations"][0]
    assert obs["role_usage_signals"]["receiving"] == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}
    assert obs["opponent"] == "New England Patriots"  # resolves deterministically
    assert obs["duplicate_raw_row_count"] == 2  # both real rows disclosed, never inflated into 2 observations

    # weather: real target-game facts found (partial -- only 1 same-dome comparable, below the floor).
    weather = intelligence.dimensions["weather"]
    assert weather.facts["temperature_f"] == 63.1
    assert package.dimension_completeness["weather"].completeness == "partial"

    # venue: real target-game facts found (partial -- 0 other real games share Lumen Field).
    venue = intelligence.dimensions["venue"]
    assert venue.facts["venue_name"] == "Lumen Field"
    assert package.dimension_completeness["venue"].completeness == "partial"

    # market: real target odds + real comparable pool crosses the floor -- joined.
    market = intelligence.dimensions["market"]
    assert market.insufficient_evidence is False
    assert package.dimension_completeness["market"].completeness == "joined"

    # news: genuinely unavailable for this exact game via the current, unmodified engine
    # path -- games.home_team/away_team ("SEA"/"NE") don't exactly match teams.name
    # ("Seattle Seahawks"/"New England Patriots"), so resolve_team_ids_by_name resolves
    # zero team_ids and news_articles_for_teams is genuinely empty. A real, disclosed
    # finding (Section 7 of the report), not a fabricated zero.
    assert intelligence.dimensions["news"].sample_size == 0
    assert package.dimension_completeness["news"].completeness == "unavailable"

    # Package-level completeness is independent of confidence -- proven directly: market is
    # "joined" while its own confidence may or may not be high, and player_performance is
    # "joined" with confidence=None (see test_jsn_sea_ne_real_engine_proof) -- data_completeness
    # never stands in for, or is derived from, a prediction/confidence number.
    assert package.dimension_completeness["player_performance"].completeness == "joined"
    assert intelligence.dimensions["player_performance"].confidence is None

    # No prediction/probability field anywhere on the package (structural, see
    # test_context_package.py's own dedicated proof) -- spot-checked here too.
    assert not hasattr(package, "confidence")
    assert not hasattr(package, "probability")
