"""Demo provider adapters (DEMO-2, docs/blueprint/demo-simulation-environment.md
Section 8 -- "a `Demo*Adapter` family... implementing the same ABCs, returning
the current scenario step's scripted data instead of a real HTTP response").

Every class below implements one of the nine category ABCs in
`app/adapters/base.py` -- the exact same interfaces the real vendor adapters
(`app/adapters/providers/*.py`) implement. Nothing downstream (a worker, the
caching boundary, eventually an agent) can tell a `Demo*Adapter` apart from a
real one by type; only the data differs. This is Rule 1 of the approved Demo
design made concrete: Demo Mode replaces the provider, never the business
logic that consumes it.

Structural guarantee, not a convention: **this module imports no HTTP client
of any kind** (no `httpx`, `requests`, `aiohttp`, no provider SDK, no
provider URL, no provider credential). Every `fetch_*` method builds its
`AdapterResponse` directly from constructor-injected (or, if none was given,
small deterministic starter) in-memory data -- there is no code path here
that could ever reach a real vendor, even by misconfiguration.

Data-injection contract (the DEMO-3 connection point): every constructor
accepts its category's data as an optional keyword argument, defaulting to
`app.demo.starter_data`'s small fixed dataset when omitted. DEMO-3's
scenario runner is expected to construct these adapters itself, passing in
whatever the current scenario step's data should be, rather than this
module ever knowing about scenarios, steps, or a virtual clock. A `fail`
flag (mirroring the existing `tests/adapters/fakes.py` fakes' own
convention) lets a caller -- eventually the scenario runner -- deterministically
trigger the same `ProviderUnavailableError` path a real outage would.

`provider_name` (DEMO-3 addition, discovered necessary only once these
adapters were actually exercised end-to-end through the real persistence
layer, not a DEMO-2 design change): every constructor accepts an optional
`provider_name`, defaulting to `DEMO_PROVIDER_NAME` -- DEMO-2's own tests
never pass it and keep seeing `"demo"`, unchanged. The reason it exists at
all: several REAL persistence modules (`app.persistence.game_identity`,
`.team_identity`, and the workers' own inline reverse-resolvers) key
`game_provider_ids`/`team_provider_ids` rows by the literal vendor name
("sportsdataio", "the_odds_api") -- that string comes from
`AdapterResponse.source`, i.e. `adapter.provider_name`, not from a
category name. A `Demo*Adapter` that always reported `"demo"` would write
identity-linkage rows under a provider name none of those real,
unmodified lookups ever query for, silently breaking cross-worker
resolution (confirmed by the DEMO-3 scenario-runner integration test
before this was added -- see that test file's own note). The fix lives
entirely here, in the Demo adapter construction, not in any real
persistence module or worker: `app.demo.runner.ScenarioRunner` passes the
real vendor's own provider name for the categories where identity linkage
depends on it (schedule/roster/injury/team_stats/player_stats ->
"sportsdataio", odds/player_props -> "the_odds_api"), exactly mirroring
what `SportsDataIOScheduleAdapter`/`TheOddsApiOddsAdapter`/etc. already
report themselves.
"""
from __future__ import annotations

from datetime import datetime

from app.adapters.base import (
    InjuryAdapter,
    NewsAdapter,
    OddsAdapter,
    PlayerPropsAdapter,
    PlayerStatsAdapter,
    RosterAdapter,
    ScheduleAdapter,
    TeamStatsAdapter,
    WeatherAdapter,
)
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
from app.demo import starter_data

#: Default provider_name for every Demo*Adapter when a caller doesn't
#: override it -- surfaced only as AdapterResponse.source metadata (per
#: base.py's own docstring), never as part of the data itself.
DEMO_PROVIDER_NAME = "demo"


class DemoOddsAdapter(OddsAdapter):

    def __init__(
        self, *, odds_by_game: dict[str, list[OddsLine]] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._odds_by_game = odds_by_game if odds_by_game is not None else starter_data.default_odds_by_game()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        """Mirrors `TheOddsApiOddsAdapter.fetch_odds`'s own documented
        discovery-mode contract exactly (Phase 3E-4B/C): an empty
        `game_external_ids` returns every line across every scripted game,
        unfiltered -- the real bulk endpoint has no per-game filter and
        always returns the full slate, so Odds Worker's discovery-mode
        call (`fetch_odds([])`) depends on that exact behavior. A non-empty
        list filters to just those games, matching the real adapter's own
        post-fetch filtering for a targeted call."""
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        if not game_external_ids:
            lines = [line for game_lines in self._odds_by_game.values() for line in game_lines]
        else:
            lines = [line for game_id in game_external_ids for line in self._odds_by_game.get(game_id, [])]
        return AdapterResponse(value=lines, source=self.provider_name)


class DemoPlayerPropsAdapter(PlayerPropsAdapter):

    def __init__(
        self, *, props_by_game: dict[str, list[PlayerProp]] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._props_by_game = props_by_game if props_by_game is not None else starter_data.default_player_props_by_game()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_player_props(self, game_external_ids: list[str]) -> AdapterResponse[list[PlayerProp]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        props = [prop for game_id in game_external_ids for prop in self._props_by_game.get(game_id, [])]
        return AdapterResponse(value=props, source=self.provider_name)


class DemoInjuryAdapter(InjuryAdapter):

    def __init__(
        self, *, injuries: list[InjuryReport] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._injuries = injuries if injuries is not None else starter_data.default_injuries()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        reports = self._injuries if team is None else [r for r in self._injuries if r.team == team]
        return AdapterResponse(value=reports, source=self.provider_name)


class DemoWeatherAdapter(WeatherAdapter):

    def __init__(
        self, *, weather_by_game: dict[str, WeatherConditions] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._weather_by_game = weather_by_game if weather_by_game is not None else starter_data.default_weather_by_game()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_weather(self, game_external_id: str, kickoff: datetime) -> AdapterResponse[WeatherConditions]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        conditions = self._weather_by_game.get(
            game_external_id,
            WeatherConditions(game_external_id=game_external_id),
        )
        return AdapterResponse(value=conditions, source=self.provider_name)


class DemoRosterAdapter(RosterAdapter):

    def __init__(
        self, *, roster_by_team: dict[str, list[RosterEntry]] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._roster_by_team = roster_by_team if roster_by_team is not None else starter_data.default_roster_by_team()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        entries = self._roster_by_team.get(team, [])
        return AdapterResponse(value=entries, source=self.provider_name)


class DemoScheduleAdapter(ScheduleAdapter):

    def __init__(
        self, *, schedule: list[ScheduleEntry] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._schedule = schedule if schedule is not None else starter_data.default_schedule()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_schedule(self, season_external_id: str) -> AdapterResponse[list[ScheduleEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        return AdapterResponse(value=list(self._schedule), source=self.provider_name)


class DemoNewsAdapter(NewsAdapter):

    def __init__(
        self, *, articles: list[NewsArticle] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._articles = articles if articles is not None else starter_data.default_news()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        articles = self._articles if team is None else [a for a in self._articles if team in a.related_teams]
        return AdapterResponse(value=articles, source=self.provider_name)


class DemoTeamStatsAdapter(TeamStatsAdapter):

    def __init__(
        self, *, stats_by_game: dict[str, list[TeamStatLine]] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._stats_by_game = stats_by_game if stats_by_game is not None else starter_data.default_team_stats_by_game()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        lines = self._stats_by_game.get(game_external_id, [])
        return AdapterResponse(value=lines, source=self.provider_name)


class DemoPlayerStatsAdapter(PlayerStatsAdapter):

    def __init__(
        self, *, stats_by_game: dict[str, list[PlayerStatLine]] | None = None, fail: bool = False,
        provider_name: str = DEMO_PROVIDER_NAME,
    ):
        self._stats_by_game = stats_by_game if stats_by_game is not None else starter_data.default_player_stats_by_game()
        self._fail = fail
        self.provider_name = provider_name

    async def fetch_player_stats(self, game_external_id: str) -> AdapterResponse[list[PlayerStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        lines = self._stats_by_game.get(game_external_id, [])
        return AdapterResponse(value=lines, source=self.provider_name)
