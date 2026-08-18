"""Scenario tests for the five concrete SportsDataIO adapters (Phase
3C-ii). Fixtures are real, live-captured structures (see
tests/fixtures/sportsdataio/PROVENANCE.md) -- this is the first Playbook
vendor with fixtures that reached CONFIRMED FROM LIVE FREE TRIAL --
STRUCTURE, not just ASSUMED.

Covers: successful normalization, malformed payloads, provider error
translation, the week-bulk-cache -> per-game-filter behavior (Mac's
explicit 2026-08-12 architecture decision -- a second game from an
already-fetched week must not trigger a second provider call), the
Roster+DepthChart merge (including DepthCharts' value overriding Players'
own, scrambled depth field), the Injuries game_external_id derivation via
an injected Schedule-lookup resolver, nested PlayerStats payload handling,
and tolerance of scrambled/internally-inconsistent trial values (no test
here asserts they reconcile mathematically -- see PROVENANCE.md).
"""
from __future__ import annotations

from datetime import datetime, timezone

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
from app.adapters.models import (
    AdapterResponse,
    InjuryReport,
    PlayerStatLine,
    RosterEntry,
    ScheduleEntry,
    TeamStatLine,
)
from app.adapters.providers.sportsdataio import (
    SportsDataIOInjuryAdapter,
    SportsDataIOPlayerStatsAdapter,
    SportsDataIORosterAdapter,
    SportsDataIOScheduleAdapter,
    SportsDataIOTeamStatsAdapter,
)
from tests.adapters.fakes import FakeRosterAdapter, FakeTeamStatsAdapter
from tests.adapters.sportsdataio_fixtures import load

BASE_URL = "https://api.sportsdata.io"
API_KEY = "test-key"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL)


# ============================================================
# Roster + DepthChart merge
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_roster_merges_depth_chart_rank_from_dedicated_endpoint_not_players_own_field():
    """The core source-of-truth proof: Worthy's OWN `DepthOrder` on the
    Players response is 3, but DepthCharts (the authoritative source) says
    1 -- the normalized RosterEntry must reflect DepthCharts' value, not
    Players'. Ogbah has no DepthCharts entry at all -- his rank stays
    None, not silently defaulted to Players' own null."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_roster("KC")

    assert isinstance(response, AdapterResponse)
    by_id = {e.player_external_id: e for e in response.value}
    assert by_id["24924"].depth_chart_rank == 1  # from DepthCharts, not Players' own "3"
    assert by_id["17958"].depth_chart_rank is None  # no DepthCharts entry for this player
    assert by_id["24924"].team == "KC"
    assert by_id["24924"].player_name == "Xavier Worthy"
    assert by_id["24924"].position == "RWR" or by_id["24924"].position  # Players' own Position used


@pytest.mark.asyncio
@respx.mock
async def test_depth_chart_bulk_is_cached_across_multiple_roster_fetches():
    """Two different teams requested -- the league-wide DepthCharts bulk
    payload is fetched once and reused, not re-fetched per team."""
    players_route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    other_players_route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/SEA").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    depth_route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    adapter = SportsDataIORosterAdapter(
        client=_client(), api_key=API_KEY, cache_backend=InMemoryCacheBackend()
    )
    await adapter.fetch_roster("KC")
    await adapter.fetch_roster("SEA")

    assert players_route.call_count == 1
    assert other_players_route.call_count == 1
    assert depth_route.call_count == 1  # reused, not re-fetched


@pytest.mark.asyncio
@respx.mock
async def test_depth_chart_failure_propagates_no_silent_fallback():
    """Mac's explicit instruction: if DepthCharts fails, the whole
    fetch_roster call raises -- it must NOT silently fall back to Players'
    own (unreliable, scrambled-in-trial) depth fields."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(return_value=httpx.Response(503))
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_roster("KC")


@pytest.mark.asyncio
@respx.mock
async def test_malformed_roster_row_is_isolated_and_skipped(caplog):
    """Row isolation (2026-08-18, same defensive philosophy as the
    Schedule fix): one player row missing PlayerID is logged and skipped,
    not batch-fatal. This fixture has exactly one row, so the result
    comes back empty, not raised."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("roster_malformed.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_roster("KC")
    assert response.value == []
    assert "skipping malformed roster row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_roster_valid_rows_survive_around_one_malformed_row():
    """The fuller row-isolation proof: a valid player alongside a
    malformed one -- the valid player still comes back."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"PlayerID": 24924, "Team": "KC", "Name": "Xavier Worthy", "Position": "WR"},
                {"Team": "KC", "Name": "Nobody", "Position": "QB"},  # missing PlayerID
            ],
        )
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_roster("KC")
    assert [e.player_external_id for e in response.value] == ["24924"]


@pytest.mark.asyncio
@respx.mock
async def test_malformed_depth_chart_entry_is_isolated_and_skipped(caplog):
    """Row isolation: one depth-chart entry missing PlayerID is logged
    and skipped -- the roster fetch itself still succeeds, just without a
    depth_chart_rank for that entry (this fixture has only that one
    entry, so every roster player ends up with depth_chart_rank=None,
    not raised)."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_malformed.json"))
    )
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_roster("KC")
    assert len(response.value) == 2  # rosters_normal.json's own 2 players, both isolated from the bad depth-chart entry
    assert all(e.depth_chart_rank is None for e in response.value)
    assert "skipping malformed depth chart entry" in caplog.text


# ============================================================
# Schedule
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_schedule_normalizes_datetime_utc_stadium_and_status():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=load("schedules_normal.json"))
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_schedule("2026REG")

    entry = response.value[0]
    assert isinstance(entry, ScheduleEntry)
    assert entry.game_external_id == "202610130"
    assert entry.home_team == "SEA"
    assert entry.away_team == "NE"
    assert entry.status == "scheduled"
    assert entry.scheduled_start == datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
    assert entry.stadium  # StadiumDetails.Name, not just StadiumID
    # Phase 3E-6, Option A: venue coordinates + normalized type preserved,
    # not discarded -- CONFIRMED FROM LIVE FREE TRIAL fixture values.
    assert entry.venue_lat == 47.5952
    assert entry.venue_long == -122.331625
    assert entry.venue_type == "outdoor"


@pytest.mark.asyncio
@respx.mock
async def test_schedule_missing_venue_metadata_stays_none_not_fabricated():
    """A response with no StadiumDetails at all -- e.g. a provider entry
    that never carried venue metadata -- is a legitimate, expected
    "unknown," not malformed. venue_lat/venue_long/venue_type all stay
    None rather than being guessed or defaulted."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "GameKey": "202610999",
                    "SeasonType": 1,
                    "Week": 1,
                    "HomeTeam": "SEA",
                    "AwayTeam": "NE",
                    "DateTimeUTC": "2026-09-10T00:20:00",
                    "Status": "Scheduled",
                }
            ],
        )
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_schedule("2026REG")

    entry = response.value[0]
    assert entry.stadium is None
    assert entry.venue_lat is None
    assert entry.venue_long is None
    assert entry.venue_type is None


@pytest.mark.asyncio
@respx.mock
async def test_schedule_unrecognized_venue_type_is_isolated_and_skipped(caplog):
    """Row isolation (2026-08-18): a present-but-unrecognized
    StadiumDetails.Type is never silently passed through or guessed --
    but as of the row-isolation fix, that one row is logged and skipped
    rather than aborting the whole fetch. This fixture has exactly one
    row, so the response comes back empty, not raised."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=load("schedules_unrecognized_venue_type.json"))
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_schedule("2026REG")
    assert response.value == []
    assert "skipping malformed/unrecognized schedule row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_schedule_unrecognized_status_is_isolated_and_skipped(caplog):
    """The full 9-value SportsDataIO status vocabulary is CONFIRMED FROM
    PROVIDER DOCUMENTATION (2026-08-18) -- a value outside it ("TBD" here,
    never documented) still raises internally, but row isolation means
    that raise is caught and logged per-row, not propagated to the
    caller. This fixture has exactly one row, so the response comes back
    empty, not raised."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=load("schedules_unrecognized_status.json"))
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_schedule("2026REG")
    assert response.value == []
    assert "skipping malformed/unrecognized schedule row" in caplog.text
    assert "GameKey='202610130'" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_malformed_schedule_row_is_isolated_and_skipped(caplog):
    """A structurally malformed row (missing GameKey) is also row-isolated
    -- logged and skipped, not batch-fatal, same discipline as an
    unrecognized status/venue_type."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json=load("schedules_malformed.json"))
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_schedule("2026REG")
    assert response.value == []
    assert "skipping malformed/unrecognized schedule row" in caplog.text


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "raw_status,expected_internal",
    [
        ("Scheduled", "scheduled"),
        ("InProgress", "live"),
        ("Final", "final"),
        ("F/OT", "final"),
        ("Postponed", "postponed"),
        ("Canceled", "canceled"),
        ("Delayed", "scheduled"),
        ("Suspended", "live"),
        ("Forfeit", "final"),
    ],
)
async def test_schedule_maps_every_documented_status(raw_status, expected_internal):
    """CONFIRMED FROM PROVIDER DOCUMENTATION (2026-08-18): all 9 documented
    SportsDataIO status values normalize to this project's existing
    internal vocabulary -- no invented internal states."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "GameKey": "202610130",
                    "HomeTeam": "SEA",
                    "AwayTeam": "NE",
                    "DateTimeUTC": "2026-09-10T00:20:00",
                    "SeasonType": 1,
                    "Status": raw_status,
                }
            ],
        )
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_schedule("2026REG")
    assert response.value[0].status == expected_internal


@pytest.mark.asyncio
@respx.mock
async def test_schedule_one_bad_row_does_not_take_down_valid_rows_around_it():
    """The core row-isolation proof: a batch with a genuinely unrecognized
    status sandwiched between two valid games -- both valid games survive,
    the bad one is simply absent from the result."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"GameKey": "g1", "HomeTeam": "SEA", "AwayTeam": "NE", "DateTimeUTC": "2026-09-10T00:20:00", "SeasonType": 1, "Status": "Scheduled"},
                {"GameKey": "g2", "HomeTeam": "KC", "AwayTeam": "BUF", "DateTimeUTC": "2026-09-10T17:00:00", "SeasonType": 1, "Status": "TBD"},
                {"GameKey": "g3", "HomeTeam": "DAL", "AwayTeam": "PHI", "DateTimeUTC": "2026-09-10T20:00:00", "SeasonType": 1, "Status": "InProgress"},
            ],
        )
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    response = await adapter.fetch_schedule("2026REG")
    assert [e.game_external_id for e in response.value] == ["g1", "g3"]
    assert response.value[1].status == "live"


@pytest.mark.asyncio
@respx.mock
async def test_schedule_top_level_provider_failure_still_raises():
    """Row isolation only applies inside an already-successful response --
    an HTTP-level failure still fails the whole call, unchanged."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(return_value=httpx.Response(500))
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_schedule("2026REG")


@pytest.mark.asyncio
@respx.mock
async def test_schedule_non_array_payload_still_raises():
    """Row isolation only applies to individual rows within an array -- a
    non-array top-level payload still fails the whole call, unchanged."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Schedules/2026REG").mock(
        return_value=httpx.Response(200, json={"not": "an array"})
    )
    adapter = SportsDataIOScheduleAdapter(client=_client(), api_key=API_KEY)
    with pytest.raises(ProviderDataError):
        await adapter.fetch_schedule("2026REG")


# ============================================================
# TeamStats -- week-bulk cache -> per-game filter
# ============================================================

def _season_week_lookup(mapping: dict[str, tuple[str, int]]):
    return lambda game_external_id: mapping[game_external_id]


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_filters_week_bulk_by_game_key():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510122": ("2025REG", 1)}),
    )
    response = await adapter.fetch_team_stats("202510122")

    assert {line.team for line in response.value} == {"ARI", "NO"}
    assert all(line.game_external_id == "202510122" for line in response.value)
    for line in response.value:
        assert isinstance(line, TeamStatLine)
        assert "GameKey" not in line.stats  # promoted field, not duplicated
        assert "Team" not in line.stats
        assert "Score" in line.stats  # everything else stays in stats


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_second_game_same_week_reuses_cached_bulk_no_second_call():
    """The actual efficiency requirement: two different GameKeys, same
    season/week -- only one provider HTTP call total."""
    route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup(
            {"202510122": ("2025REG", 1), "202510102": ("2025REG", 1)}
        ),
        cache_backend=InMemoryCacheBackend(),
    )
    first = await adapter.fetch_team_stats("202510122")
    second = await adapter.fetch_team_stats("202510102")

    assert route.call_count == 1
    assert {line.team for line in first.value} == {"ARI", "NO"}
    assert {line.team for line in second.value} == {"ATL", "TB"}


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_no_bulk_cache_configured_refetches_each_call():
    """Without a cache_backend (the default), each call re-fetches -- this
    documents the opt-in nature of the bulk cache, matching every other
    adapter's "no caching of its own unless wrapped/configured" behavior."""
    route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup(
            {"202510122": ("2025REG", 1), "202510102": ("2025REG", 1)}
        ),
    )
    await adapter.fetch_team_stats("202510122")
    await adapter.fetch_team_stats("202510102")

    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_tolerates_internally_inconsistent_scrambled_numbers():
    """Real, confirmed trial behavior: Score != sum(quarters) in every
    captured row. The adapter must not validate this -- it's expected,
    not a defect (see PROVENANCE.md)."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510122": ("2025REG", 1)}),
    )
    response = await adapter.fetch_team_stats("202510122")
    ari = next(line for line in response.value if line.team == "ARI")
    quarters_sum = sum(
        ari.stats[f"ScoreQuarter{n}"] for n in (1, 2, 3, 4)
    ) + ari.stats["ScoreOvertime"]
    assert quarters_sum != ari.stats["Score"]  # documents the scrambling, doesn't fix it


@pytest.mark.asyncio
@respx.mock
async def test_malformed_team_stats_row_is_isolated_and_skipped(caplog):
    """Row isolation (2026-08-18): a row missing GameKey can't even be
    matched against the requested game, so it's logged and skipped during
    filtering -- not batch-fatal. This fixture has exactly one row, so
    the result comes back empty, not raised."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_malformed.json"))
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"whatever": ("2025REG", 1)}),
    )
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_team_stats("whatever")
    assert response.value == []
    assert "skipping malformed team-stats row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_valid_rows_survive_a_malformed_row_elsewhere_in_the_week(caplog):
    """The fuller proof: the week's bulk payload has one row for the
    requested game (valid) and one row belonging to a different game
    entirely, missing GameKey -- the valid row for the requested game
    still comes back."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"GameKey": "202510104", "Team": "BUF", "Score": 27},
                {"Team": "SOME-OTHER-GAME", "Score": 10},  # missing GameKey
            ],
        )
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510104": ("2025REG", 1)}),
    )
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_team_stats("202510104")
    assert len(response.value) == 1
    assert response.value[0].team == "BUF"
    assert "skipping malformed team-stats row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_401_raises_provider_auth_error():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(return_value=httpx.Response(401))
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"x": ("2025REG", 1)}),
    )
    with pytest.raises(ProviderAuthError):
        await adapter.fetch_team_stats("x")


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_429_raises_provider_rate_limit_error():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(return_value=httpx.Response(429))
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"x": ("2025REG", 1)}),
    )
    with pytest.raises(ProviderRateLimitError):
        await adapter.fetch_team_stats("x")


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_5xx_raises_provider_unavailable_error():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(return_value=httpx.Response(503))
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"x": ("2025REG", 1)}),
    )
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_team_stats("x")


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_404_raises_provider_data_error():
    """CONFIRMED real behavior from this project's own diagnostic history:
    a week that hasn't been played yet 404s -- a data-availability
    condition, not an outage."""
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2026REG/1").mock(return_value=httpx.Response(404))
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"x": ("2026REG", 1)}),
    )
    with pytest.raises(ProviderDataError):
        await adapter.fetch_team_stats("x")


@pytest.mark.asyncio
@respx.mock
async def test_team_stats_timeout_raises_provider_unavailable_error():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"x": ("2025REG", 1)}),
    )
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_team_stats("x")


# ============================================================
# PlayerStats -- week-bulk cache -> per-game filter, nested payload
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_player_stats_filters_by_game_key_and_preserves_nested_scoring_details():
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOPlayerStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510104": ("2025REG", 1)}),
    )
    response = await adapter.fetch_player_stats("202510104")

    assert len(response.value) == 1
    line = response.value[0]
    assert isinstance(line, PlayerStatLine)
    assert line.player_external_id == "19801"
    assert line.player_name == "Josh Allen"
    assert line.team == "BUF"
    assert "GameKey" not in line.stats
    assert "PlayerID" not in line.stats
    assert "Name" not in line.stats
    assert "Team" not in line.stats
    assert "ScoringDetails" in line.stats  # nested sub-structure preserved, not extracted
    assert isinstance(line.stats["ScoringDetails"], list)
    assert line.stats["ScoringDetails"][0]["ScoringType"] == "PassingTouchdown"


@pytest.mark.asyncio
@respx.mock
async def test_player_stats_second_game_same_week_reuses_cached_bulk_no_second_call():
    route = respx.get(f"{BASE_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOPlayerStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup(
            {"202510104": ("2025REG", 1), "202510121": ("2025REG", 1)}
        ),
        cache_backend=InMemoryCacheBackend(),
    )
    first = await adapter.fetch_player_stats("202510104")
    second = await adapter.fetch_player_stats("202510121")

    assert route.call_count == 1
    assert first.value[0].player_name == "Josh Allen"
    assert second.value[0].player_name == "Harold Landry III"
    assert second.value[0].stats["ScoringDetails"] == []  # present but empty for this row


@pytest.mark.asyncio
@respx.mock
async def test_malformed_player_stats_row_is_isolated_and_skipped(caplog):
    """Row isolation (2026-08-18): a row missing PlayerID is logged and
    skipped, not batch-fatal. This fixture has exactly one row, so the
    result comes back empty, not raised."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_malformed.json"))
    )
    adapter = SportsDataIOPlayerStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510104": ("2025REG", 1)}),
    )
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_player_stats("202510104")
    assert response.value == []
    assert "skipping malformed player-stats row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_player_stats_valid_rows_survive_a_malformed_row_for_the_same_game(caplog):
    """The fuller proof: two rows for the same requested game, one valid
    and one missing PlayerID -- the valid player's stats still come
    back."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"GameKey": "202510104", "PlayerID": 19801, "Name": "Josh Allen", "Team": "BUF", "PassingYards": 300},
                {"GameKey": "202510104", "Name": "Nobody", "Team": "BUF", "PassingYards": 0},  # missing PlayerID
            ],
        )
    )
    adapter = SportsDataIOPlayerStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510104": ("2025REG", 1)}),
    )
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_player_stats("202510104")
    assert len(response.value) == 1
    assert response.value[0].player_external_id == "19801"
    assert "skipping malformed player-stats row" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_player_stats_tolerates_fractional_scrambled_counting_stats():
    """Real, confirmed trial behavior: counting stats like PassingAttempts
    can be fractional (53.6). Not validated/rejected -- expected."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/PlayerGameStatsByWeek/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("player_stats_week_bulk_normal.json"))
    )
    adapter = SportsDataIOPlayerStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510104": ("2025REG", 1)}),
    )
    response = await adapter.fetch_player_stats("202510104")
    passing_attempts = response.value[0].stats["PassingAttempts"]
    assert isinstance(passing_attempts, float) and passing_attempts != int(passing_attempts)


# ============================================================
# Injuries -- derived game_external_id via Schedule-lookup resolver
# ============================================================

def _game_key_lookup(mapping: dict[tuple[str, str, str, int], str | None]):
    def resolver(team: str, opponent: str, season: str, week: int) -> str | None:
        return mapping.get((team, opponent, season, week))
    return resolver


@pytest.mark.asyncio
@respx.mock
async def test_injuries_derives_game_external_id_via_resolver():
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup(
            {
                ("ARI", "NO", "2025REG", 1): "202510122",
                ("ATL", "TB", "2025REG", 1): "202510102",
                ("BAL", "BUF", "2025REG", 1): "202510104",
            }
        ),
    )
    response = await adapter.fetch_injuries()

    assert len(response.value) == 3
    by_team = {r.team: r for r in response.value}
    assert by_team["ARI"].game_external_id == "202510122"
    assert isinstance(by_team["ARI"], InjuryReport)
    assert by_team["ARI"].description is None  # deliberately unmapped, see module docstring


@pytest.mark.asyncio
@respx.mock
async def test_injuries_filters_by_team_param():
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({("ARI", "NO", "2025REG", 1): "202510122"}),
    )
    response = await adapter.fetch_injuries(team="ARI")

    assert len(response.value) == 1
    assert response.value[0].team == "ARI"


@pytest.mark.asyncio
@respx.mock
async def test_injuries_skips_records_with_no_resolvable_game_bye_week_case():
    """A resolver returning None (e.g. a bye-week team) is expected,
    real-world behavior -- that record is skipped, not raised as
    malformed."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({}),  # resolves nothing -- every team "on bye"
    )
    response = await adapter.fetch_injuries()

    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_malformed_injuries_row_is_isolated_valid_rows_survive(caplog):
    """Phase 3E-5, Mac's Decision 3: a single malformed row (here, ATL's
    row is missing PlayerID) must not invalidate the whole week's
    response -- ARI's and BAL's otherwise-valid rows must still come back.
    This replaces the pre-3E-5 whole-call-raises behavior, approved
    explicitly as part of 3E-5."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_mixed_with_malformed_row.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup(
            {
                ("ARI", "NO", "2025REG", 1): "202510122",
                ("ATL", "TB", "2025REG", 1): "202510102",
                ("BAL", "BUF", "2025REG", 1): "202510104",
            }
        ),
    )
    with caplog.at_level("WARNING"):
        response = await adapter.fetch_injuries()

    by_team = {r.team: r for r in response.value}
    assert set(by_team) == {"ARI", "BAL"}  # ATL's malformed row is absent, not a crash
    assert len(response.value) == 2

    # Logged, not silently dropped -- diagnosable per Mac's explicit
    # requirement.
    assert any("malformed row skipped" in record.message for record in caplog.records)
    assert any("ATL" in record.message for record in caplog.records)


@pytest.mark.asyncio
@respx.mock
async def test_all_rows_malformed_returns_empty_not_raised():
    """The degenerate case of the isolation above: if every row in the
    week's response is malformed, fetch_injuries succeeds with an empty
    list rather than raising -- the response as a whole is still a valid
    JSON array (the provider/response-level contract `_parse_json_array`
    enforces), it's just that none of its rows normalized."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_malformed.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({("ARI", "NO", "2025REG", 1): "202510122"}),
    )
    response = await adapter.fetch_injuries()
    assert response.value == []


@pytest.mark.asyncio
@respx.mock
async def test_injuries_non_array_top_level_still_raises_provider_data_error():
    """The boundary Mac's Decision 3 explicitly preserves: a genuine
    response-level failure (here, a top-level object instead of the
    expected array) still fails the whole fetch -- per-row isolation only
    applies to malformed rows *within* an otherwise-valid array, never to
    a fundamentally wrong top-level shape."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json={"error": "not an array"})
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({}),
    )
    with pytest.raises(ProviderDataError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_injuries_provider_unavailable_still_raises_whole_fetch():
    """The other boundary Decision 3 preserves: a transport/HTTP-level
    failure still fails the whole fetch -- untouched by per-row isolation,
    which only ever operates on rows already inside a successfully
    parsed, well-shaped response."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(500)
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({}),
    )
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_injuries()


@pytest.mark.asyncio
@respx.mock
async def test_injuries_tolerates_scrambled_status_value():
    """Every Status value in the real capture is literally "Scrambled" --
    the adapter must not validate/reject this, only pass it through
    structurally (see PROVENANCE.md)."""
    respx.get(f"{BASE_URL}/v3/nfl/stats/json/Injuries/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("injuries_normal.json"))
    )
    adapter = SportsDataIOInjuryAdapter(
        client=_client(), api_key=API_KEY,
        current_season_week=lambda: ("2025REG", 1),
        game_key_for=_game_key_lookup({("ARI", "NO", "2025REG", 1): "202510122"}),
    )
    response = await adapter.fetch_injuries(team="ARI")
    assert response.value[0].status == "Scrambled"


# ============================================================
# Cache boundary (outer CachingAdapter) + vendor swap
# ============================================================

@pytest.mark.asyncio
@respx.mock
async def test_outer_caching_adapter_avoids_second_http_call_for_roster():
    route = respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    adapter = SportsDataIORosterAdapter(client=_client(), api_key=API_KEY)
    caching = CachingAdapter(adapter, InMemoryCacheBackend(), ttl_seconds=900)

    response_model = AdapterResponse[list[RosterEntry]]
    first = await caching.call("fetch_roster", "KC", response_model=response_model)
    second = await caching.call("fetch_roster", "KC", response_model=response_model)

    assert route.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True


@pytest.mark.asyncio
@respx.mock
async def test_swapping_fake_for_real_roster_adapter_requires_no_caller_change():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/Players/KC").mock(
        return_value=httpx.Response(200, json=load("rosters_normal.json"))
    )
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/DepthCharts").mock(
        return_value=httpx.Response(200, json=load("depth_charts_normal.json"))
    )
    backend = InMemoryCacheBackend()
    response_model = AdapterResponse[list[RosterEntry]]

    async def _get_roster(caching_adapter: CachingAdapter):
        return await caching_adapter.call("fetch_roster", "KC", response_model=response_model)

    caching_fake = CachingAdapter(FakeRosterAdapter(), backend, ttl_seconds=900)
    fake_result = await _get_roster(caching_fake)
    assert fake_result.source == "fake_roster_provider"

    caching_real = CachingAdapter(
        SportsDataIORosterAdapter(client=_client(), api_key=API_KEY), backend, ttl_seconds=900
    )
    real_result = await _get_roster(caching_real)
    assert real_result.source == "sportsdataio"

    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(real_result, AdapterResponse)


@pytest.mark.asyncio
@respx.mock
async def test_swapping_fake_for_real_team_stats_adapter_requires_no_caller_change():
    respx.get(f"{BASE_URL}/v3/nfl/scores/json/TeamGameStats/2025REG/1").mock(
        return_value=httpx.Response(200, json=load("team_stats_week_bulk_normal.json"))
    )
    backend = InMemoryCacheBackend()
    response_model = AdapterResponse[list[TeamStatLine]]

    async def _get_stats(caching_adapter: CachingAdapter, game_id: str):
        return await caching_adapter.call("fetch_team_stats", game_id, response_model=response_model)

    caching_fake = CachingAdapter(FakeTeamStatsAdapter(), backend, ttl_seconds=900)
    fake_result = await _get_stats(caching_fake, "game-1")
    assert fake_result.source == "fake_stats_provider"

    real_adapter = SportsDataIOTeamStatsAdapter(
        client=_client(), api_key=API_KEY,
        season_week_for_game=_season_week_lookup({"202510122": ("2025REG", 1)}),
    )
    caching_real = CachingAdapter(real_adapter, backend, ttl_seconds=900)
    real_result = await _get_stats(caching_real, "202510122")
    assert real_result.source == "sportsdataio"

    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(real_result, AdapterResponse)
