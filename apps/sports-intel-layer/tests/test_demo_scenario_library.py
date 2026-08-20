"""Integration tests for DEMO-5's four new scenarios (Pregame Intelligence
Evolution, Team News: Injury & Depth Chart Change, Provider Outage
Resilience, Postgame Stat Correction) -- same discipline as
test_demo_scenario_runner.py: real ScenarioRunner, real worker
entrypoints, real persistence layer, an in-memory fake Supabase standing
in for the isolated demo project. Every assertion checks what actually
landed in the fake store, not what the code is expected to do.

Deterministic replay and reset-to-baseline are proven once, parametrized
across all four scenarios, rather than duplicated per scenario -- both are
runner/reset-layer guarantees, not scenario-specific behavior, and
DEMO-3's own test suite already proves them in depth for the baseline
scenario.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.demo.reset import PRESERVED_REFERENCE_TAXONOMY, reset_demo_operational_data
from app.demo.runner import ScenarioRunner
from app.demo.scenarios import load_bundled_scenario
from app.environment_safety import DEMO_ENVIRONMENT_NAME, DEMO_SUPABASE_PROJECT_REF
from tests.demo.fake_supabase import FakeSupabase

SUPABASE_URL = f"https://{DEMO_SUPABASE_PROJECT_REF}.supabase.co"

TEAM_KC = "team-kc-0000-0000-0000-000000000001"
TEAM_BAL = "team-bal-0000-0000-0000-000000000002"

NEW_SCENARIO_NAMES = [
    "pregame_intelligence_evolution",
    "team_news_injury_depth_chart",
    "provider_outage_resilience",
    "postgame_stat_correction",
]


def _seed_reference_taxonomy(fake: FakeSupabase) -> None:
    fake.seed("sports", [{"id": "sport-football", "name": "football"}])
    fake.seed("leagues", [{"id": "league-nfl", "code": "nfl"}])
    fake.seed(
        "seasons",
        [{"year": 2026, "league_id": "league-nfl", "start_date": "2026-09-04", "end_date": "2027-02-14"}],
    )
    fake.seed("teams", [{"id": TEAM_KC, "name": "Kansas City Chiefs"}, {"id": TEAM_BAL, "name": "Baltimore Ravens"}])
    fake.seed(
        "team_provider_ids",
        [
            {"team_id": TEAM_KC, "provider_name": "the_odds_api", "provider_team_id": "Kansas City Chiefs"},
            {"team_id": TEAM_KC, "provider_name": "sportsdataio", "provider_team_id": "KC"},
            {"team_id": TEAM_BAL, "provider_name": "the_odds_api", "provider_team_id": "Baltimore Ravens"},
            {"team_id": TEAM_BAL, "provider_name": "sportsdataio", "provider_team_id": "BAL"},
        ],
    )


def _new_fake(monkeypatch) -> FakeSupabase:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    fake = FakeSupabase()
    _seed_reference_taxonomy(fake)
    fake.register_routes(SUPABASE_URL)
    return fake


def _headers() -> dict:
    return {"Authorization": "Bearer test-service-role-key", "apikey": "test-service-role-key", "Content-Type": "application/json"}


async def _run_scenario(monkeypatch, name: str):
    fake = _new_fake(monkeypatch)
    scenario = load_bundled_scenario(name)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        outcomes = await runner.run_to_completion()
        await runner.aclose()
    return fake, scenario, runner, outcomes


# -- Pregame Intelligence Evolution --

@pytest.mark.asyncio
@respx.mock
async def test_pregame_evolution_runs_clean_and_progresses_virtual_time(monkeypatch):
    fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, "pregame_intelligence_evolution")

    errors = [o for o in outcomes if o.error]
    assert errors == [], f"steps raised: {errors}"
    assert runner.status == "completed"
    assert runner.virtual_now == scenario.steps[-1].virtual_now
    assert [o.virtual_now for o in outcomes] == [s.virtual_now for s in scenario.steps]


@pytest.mark.asyncio
@respx.mock
async def test_pregame_evolution_odds_and_props_are_append_only_not_overwritten(monkeypatch):
    fake, *_ = await _run_scenario(monkeypatch, "pregame_intelligence_evolution")

    moneylines = [row for row in fake.tables["odds_snapshots"] if row["market_type"] == "moneyline"]
    props = [row for row in fake.tables["odds_snapshots"] if row["market_type"] == "prop"]
    assert sorted(row["line_data"]["home"] for row in moneylines) == [-145, -120]
    assert sorted(row["line_data"]["line"] for row in props) == [1.5, 2.5]

    weather_rows = fake.tables["weather_snapshots"]
    assert len(weather_rows) == 2
    assert sorted(row["weather_data"]["conditions"] for row in weather_rows) == ["clear", "rain"]


@pytest.mark.asyncio
@respx.mock
async def test_pregame_evolution_weather_freshness_flips_to_stale_after_the_long_gap(monkeypatch):
    """The scenario's own point: 80 real minutes pass with no further
    weather poll after the second (14:10) snapshot -- well past the
    confirmed 900-second weather TTL -- so the final daily_game_intelligence
    reassembly (15:30) must record the weather category as no longer
    fresh."""
    fake, *_ = await _run_scenario(monkeypatch, "pregame_intelligence_evolution")

    dgi = fake.tables["daily_game_intelligence"][0]
    assert dgi["weather"] is not None
    assert dgi["weather"]["status"] != "fresh"


# -- Team News: Injury & Depth Chart Change --

@pytest.mark.asyncio
@respx.mock
async def test_team_news_runs_clean(monkeypatch):
    fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, "team_news_injury_depth_chart")

    errors = [o for o in outcomes if o.error]
    assert errors == [], f"steps raised: {errors}"
    assert runner.status == "completed"


@pytest.mark.asyncio
@respx.mock
async def test_team_news_injury_history_is_append_only(monkeypatch):
    fake, *_ = await _run_scenario(monkeypatch, "team_news_injury_depth_chart")

    statuses = sorted(row["report_data"]["status"] for row in fake.tables["injury_reports"])
    assert statuses == ["out", "questionable"]


@pytest.mark.asyncio
@respx.mock
async def test_team_news_depth_chart_snapshots_are_written_unconditionally_every_poll(monkeypatch):
    """depth_chart_snapshots is written once per team per Master Refresh
    call, every time, regardless of whether that team's roster content
    changed this call -- two master_refresh steps x two teams = 4 rows."""
    fake, *_ = await _run_scenario(monkeypatch, "team_news_injury_depth_chart")

    assert len(fake.tables["depth_chart_snapshots"]) == 4


@pytest.mark.asyncio
@respx.mock
async def test_team_news_roster_membership_only_changes_for_the_player_who_actually_changed_teams(monkeypatch):
    """The two QBs are observed with the same team both times -- one
    membership row each, never a second. The shared WR is observed with
    BAL first, then KC -- two distinct membership rows, since the
    OBSERVED team genuinely differs from the LATEST known one. This is
    the exact distinction 'insert-on-change' means, proven against real
    persistence, not asserted from the docstring."""
    fake, *_ = await _run_scenario(monkeypatch, "team_news_injury_depth_chart")

    memberships = fake.tables["roster_memberships"]
    assert len(memberships) == 4  # KC QB (1) + BAL QB (1) + shared WR (2)

    by_player = {}
    for row in memberships:
        by_player.setdefault(row["player_id"], []).append(row["team_id"])

    membership_counts = sorted(len(teams) for teams in by_player.values())
    assert membership_counts == [1, 1, 2]


# -- Provider Outage Resilience --

@pytest.mark.asyncio
@respx.mock
async def test_outage_injury_category_fails_others_succeed(monkeypatch):
    fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, "provider_outage_resilience")

    pregame_outcome = outcomes[-1]
    assert pregame_outcome.error is None  # the worker itself never raises...
    assert pregame_outcome.result.status == "partial"  # ...it reports partial instead
    assert any("injury" in failure for failure in pregame_outcome.result.category_failures)


@pytest.mark.asyncio
@respx.mock
async def test_outage_odds_props_weather_still_persisted_despite_injury_outage(monkeypatch):
    fake, *_ = await _run_scenario(monkeypatch, "provider_outage_resilience")

    assert len(fake.tables["odds_snapshots"]) >= 2  # moneyline + prop
    assert len(fake.tables["weather_snapshots"]) == 1
    assert fake.tables.get("injury_reports", []) == []  # the simulated outage: zero rows


@pytest.mark.asyncio
@respx.mock
async def test_outage_daily_game_intelligence_still_refreshes_for_succeeding_categories(monkeypatch):
    fake, *_ = await _run_scenario(monkeypatch, "provider_outage_resilience")

    dgi = fake.tables["daily_game_intelligence"][0]
    assert dgi["odds"] is not None
    assert dgi["weather"] is not None


# -- Postgame Stat Correction --

@pytest.mark.asyncio
@respx.mock
async def test_postgame_correction_runs_clean(monkeypatch):
    fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, "postgame_stat_correction")

    errors = [o for o in outcomes if o.error]
    assert errors == [], f"steps raised: {errors}"
    assert runner.status == "completed"


@pytest.mark.asyncio
@respx.mock
async def test_postgame_correction_only_the_changed_team_and_player_gain_a_second_row(monkeypatch):
    """KC's stats genuinely changed between the two postgame_worker calls
    (Score 27->30, total_yards 350->365) -- a second row. BAL's stats were
    re-fetched IDENTICAL both times -- no second row. Same distinction for
    the two players: the KC QB's passing_yards changed (240->255), the
    BAL QB's did not."""
    fake, *_ = await _run_scenario(monkeypatch, "postgame_stat_correction")

    team_stats_by_team_id = {}
    for row in fake.tables["team_stats"]:
        team_stats_by_team_id.setdefault(row["team_id"], []).append(row["stats"])
    team_row_counts = sorted(len(rows) for rows in team_stats_by_team_id.values())
    assert team_row_counts == [1, 2]  # BAL unchanged (1), KC corrected (2)

    player_stats_by_player_id = {}
    for row in fake.tables["player_stats"]:
        player_stats_by_player_id.setdefault(row["player_id"], []).append(row["stats"])
    player_row_counts = sorted(len(rows) for rows in player_stats_by_player_id.values())
    assert player_row_counts == [1, 2]  # BAL QB unchanged (1), KC QB corrected (2)


@pytest.mark.asyncio
@respx.mock
async def test_postgame_correction_final_score_is_updated_to_reflect_the_correction(monkeypatch):
    fake, *_ = await _run_scenario(monkeypatch, "postgame_stat_correction")

    game = fake.tables["games"][0]
    assert game["final_score"] == {"home": 30, "away": 24}  # not the original {27, 24}


# -- Cross-cutting: deterministic replay + reset-to-baseline, all four new scenarios --

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", NEW_SCENARIO_NAMES)
async def test_deterministic_replay(monkeypatch, scenario_name):
    scenario = load_bundled_scenario(scenario_name)

    async def _run_once():
        fake = _new_fake(monkeypatch)
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            runner = ScenarioRunner(supabase_client=client)
            runner.load(scenario)
            await runner.run_to_completion()
            await runner.aclose()
        return fake

    with respx.mock:
        fake_a = await _run_once()
    with respx.mock:
        fake_b = await _run_once()

    _NON_DETERMINISTIC_FIELDS = {
        "id", "game_id", "player_id", "team_id", "captured_at", "created_at", "observed_at", "last_updated",
    }

    def _normalize(value):
        if isinstance(value, dict):
            return {k: _normalize(v) for k, v in value.items() if k not in _NON_DETERMINISTIC_FIELDS}
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    all_tables = set(fake_a.tables) | set(fake_b.tables)
    for table in all_tables:
        rows_a = sorted(_normalize(fake_a.tables.get(table, [])), key=str)
        rows_b = sorted(_normalize(fake_b.tables.get(table, [])), key=str)
        assert rows_a == rows_b, f"{scenario_name}: table {table!r} diverged between two runs"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", NEW_SCENARIO_NAMES)
async def test_reset_returns_to_baseline_and_preserves_reference_taxonomy(monkeypatch, scenario_name):
    with respx.mock:
        fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, scenario_name)
        assert not [o for o in outcomes if o.error]

        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            await reset_demo_operational_data(
                client, _headers(),
                railway_environment_name=DEMO_ENVIRONMENT_NAME,
                supabase_url=SUPABASE_URL,
            )

    for table in PRESERVED_REFERENCE_TAXONOMY:
        assert len(fake.tables.get(table, [])) > 0, f"{scenario_name}: {table!r} should have survived reset"
    from app.demo.reset import RESET_TABLE_ORDER

    for table, _pk in RESET_TABLE_ORDER:
        assert fake.tables.get(table, []) == [], f"{scenario_name}: {table!r} should be empty after reset"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", NEW_SCENARIO_NAMES)
async def test_no_real_provider_client_is_ever_contacted(monkeypatch, scenario_name):
    from app.demo.runner import UNREACHABLE_PLACEHOLDER_URL

    with respx.mock:
        fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, scenario_name)
        placeholder_calls = [
            call for call in respx.calls if call.request.url.host == httpx.URL(UNREACHABLE_PLACEHOLDER_URL).host
        ]

    assert placeholder_calls == [], f"{scenario_name}: real vendor placeholder was contacted"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", NEW_SCENARIO_NAMES)
async def test_only_the_demo_supabase_url_is_ever_contacted(monkeypatch, scenario_name):
    """No cross-environment access: every respx call this run makes,
    across every host, resolves to either the fake demo Supabase host or
    the unreachable placeholder -- never anything else (a dev/staging/
    production URL, a real vendor host)."""
    with respx.mock:
        fake, scenario, runner, outcomes = await _run_scenario(monkeypatch, scenario_name)
        hosts_contacted = {call.request.url.host for call in respx.calls}

    allowed_hosts = {httpx.URL(SUPABASE_URL).host, "demo-adapter-injected.invalid"}
    assert hosts_contacted <= allowed_hosts, f"{scenario_name}: unexpected host(s) contacted: {hosts_contacted - allowed_hosts}"
