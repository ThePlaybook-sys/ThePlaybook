"""Integration tests for app.demo.runner.ScenarioRunner (DEMO-3).

Exercises the full chain the approved architecture describes: Scenario
Runner -> virtual_now -> Demo*Adapter built from scripted step data ->
the REAL worker entrypoints (via the DEMO-3 adapter-injection seam) -> the
REAL persistence layer -> an in-memory fake Supabase
(`tests/demo/fake_supabase.py`) standing in for the isolated demo project.
Nothing here re-implements a worker or a persistence function; every
assertion checks what actually landed in the fake store after a real
worker call, exactly as a live demo Supabase read would.
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


def _seed_reference_taxonomy(fake: FakeSupabase) -> None:
    """Exactly the reference-taxonomy subset every environment's
    supabase/seed.sql already bootstraps for these two real teams --
    never touched by reset, never scenario-authored."""
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


@pytest.mark.asyncio
@respx.mock
async def test_minimal_scenario_runs_to_completion_with_no_step_errors(monkeypatch):
    fake = _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        try:
            runner.load(scenario)
            outcomes = await runner.run_to_completion()
        finally:
            await runner.aclose()

    errors = [o for o in outcomes if o.error]
    assert errors == [], f"scenario steps raised: {errors}"
    assert runner.status == "completed"
    assert len(outcomes) == len(scenario.steps)
    assert runner.checkpoints == [step.checkpoint_note for step in scenario.steps if step.checkpoint_note]

    assert len(fake.tables.get("games", [])) == 1
    game = fake.tables["games"][0]
    assert game["home_team"] == "KC" and game["away_team"] == "BAL"
    assert game["status"] == "final"
    assert game["finalized_at"] is not None
    assert game["final_score"] == {"home": 27, "away": 24}

    assert len(fake.tables.get("players", [])) == 2
    assert len(fake.tables.get("odds_snapshots", [])) >= 1
    assert any(row["market_type"] == "prop" for row in fake.tables.get("odds_snapshots", []))
    # 2, not 1: the standalone injury_worker step (questionable) plus
    # pregame_worker's own T-minus-5 injury re-poll (upgraded to out) --
    # injury_reports is append-only, every poll writes a new row.
    assert len(fake.tables.get("injury_reports", [])) == 2
    assert len(fake.tables.get("team_stats", [])) == 2
    assert len(fake.tables.get("player_stats", [])) == 2

    dgi_rows = fake.tables.get("daily_game_intelligence", [])
    assert len(dgi_rows) == 1
    dgi = dgi_rows[0]
    assert dgi["game_id"] == game["id"]
    assert dgi["odds"] is not None
    assert dgi["injuries"] is not None
    assert dgi["news"] is not None


@pytest.mark.asyncio
@respx.mock
async def test_run_next_step_advances_one_step_at_a_time_and_moves_virtual_now(monkeypatch):
    _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        assert runner.virtual_now == scenario.initial_virtual_now
        assert runner.status == "loaded"

        first = await runner.run_next_step()
        assert first.step_index == 0
        assert runner.virtual_now == scenario.steps[0].virtual_now
        assert runner.step_index == 1
        assert not runner.is_finished

        await runner.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_no_real_provider_client_is_ever_contacted(monkeypatch):
    """Structural proof, mirroring test_adapter_injection_seam.py: the
    placeholder client every worker call receives points nowhere real and
    has zero registered route -- if a worker ever fell through to
    constructing its real vendor adapter despite an injected Demo*Adapter,
    the very first attempted call would raise, not silently succeed."""
    _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        outcomes = await runner.run_to_completion()
        await runner.aclose()

    assert [o.error for o in outcomes] == [None] * len(outcomes)


@pytest.mark.asyncio
@respx.mock
async def test_provider_failure_injection_produces_a_partial_or_failed_worker_result(monkeypatch):
    _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")
    # DEMO-2's fail=True mechanism, driven from inject_failure -- the odds step.
    scenario.steps[1].inject_failure = True

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        outcomes = await runner.run_to_completion()
        await runner.aclose()

    odds_outcome = outcomes[1]
    assert odds_outcome.error is None  # the worker itself never raises...
    assert odds_outcome.result.status in {"partial", "failed"}  # ...it reports failure instead


@pytest.mark.asyncio
@respx.mock
async def test_deterministic_replay_same_scenario_same_baseline_same_persisted_state(monkeypatch):
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

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

    # game_id/player_id/team_id/id are freshly-generated UUIDs each run
    # (not stable across two independent scenario runs, even though what
    # they *point at* is identical -- including nested inside
    # daily_game_intelligence's own players/odds/injuries jsonb blobs);
    # captured_at/created_at/observed_at/last_updated are insertion-order
    # timestamps, not scenario data. Deterministic replay means the DATA
    # content matches, not that generated identifiers or wall-clock-like
    # bookkeeping do -- so both are stripped recursively before comparing.
    _NON_DETERMINISTIC_FIELDS = {
        "id", "game_id", "player_id", "team_id", "captured_at", "created_at", "observed_at", "last_updated",
    }

    def _normalize(value):
        if isinstance(value, dict):
            return {k: _normalize(v) for k, v in value.items() if k not in _NON_DETERMINISTIC_FIELDS}
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    for table in ("odds_snapshots", "injury_reports", "team_stats", "player_stats", "daily_game_intelligence"):
        rows_a = sorted(_normalize(fake_a.tables.get(table, [])), key=str)
        rows_b = sorted(_normalize(fake_b.tables.get(table, [])), key=str)
        assert rows_a == rows_b, f"table {table!r} diverged between two runs of the same scenario"


@pytest.mark.asyncio
async def test_reset_after_a_scenario_run_clears_operational_data_but_preserves_reference_taxonomy(monkeypatch):
    with respx.mock:
        fake = _new_fake(monkeypatch)
        scenario = load_bundled_scenario("minimal_pregame_to_postgame")
        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            runner = ScenarioRunner(supabase_client=client)
            runner.load(scenario)
            await runner.run_to_completion()
            await runner.aclose()

        assert fake.tables.get("games")
        assert fake.tables.get("players")

        async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
            counts = await reset_demo_operational_data(
                client, _headers(),
                railway_environment_name=DEMO_ENVIRONMENT_NAME,
                supabase_url=SUPABASE_URL,
            )

    assert counts["games"] == 1
    assert counts["players"] == 2
    for table in PRESERVED_REFERENCE_TAXONOMY:
        assert len(fake.tables.get(table, [])) > 0, f"{table!r} should have survived reset untouched"
    assert fake.tables["games"] == []
    assert fake.tables["players"] == []
    assert fake.tables["odds_snapshots"] == []
    assert fake.tables["daily_game_intelligence"] == []


@pytest.mark.asyncio
@respx.mock
async def test_advance_time_step_moves_virtual_now_without_invoking_any_worker(monkeypatch):
    from app.demo.scenario import Scenario, ScenarioStep

    _new_fake(monkeypatch)
    scenario = Scenario(
        scenario_id="advance-only", title="t", description="d", version="1.0.0",
        phase_requirements=["phase_3"],
        initial_virtual_now=__import__("datetime").datetime(2026, 9, 14, 12, 0, tzinfo=__import__("datetime").timezone.utc),
        slate={},
        steps=[
            ScenarioStep(
                virtual_now=__import__("datetime").datetime(2026, 9, 14, 15, 0, tzinfo=__import__("datetime").timezone.utc),
                action="advance_time",
            ),
        ],
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        outcome = await runner.run_next_step()
        await runner.aclose()

    assert outcome.error is None
    assert outcome.result is None
    assert runner.virtual_now == scenario.steps[0].virtual_now


@pytest.mark.asyncio
@respx.mock
async def test_runner_never_reads_the_wall_clock(monkeypatch):
    """A scenario dated far in the past still runs correctly -- proves
    virtual_now, not datetime.now(), drives every worker's window/cadence
    logic. If any worker path fell back to the real wall clock, a
    virtual_now this far from "now" would push every game outside every
    worker's 7-day candidate window and silently persist nothing."""
    fake = _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        outcomes = await runner.run_to_completion()
        await runner.aclose()

    assert [o.error for o in outcomes] == [None] * len(outcomes)
    assert fake.tables.get("games")
    assert fake.tables.get("odds_snapshots")


@pytest.mark.asyncio
@respx.mock
async def test_placeholder_client_receives_zero_calls_and_no_real_credential_is_used(monkeypatch):
    """Strengthens the structural adapter-injection proof: not just "no
    error", but the placeholder client -- which every worker call
    receives for its required-but-unused vendor client param -- is
    verified to have made exactly zero requests, and the placeholder key
    string is never a real credential."""
    from app.demo.runner import UNREACHABLE_PLACEHOLDER_URL, UNUSED_PLACEHOLDER_KEY

    _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        await runner.run_to_completion()
        placeholder_calls = [
            call for call in respx.calls if call.request.url.host == httpx.URL(UNREACHABLE_PLACEHOLDER_URL).host
        ]
        await runner.aclose()

    assert placeholder_calls == []
    assert UNUSED_PLACEHOLDER_KEY == "demo-unused-placeholder-key"
    assert "sk-" not in UNUSED_PLACEHOLDER_KEY  # not shaped like a real API key


@pytest.mark.asyncio
@respx.mock
async def test_event_injection_line_move_and_injury_upgrade_are_both_visible_in_persisted_history(monkeypatch):
    """DEMO-3's approved 'event injection' requirement: a later step's
    changed provider data (the pregame step's line move and injury
    upgrade) must actually change downstream persisted state, not just
    run without erroring."""
    fake = _new_fake(monkeypatch)
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        runner = ScenarioRunner(supabase_client=client)
        runner.load(scenario)
        await runner.run_to_completion()
        await runner.aclose()

    moneylines = [
        row for row in fake.tables["odds_snapshots"] if row["market_type"] == "moneyline"
    ]
    home_lines = sorted(row["line_data"]["home"] for row in moneylines)
    assert home_lines == [-125, -120]  # opening line, then the pregame move

    injury_statuses = sorted(row["report_data"]["status"] for row in fake.tables["injury_reports"])
    assert injury_statuses == ["out", "questionable"]  # questionable, then upgraded to out


@pytest.mark.asyncio
async def test_scenario_can_be_re_run_after_reset_reaching_the_same_baseline(monkeypatch):
    scenario = load_bundled_scenario("minimal_pregame_to_postgame")

    with respx.mock:
        fake = _new_fake(monkeypatch)

        async def _run_and_reset():
            async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
                runner = ScenarioRunner(supabase_client=client)
                runner.load(scenario)
                await runner.run_to_completion()
                await runner.aclose()
            async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
                return await reset_demo_operational_data(
                    client, _headers(),
                    railway_environment_name=DEMO_ENVIRONMENT_NAME,
                    supabase_url=SUPABASE_URL,
                )

        first_counts = await _run_and_reset()
        second_counts = await _run_and_reset()

    assert first_counts == second_counts
