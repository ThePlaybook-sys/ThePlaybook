"""DEMO-2 tests (docs/blueprint/demo-simulation-environment.md Section 17 --
adapter conformance, isolation, and swap tests, mirroring the same discipline
every real vendor adapter in this project has already been held to).

Covers: conformance against the shared ABCs, normalized-model-type parity
with real adapters, deterministic input->output, empty/multiple-record
behavior, constructor-injected data, structural absence of any HTTP client
or provider credential, zero coupling between app/demo/ and
app/adapters/providers/, and a caller-side vendor-swap test proving a
Demo*Adapter is interchangeable with a real adapter behind the shared
interface.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.adapters.cache import CachingAdapter, InMemoryCacheBackend
from app.adapters.errors import ProviderUnavailableError
from app.adapters.models import (
    AdapterResponse,
    InjuryReport,
    NewsArticle,
    OddsLine,
    PlayerProp,
    PlayerStatLine,
    RosterEntry,
    ScheduleEntry,
    TeamStatLine,
    WeatherConditions,
)
from app.demo import adapters as demo_adapters_module
from app.demo import starter_data
from app.demo.adapters import (
    DemoInjuryAdapter,
    DemoNewsAdapter,
    DemoOddsAdapter,
    DemoPlayerPropsAdapter,
    DemoPlayerStatsAdapter,
    DemoRosterAdapter,
    DemoScheduleAdapter,
    DemoTeamStatsAdapter,
    DemoWeatherAdapter,
)
from tests.adapters.conformance import (
    assert_adapter_identity,
    assert_raises_provider_error,
    assert_returns_envelope,
)
from tests.adapters.fakes import FakeOddsAdapterV1

# Every (adapter instance, fetch method name, args, expected element type) case,
# covering all 9 categories in one parametrized sweep for the conformance /
# model-parity / determinism / empty-input checks that apply identically to
# each of them.
_CASES = [
    (DemoOddsAdapter(), "fetch_odds", ([starter_data.GAME_1, starter_data.GAME_2],), OddsLine),
    (DemoPlayerPropsAdapter(), "fetch_player_props", ([starter_data.GAME_1],), PlayerProp),
    (DemoInjuryAdapter(), "fetch_injuries", (None,), InjuryReport),
    (DemoRosterAdapter(), "fetch_roster", (starter_data.HAWKS,), RosterEntry),
    (DemoScheduleAdapter(), "fetch_schedule", ("demo-season-2026",), ScheduleEntry),
    (DemoNewsAdapter(), "fetch_news", (None,), NewsArticle),
    (DemoTeamStatsAdapter(), "fetch_team_stats", (starter_data.GAME_1,), TeamStatLine),
    (DemoPlayerStatsAdapter(), "fetch_player_stats", (starter_data.GAME_1,), PlayerStatLine),
]


@pytest.mark.parametrize("adapter,method_name,args,element_type", _CASES)
@pytest.mark.asyncio
async def test_conformance_identity_and_envelope(adapter, method_name, args, element_type):
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(adapter, method_name, *args)
    assert isinstance(response.value, list)
    assert len(response.value) > 0, "starter data should produce at least one record for this case"
    assert all(isinstance(item, element_type) for item in response.value)


@pytest.mark.asyncio
async def test_weather_adapter_conformance_and_singular_envelope():
    # WeatherAdapter returns a singular WeatherConditions, not a list --
    # kept out of the parametrized sweep above since its shape differs.
    from datetime import datetime, timezone

    adapter = DemoWeatherAdapter()
    assert_adapter_identity(adapter)
    response = await assert_returns_envelope(
        adapter, "fetch_weather", starter_data.GAME_1, datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)
    )
    assert isinstance(response.value, WeatherConditions)


@pytest.mark.parametrize("adapter,method_name,args,element_type", _CASES)
@pytest.mark.asyncio
async def test_deterministic_input_produces_deterministic_output(adapter, method_name, args, element_type):
    method = getattr(adapter, method_name)
    first = await method(*args)
    second = await method(*args)
    assert first.value == second.value


@pytest.mark.asyncio
async def test_empty_game_list_returns_empty_odds():
    response = await DemoOddsAdapter().fetch_odds([])
    assert response.value == []


@pytest.mark.asyncio
async def test_empty_game_list_returns_empty_player_props():
    response = await DemoPlayerPropsAdapter().fetch_player_props([])
    assert response.value == []


@pytest.mark.asyncio
async def test_unknown_team_returns_empty_roster_not_an_error():
    response = await DemoRosterAdapter().fetch_roster("Team Nobody Seeded")
    assert response.value == []


@pytest.mark.asyncio
async def test_unknown_game_returns_empty_team_stats_not_an_error():
    response = await DemoTeamStatsAdapter().fetch_team_stats("game-that-does-not-exist")
    assert response.value == []


@pytest.mark.asyncio
async def test_multiple_games_returns_records_from_every_game():
    response = await DemoOddsAdapter().fetch_odds([starter_data.GAME_1, starter_data.GAME_2])
    game_ids_present = {line.game_external_id for line in response.value}
    assert game_ids_present == {starter_data.GAME_1, starter_data.GAME_2}


@pytest.mark.asyncio
async def test_injury_filter_by_team_narrows_results():
    all_reports = (await DemoInjuryAdapter().fetch_injuries(None)).value
    hawks_reports = (await DemoInjuryAdapter().fetch_injuries(starter_data.HAWKS)).value
    assert len(hawks_reports) <= len(all_reports)
    assert all(r.team == starter_data.HAWKS for r in hawks_reports)


@pytest.mark.asyncio
async def test_news_filter_by_team_narrows_results():
    all_articles = (await DemoNewsAdapter().fetch_news(None)).value
    wolves_articles = (await DemoNewsAdapter().fetch_news(starter_data.WOLVES)).value
    assert len(wolves_articles) <= len(all_articles)
    assert all(starter_data.WOLVES in a.related_teams for a in wolves_articles)


# --- Constructor-injected data (the DEMO-3 connection point) ---------------

@pytest.mark.asyncio
async def test_constructor_injected_odds_data_overrides_the_default_starter_set():
    injected = OddsLine(
        game_external_id="scenario-game-x", home_team="Injected Home", away_team="Injected Away",
        commence_time=starter_data.KICKOFF_1, sportsbook="ScenarioBook", market_type="moneyline",
        line_data={"home": -200, "away": 175},
    )
    adapter = DemoOddsAdapter(odds_by_game={"scenario-game-x": [injected]})
    response = await adapter.fetch_odds(["scenario-game-x"])
    assert response.value == [injected]
    # The default starter game must NOT leak through once real data was injected.
    default_leak = await adapter.fetch_odds([starter_data.GAME_1])
    assert default_leak.value == []


@pytest.mark.asyncio
async def test_constructor_injected_fail_flag_raises_provider_unavailable_error():
    adapter = DemoOddsAdapter(fail=True)
    await assert_raises_provider_error(adapter, "fetch_odds", [starter_data.GAME_1])
    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch_odds([starter_data.GAME_1])


@pytest.mark.asyncio
async def test_every_demo_adapter_accepts_a_fail_flag_and_raises_provider_error():
    failing_cases = [
        (DemoOddsAdapter(fail=True), "fetch_odds", ([starter_data.GAME_1],)),
        (DemoPlayerPropsAdapter(fail=True), "fetch_player_props", ([starter_data.GAME_1],)),
        (DemoInjuryAdapter(fail=True), "fetch_injuries", (None,)),
        (DemoWeatherAdapter(fail=True), "fetch_weather", (starter_data.GAME_1, starter_data.KICKOFF_1)),
        (DemoRosterAdapter(fail=True), "fetch_roster", (starter_data.HAWKS,)),
        (DemoScheduleAdapter(fail=True), "fetch_schedule", ("demo-season-2026",)),
        (DemoNewsAdapter(fail=True), "fetch_news", (None,)),
        (DemoTeamStatsAdapter(fail=True), "fetch_team_stats", (starter_data.GAME_1,)),
        (DemoPlayerStatsAdapter(fail=True), "fetch_player_stats", (starter_data.GAME_1,)),
    ]
    for adapter, method_name, args in failing_cases:
        await assert_raises_provider_error(adapter, method_name, *args)


# --- Structural isolation: no HTTP client, no provider credential ----------

_DEMO_SOURCE_FILES = [
    Path(inspect.getfile(demo_adapters_module)),
    Path(inspect.getfile(starter_data)),
]

_FORBIDDEN_HTTP_IMPORTS = {"httpx", "requests", "aiohttp", "urllib3", "http.client"}
_FORBIDDEN_CREDENTIAL_NAMES = [
    "SPORTSDATAIO_API_KEY", "SPORTSDATAIO_DIAGNOSTIC_TOKEN", "THE_ODDS_API_KEY",
    "WEATHERAPI_API_KEY", "NEWSAPI_API_KEY", "GNEWS_API_KEY",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TELEGRAM_BOT_TOKEN",
    "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_URL",
]


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_demo_module_imports_no_http_client_library():
    for path in _DEMO_SOURCE_FILES:
        imported = _imported_module_names(path.read_text())
        overlap = imported & _FORBIDDEN_HTTP_IMPORTS
        assert not overlap, f"{path} imports forbidden HTTP client(s): {overlap}"


def test_demo_module_references_no_provider_or_credential_env_var_by_name():
    for path in _DEMO_SOURCE_FILES:
        source = path.read_text()
        assert "os.environ" not in source and "getenv" not in source, (
            f"{path} should never read environment variables at all"
        )
        for name in _FORBIDDEN_CREDENTIAL_NAMES:
            assert name not in source, f"{path} references forbidden credential name {name!r}"


def test_demo_adapters_construct_with_zero_arguments_and_never_touch_a_network():
    # If any of these secretly needed a live connection, constructing them
    # with no args (using only starter data) would be the first thing to fail.
    DemoOddsAdapter()
    DemoPlayerPropsAdapter()
    DemoInjuryAdapter()
    DemoWeatherAdapter()
    DemoRosterAdapter()
    DemoScheduleAdapter()
    DemoNewsAdapter()
    DemoTeamStatsAdapter()
    DemoPlayerStatsAdapter()


# --- Zero coupling between app/demo/ and the real provider adapters --------

def test_demo_package_does_not_import_real_provider_implementations():
    for path in _DEMO_SOURCE_FILES:
        imported_from = path.read_text()
        assert "app.adapters.providers" not in imported_from, (
            f"{path} must never depend on a real vendor adapter implementation"
        )


def test_real_provider_modules_do_not_import_app_demo():
    providers_dir = Path(demo_adapters_module.__file__).resolve().parents[1] / "adapters" / "providers"
    provider_files = sorted(providers_dir.glob("*.py"))
    assert provider_files, "expected at least one real provider adapter file to check"
    for path in provider_files:
        source = path.read_text()
        assert "app.demo" not in source, f"{path} must never depend on app.demo"


# --- Caller-side vendor swap: Demo is interchangeable with a real/fake adapter ---

ODDS_RESPONSE_MODEL = AdapterResponse[list[OddsLine]]


async def _get_odds(caching_adapter: CachingAdapter, game_external_id: str):
    """Caller-side code, written once against the interface -- identical
    regardless of which adapter (fake, real, or demo) sits behind it,
    mirroring tests/adapters/test_transport_swap.py's own precedent."""
    return await caching_adapter.call(
        "fetch_odds", [game_external_id], response_model=ODDS_RESPONSE_MODEL
    )


@pytest.mark.asyncio
async def test_swapping_a_fake_adapter_for_a_demo_adapter_requires_no_caller_change():
    backend = InMemoryCacheBackend()

    caching_fake = CachingAdapter(FakeOddsAdapterV1(), backend, ttl_seconds=60)
    fake_result = await _get_odds(caching_fake, "game-1")
    assert fake_result.source == "fake_provider_v1"

    caching_demo = CachingAdapter(DemoOddsAdapter(), backend, ttl_seconds=60)
    demo_result = await _get_odds(caching_demo, starter_data.GAME_1)
    assert demo_result.source == "demo"
    assert demo_result.value[0].sportsbook == "DemoBook"

    # Same call site (_get_odds), same response envelope type -- the only
    # difference between the two blocks above is which adapter instance was
    # constructed, exactly the property Rule 1 requires.
    assert isinstance(fake_result, AdapterResponse)
    assert isinstance(demo_result, AdapterResponse)
