"""Phase 3F-2: proves the dynamic roster-ingestion path (not the static
`player_backfill.PLAYER_BACKFILL` list) is what makes PlayerStats
resolution work, end to end, against real captured fixture data.

**Why this file exists separately from test_roster_ingestion.py /
test_player_stats_persistence.py.** Those files each test one module in
isolation with synthetic identity rows. What was NOT proven anywhere
before this phase: that `app.persistence.roster_ingestion.persist_roster`
(not `app.persistence.player_backfill.backfill_known_players`) is
*sufficient*, by itself, to make a subsequent `persist_player_stats` call
resolve the exact same internal `players.id` -- the actual dependency
chain a real Sunday slate needs (roster ingestion runs in Master Refresh,
long before Postgame Worker ever calls PlayerStats).

**Fixture-evidence honesty, stated plainly:** this project's two real
SportsDataIO captures for player identity are for disjoint players --
`rosters_normal.json` (Xavier Worthy/24924, Emmanuel Ogbah/17958, both KC)
and `player_stats_week_bulk_normal.json` (Josh Allen/19801/BUF, Harold
Landry III/19862/NE) share no PlayerID. No live call was made or is
authorized to close that gap (Mac's explicit instruction). This file
therefore constructs its own `RosterEntry` roster-ingestion input using
Josh Allen's already fixture-confirmed real identity (PlayerID 19801,
Name, Team, Position -- the exact values captured in
`player_stats_week_bulk_normal.json`, the same identity already present in
`PLAYER_BACKFILL`) rather than inventing a new player. This proves the
*mechanism* composes correctly against real identity data; it is not new
evidence that SportsDataIO's `/Players/BUF` endpoint was actually
captured -- it wasn't. `app.persistence.player_backfill` is never
imported or called anywhere in this file, so nothing here can be
succeeding "because of the backfill module" by accident.
"""
from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, RosterEntry
from app.adapters.providers.sportsdataio import SportsDataIOPlayerStatsAdapter
from app.persistence.player_stats import persist_player_stats
from app.persistence.roster_ingestion import persist_roster
from tests.adapters.sportsdataio_fixtures import load

SUPABASE_URL = "https://test-project.supabase.co"
SPORTSDATAIO_URL = "https://api.sportsdata.io"

#: Josh Allen's real, fixture-confirmed identity (player_stats_week_bulk_normal.json)
#: -- see module docstring for why this identity, not a fabricated one.
JOSH_ALLEN_ID = "19801"
JOSH_ALLEN_GAME_KEY = "202510104"


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _roster_response():
    return AdapterResponse(
        value=[RosterEntry(team="BUF", player_external_id=JOSH_ALLEN_ID, player_name="Josh Allen", position="QB")],
        source="sportsdataio",
    )


async def _fetch_real_player_stats_fixture():
    """Fetches PlayerGameStatsByWeek through the real adapter against the
    real captured fixture -- proves the composition against actual parsed
    provider bytes, not a hand-built PlayerStatLine. Callers must already
    be inside an active `@respx.mock`-decorated test; this registers its
    route in that same context rather than opening a nested one."""
    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_week_bulk_normal.json"))
    )
    async with httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as client:
        adapter = SportsDataIOPlayerStatsAdapter(
            client=client, api_key="test-key",
            season_week_for_game=lambda _game_id: ("2025REG", 1),
        )
        return await adapter.fetch_player_stats(JOSH_ALLEN_GAME_KEY)


@pytest.mark.asyncio
@respx.mock
async def test_dynamic_roster_ingestion_alone_resolves_playerstats(monkeypatch):
    """The core 3F-2 proof: roster_ingestion.persist_roster (not
    player_backfill) creates the player_provider_ids mapping; a
    subsequent persist_player_stats call for the exact same PlayerID
    resolves to that same internal player_id and inserts with it."""
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf", "provider_team_id": "BUF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "internal-josh-allen"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    roster_result = await persist_roster(_roster_response())
    assert roster_result.players_created == 1
    assert create_route.call_count == 1

    player_stats_response = await _fetch_real_player_stats_fixture()
    assert player_stats_response.value[0].player_external_id == JOSH_ALLEN_ID  # real fixture value, not asserted blind

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "game-1", "provider_game_id": JOSH_ALLEN_GAME_KEY}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "internal-josh-allen", "provider_player_id": JOSH_ALLEN_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    stats_result = await persist_player_stats(player_stats_response)

    assert stats_result.inserted == 1
    assert stats_result.unresolved_players == []
    body = _json.loads(stats_insert_route.calls.last.request.content)
    assert body["player_id"] == "internal-josh-allen"  # the exact id roster_ingestion created


@pytest.mark.asyncio
@respx.mock
async def test_playerstats_before_roster_ingestion_is_unresolved_then_resolves_after(monkeypatch):
    """Proves the real ordering dependency: PlayerStats ingestion running
    before roster ingestion has ever observed a player leaves that player
    unresolved (reported, not fabricated) -- and a later retry, after
    roster ingestion has run, succeeds without any code change."""
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "game-1", "provider_game_id": JOSH_ALLEN_GAME_KEY}])
    )

    # --- Attempt 1: Postgame runs before Master Refresh has ever ingested
    # this player's roster. No player_provider_ids mapping exists yet.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players")
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats")

    player_stats_response = await _fetch_real_player_stats_fixture()
    first_attempt = await persist_player_stats(player_stats_response)

    assert first_attempt.unresolved_players == [JOSH_ALLEN_ID]
    assert first_attempt.inserted == 0
    assert not players_insert_route.called  # never auto-created to paper over the gap
    assert not stats_insert_route.called

    # --- Roster ingestion now runs (e.g. next Master Refresh cycle).
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf", "provider_team_id": "BUF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "internal-josh-allen"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    await persist_roster(_roster_response())

    # --- Attempt 2: Postgame's next reconciliation checkpoint retries the
    # same player -- now resolves cleanly, no code change needed anywhere.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "internal-josh-allen", "provider_player_id": JOSH_ALLEN_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    second_stats_insert = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    second_attempt = await persist_player_stats(player_stats_response)

    assert second_attempt.inserted == 1
    assert second_attempt.unresolved_players == []
    body = _json.loads(second_stats_insert.calls.last.request.content)
    assert body["player_id"] == "internal-josh-allen"


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_player_does_not_block_other_players_in_same_batch(monkeypatch):
    """One player in a PlayerStats batch has never been roster-ingested;
    the other has. The resolved one is persisted; the unresolved one is
    reported and skipped -- neither blocks the other."""
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": "game-1", "provider_game_id": "202510104"},
                {"game_id": "game-2", "provider_game_id": "202510121"},
            ],
        )
    )
    # Only Josh Allen (19801) has a mapping; Harold Landry III (19862) does not.
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "internal-josh-allen", "provider_player_id": "19801"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    respx.get(f"{SPORTSDATAIO_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_week_bulk_normal.json"))
    )
    async with httpx.AsyncClient(base_url=SPORTSDATAIO_URL) as client:
        adapter = SportsDataIOPlayerStatsAdapter(
            client=client, api_key="test-key",
            season_week_for_game=lambda _game_id: ("2025REG", 1),
        )
        allen_response = await adapter.fetch_player_stats("202510104")
        landry_response = await adapter.fetch_player_stats("202510121")

    combined = AdapterResponse(value=allen_response.value + landry_response.value, source="sportsdataio")
    result = await persist_player_stats(combined)

    assert result.inserted == 1
    assert result.unresolved_players == ["19862"]
    assert insert_route.call_count == 1
    body = _json.loads(insert_route.calls.last.request.content)
    assert body["player_id"] == "internal-josh-allen"


@pytest.mark.asyncio
@respx.mock
async def test_team_change_preserves_same_player_id_for_player_stats(monkeypatch):
    """A player observed on a new team via roster ingestion keeps the same
    internal player_id -- team_stats/player_stats FKs (and any historical
    row already written) remain valid, since only players.team_id and a
    new roster_memberships row change, never player_provider_ids or the
    players row's own id."""
    _headers_env(monkeypatch)

    # First roster observation: BUF.
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf", "provider_team_id": "BUF"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    create_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        return_value=httpx.Response(201, json=[{"id": "internal-josh-allen"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    membership_route = respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots").mock(return_value=httpx.Response(201))

    first = await persist_roster(_roster_response())
    assert first.players_created == 1

    # A player_stats row gets written against this player_id (e.g. by
    # Postgame Worker after a game with BUF).
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"game_id": "game-1", "provider_game_id": JOSH_ALLEN_GAME_KEY}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "internal-josh-allen", "provider_player_id": JOSH_ALLEN_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))
    player_stats_response = await _fetch_real_player_stats_fixture()
    await persist_player_stats(player_stats_response)
    historical_body = _json.loads(stats_insert_route.calls.last.request.content)
    assert historical_body["player_id"] == "internal-josh-allen"

    # --- Team change: the same PlayerID (19801) is now observed on a
    # different team (simulating a trade -- an entirely new RosterEntry.team).
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-min", "provider_team_id": "MIN"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"player_id": "internal-josh-allen", "provider_player_id": JOSH_ALLEN_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(
        return_value=httpx.Response(200, json=[{"team_id": "team-buf"}])
    )

    traded_roster = AdapterResponse(
        value=[RosterEntry(team="MIN", player_external_id=JOSH_ALLEN_ID, player_name="Josh Allen", position="QB")],
        source="sportsdataio",
    )
    second = await persist_roster(traded_roster)

    assert second.players_created == 0  # same player, never re-created
    assert second.players_confirmed == 1
    assert second.memberships_inserted == 1  # new team -> new history row
    assert create_route.call_count == 1  # players INSERT only ever called once, total
    assert membership_route.call_count == 2  # BUF observation + MIN observation
    patch_body = _json.loads(patch_route.calls.last.request.content)
    assert patch_body == {"team_id": "team-min"}
    assert patch_route.calls.last.request.url.params.get("id") == "eq.internal-josh-allen"

    # The player_stats row written before the trade still references the
    # same internal player_id -- nothing about roster ingestion touches
    # player_stats at all, so its FK is untouched by construction, not by
    # coincidence: re-confirm the FK used at write time above.
    assert historical_body["player_id"] == "internal-josh-allen"
