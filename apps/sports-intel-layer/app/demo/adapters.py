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

#: Shared provider_name for every Demo*Adapter -- surfaced only as
#: AdapterResponse.source metadata (per base.py's own docstring), never as
#: part of the data itself. One consistent value across categories, matching
#: how a real vendor's own adapters all share that vendor's identity.
DEMO_PROVIDER_NAME = "demo"


class DemoOddsAdapter(OddsAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, odds_by_game: dict[str, list[OddsLine]] | None = None, fail: bool = False):
        self._odds_by_game = odds_by_game if odds_by_game is not None else starter_data.default_odds_by_game()
        self._fail = fail

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        lines = [line for game_id in game_external_ids for line in self._odds_by_game.get(game_id, [])]
        return AdapterResponse(value=lines, source=self.provider_name)


class DemoPlayerPropsAdapter(PlayerPropsAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, props_by_game: dict[str, list[PlayerProp]] | None = None, fail: bool = False):
        self._props_by_game = props_by_game if props_by_game is not None else starter_data.default_player_props_by_game()
        self._fail = fail

    async def fetch_player_props(self, game_external_ids: list[str]) -> AdapterResponse[list[PlayerProp]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        props = [prop for game_id in game_external_ids for prop in self._props_by_game.get(game_id, [])]
        return AdapterResponse(value=props, source=self.provider_name)


class DemoInjuryAdapter(InjuryAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, injuries: list[InjuryReport] | None = None, fail: bool = False):
        self._injuries = injuries if injuries is not None else starter_data.default_injuries()
        self._fail = fail

    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        reports = self._injuries if team is None else [r for r in self._injuries if r.team == team]
        return AdapterResponse(value=reports, source=self.provider_name)


class DemoWeatherAdapter(WeatherAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, weather_by_game: dict[str, WeatherConditions] | None = None, fail: bool = False):
        self._weather_by_game = weather_by_game if weather_by_game is not None else starter_data.default_weather_by_game()
        self._fail = fail

    async def fetch_weather(self, game_external_id: str, kickoff: datetime) -> AdapterResponse[WeatherConditions]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        conditions = self._weather_by_game.get(
            game_external_id,
            WeatherConditions(game_external_id=game_external_id),
        )
        return AdapterResponse(value=conditions, source=self.provider_name)


class DemoRosterAdapter(RosterAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, roster_by_team: dict[str, list[RosterEntry]] | None = None, fail: bool = False):
        self._roster_by_team = roster_by_team if roster_by_team is not None else starter_data.default_roster_by_team()
        self._fail = fail

    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        entries = self._roster_by_team.get(team, [])
        return AdapterResponse(value=entries, source=self.provider_name)


class DemoScheduleAdapter(ScheduleAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, schedule: list[ScheduleEntry] | None = None, fail: bool = False):
        self._schedule = schedule if schedule is not None else starter_data.default_schedule()
        self._fail = fail

    async def fetch_schedule(self, season_external_id: str) -> AdapterResponse[list[ScheduleEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        return AdapterResponse(value=list(self._schedule), source=self.provider_name)


class DemoNewsAdapter(NewsAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, articles: list[NewsArticle] | None = None, fail: bool = False):
        self._articles = articles if articles is not None else starter_data.default_news()
        self._fail = fail

    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        articles = self._articles if team is None else [a for a in self._articles if team in a.related_teams]
        return AdapterResponse(value=articles, source=self.provider_name)


class DemoTeamStatsAdapter(TeamStatsAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, stats_by_game: dict[str, list[TeamStatLine]] | None = None, fail: bool = False):
        self._stats_by_game = stats_by_game if stats_by_game is not None else starter_data.default_team_stats_by_game()
        self._fail = fail

    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        lines = self._stats_by_game.get(game_external_id, [])
        return AdapterResponse(value=lines, source=self.provider_name)


class DemoPlayerStatsAdapter(PlayerStatsAdapter):
    provider_name = DEMO_PROVIDER_NAME

    def __init__(self, *, stats_by_game: dict[str, list[PlayerStatLine]] | None = None, fail: bool = False):
        self._stats_by_game = stats_by_game if stats_by_game is not None else starter_data.default_player_stats_by_game()
        self._fail = fail

    async def fetch_player_stats(self, game_external_id: str) -> AdapterResponse[list[PlayerStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated demo outage", provider=self.provider_name)
        lines = self._stats_by_game.get(game_external_id, [])
        return AdapterResponse(value=lines, source=self.provider_name)
