"""Tests for app.master_refresh.game_refresh (Phase 3F-3's stadium
venue-surfacing addition, plus the pre-existing shared per-game refresh
behavior from 3E-2/3E-8).

`_build_stadium` is the one new piece of logic this phase adds -- pure,
directly unit-tested here. `refresh_daily_game_intelligence_for_game` is
the single shared assembly path both Master Refresh (run.py) and Pregame
Worker (pregame_worker.py) call -- proven once here that it wires
`_build_stadium`'s output into the upserted payload; test_master_refresh.py
and test_pregame_worker.py each add one assertion confirming their own
call site actually goes through this same function, not a duplicate.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.models import RosterEntry
from app.master_refresh.game_refresh import _build_stadium, _enrich_roster, refresh_daily_game_intelligence_for_game

SUPABASE_URL = "https://test-project.supabase.co"


def _entry(player_external_id, name="Test Player", team="SEA", position="QB", depth_chart_rank=1):
    return RosterEntry(
        team=team, player_external_id=player_external_id, player_name=name,
        position=position, depth_chart_rank=depth_chart_rank,
    )


def test_enrich_roster_attaches_resolved_internal_player_id():
    """Phase 3F-4: existing fields (team/player_external_id/player_name/
    position/depth_chart_rank) are preserved unchanged; player_id is the
    only addition."""
    roster = [_entry("19801", name="Josh Allen")]
    enriched = _enrich_roster(roster, {"19801": "internal-player-uuid-1"})
    assert enriched == [{
        "team": "SEA", "player_external_id": "19801", "player_name": "Josh Allen",
        "position": "QB", "depth_chart_rank": 1, "player_id": "internal-player-uuid-1",
    }]


def test_enrich_roster_multiple_players_each_resolve_to_correct_id():
    roster = [_entry("1", name="Player One"), _entry("2", name="Player Two")]
    enriched = _enrich_roster(roster, {"1": "uuid-1", "2": "uuid-2"})
    assert [e["player_id"] for e in enriched] == ["uuid-1", "uuid-2"]


def test_enrich_roster_unresolved_player_gets_null_id_not_fabricated():
    """A player absent from the resolved-id mapping (never durably
    ingested, or this cycle's persist_roster failed before reaching them)
    gets player_id: None -- the rest of the roster data (still fresh, still
    real) is preserved untouched, never dropped."""
    roster = [_entry("999", name="Unresolved Player")]
    enriched = _enrich_roster(roster, {})
    assert enriched == [{
        "team": "SEA", "player_external_id": "999", "player_name": "Unresolved Player",
        "position": "QB", "depth_chart_rank": 1, "player_id": None,
    }]


def test_enrich_roster_mixed_resolved_and_unresolved_in_same_team():
    roster = [_entry("1", name="Resolved"), _entry("2", name="Unresolved")]
    enriched = _enrich_roster(roster, {"1": "uuid-1"})
    by_name = {e["player_name"]: e["player_id"] for e in enriched}
    assert by_name == {"Resolved": "uuid-1", "Unresolved": None}


def test_enrich_roster_never_does_fuzzy_name_matching():
    """No name-based fallback: a mapping keyed by a *different* provider id
    than the roster entry carries never resolves, even if names match."""
    roster = [_entry("1", name="Josh Allen")]
    enriched = _enrich_roster(roster, {"different-id": "uuid-1"})
    assert enriched[0]["player_id"] is None


def test_stadium_includes_name_lat_long_type_when_all_present():
    game = {"stadium": "Lumen Field", "venue_lat": 47.5952, "venue_long": -122.3316, "venue_type": "outdoor"}
    assert _build_stadium(game) == {
        "name": "Lumen Field", "latitude": 47.5952, "longitude": -122.3316, "venue_type": "outdoor",
    }


def test_stadium_preserves_null_for_individually_missing_fields():
    """Real, partial current-state: name known, coordinates not yet
    captured -- each missing field stays None, never fabricated or
    defaulted to 0/empty string."""
    game = {"stadium": "Lumen Field", "venue_lat": None, "venue_long": None, "venue_type": None}
    assert _build_stadium(game) == {"name": "Lumen Field", "latitude": None, "longitude": None, "venue_type": None}


def test_stadium_is_none_when_nothing_at_all_is_known():
    game = {"stadium": None, "venue_lat": None, "venue_long": None, "venue_type": None}
    assert _build_stadium(game) is None


def test_stadium_is_none_when_venue_fields_absent_from_dict_entirely():
    """A caller-supplied game dict missing the venue keys altogether
    (rather than explicit None) -- .get() defaults, same result as
    explicit None, never a KeyError."""
    assert _build_stadium({}) is None


@pytest.mark.parametrize("venue_type", ["dome", "retractable_dome", "outdoor"])
def test_stadium_passes_through_every_venue_type_value_unchanged(venue_type):
    game = {"stadium": "Test Stadium", "venue_lat": 1.0, "venue_long": 2.0, "venue_type": venue_type}
    assert _build_stadium(game)["venue_type"] == venue_type


@pytest.mark.asyncio
@respx.mock
async def test_refresh_daily_game_intelligence_for_game_writes_full_venue_shape(monkeypatch):
    """The shared per-game refresh path -- used by both Master Refresh and
    Pregame Worker -- upserts the new venue shape, not just `name`."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))  # find_previous_final_game, both sides
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": "Lumen Field", "venue_lat": 47.5952, "venue_long": -122.3316, "venue_type": "outdoor",
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["stadium"] == {
        "name": "Lumen Field", "latitude": 47.5952, "longitude": -122.3316, "venue_type": "outdoor",
    }


@pytest.mark.asyncio
@respx.mock
async def test_refresh_daily_game_intelligence_never_fabricates_missing_venue_data(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    # A game whose venue_lat/venue_long/venue_type haven't been captured
    # yet (pre-3E-6 row, or a provider that never supplied them).
    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": "Lumen Field", "venue_lat": None, "venue_long": None, "venue_type": None,
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["stadium"] == {"name": "Lumen Field", "latitude": None, "longitude": None, "venue_type": None}
    # Phase 4/5 fields remain untouched by this change, same as always.
    assert {"ai_scores", "momentum", "matchup_ratings", "ev_calculations", "confidence_scores", "recommendation_candidates"}.isdisjoint(body.keys())


@pytest.mark.asyncio
@respx.mock
async def test_master_refresh_call_site_writes_enriched_player_id(monkeypatch):
    """Phase 3F-4: when called with `rosters`+`player_ids` (Master
    Refresh's own call site), the upserted `players` payload carries the
    resolved internal player_id alongside every pre-existing field."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": None, "venue_lat": None, "venue_long": None, "venue_type": None,
    }
    rosters = {
        "SEA": [RosterEntry(team="SEA", player_external_id="1", player_name="Resolved", position="QB", depth_chart_rank=1)],
        "NE": [RosterEntry(team="NE", player_external_id="2", player_name="Unresolved", position="WR", depth_chart_rank=2)],
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
        rosters=rosters, player_ids={"1": "internal-uuid-1"},
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["players"]["home"][0]["player_id"] == "internal-uuid-1"
    assert body["players"]["away"][0]["player_id"] is None
    # existing fields preserved unchanged
    assert body["players"]["home"][0]["player_name"] == "Resolved"
    assert body["players"]["away"][0]["depth_chart_rank"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_pregame_call_site_passthrough_preserves_enriched_shape(monkeypatch):
    """Phase 3F-4: Pregame Worker's call site (no `rosters`/`player_ids`)
    reads back whatever Master Refresh already wrote, including its
    player_id enrichment -- no second identity resolution needed."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/injury_reports").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/weather_snapshots").mock(return_value=httpx.Response(200, json=[]))
    existing_players = {
        "home": [{"team": "SEA", "player_external_id": "1", "player_name": "Resolved", "position": "QB", "depth_chart_rank": 1, "player_id": "internal-uuid-1"}],
        "away": None,
    }
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(
        return_value=httpx.Response(200, json=[{"news": None, "players": existing_players}])
    )
    upsert_route = respx.post(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(201))

    game = {
        "id": "game-1", "home_team": "SEA", "away_team": "NE",
        "scheduled_start": datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc).isoformat(),
        "stadium": None, "venue_lat": None, "venue_long": None, "venue_type": None,
    }

    await refresh_daily_game_intelligence_for_game(
        httpx.AsyncClient(base_url=SUPABASE_URL), {"Authorization": "Bearer x", "apikey": "x"}, game,
    )

    body = _json.loads(upsert_route.calls.last.request.content)
    assert body["players"] == existing_players
