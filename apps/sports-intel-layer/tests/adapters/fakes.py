"""Fake adapters used to prove the conformance suite and cache boundary
work correctly, without depending on any real vendor. No Phase 3B/3C
vendor-specific adapter exists yet (Mac's explicit instruction: Phase 3A
is provider-independent) -- these fakes stand in for "some adapter
implementing the interface" until a real one does.
"""
from __future__ import annotations

from datetime import datetime

from app.adapters.base import (
    InjuryAdapter,
    NewsAdapter,
    OddsAdapter,
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
    PlayerStatLine,
    RosterEntry,
    ScheduleEntry,
    TeamStatLine,
    WeatherConditions,
)


class FakeOddsAdapterV1(OddsAdapter):
    provider_name = "fake_provider_v1"

    def __init__(self, *, fail: bool = False, provider_reported_at: datetime | None = None):
        self._fail = fail
        # Optional, mirroring the real-world case: some vendors expose a
        # "line last moved at" timestamp, some don't. Defaults to None so
        # tests exercise both the supplied and not-supplied cases explicitly
        # rather than only ever the happy path.
        self._provider_reported_at = provider_reported_at

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        lines = [
            OddsLine(
                game_external_id=game_id,
                sportsbook="fakebook",
                market_type="moneyline",
                line_data={"home": -110, "away": -110},
            )
            for game_id in game_external_ids
        ]
        return AdapterResponse(
            value=lines,
            source=self.provider_name,
            provider_reported_at=self._provider_reported_at,
        )


class FakeOddsAdapterV2(OddsAdapter):
    """A second, independently-implemented fake -- used specifically to
    prove a vendor swap requires zero change outside the adapter itself
    (Phase 3's actual acceptance criterion for the pattern, not just an
    assertion about it)."""

    provider_name = "fake_provider_v2"

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        lines = [
            OddsLine(
                game_external_id=game_id,
                sportsbook="anotherbook",
                market_type="moneyline",
                line_data={"home": -105, "away": -115},
            )
            for game_id in game_external_ids
        ]
        return AdapterResponse(value=lines, source=self.provider_name)


class FakeTeamStatsAdapter(TeamStatsAdapter):
    provider_name = "fake_stats_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        lines = [
            TeamStatLine(
                game_external_id=game_external_id,
                team="home",
                stats={"points": 24, "total_yards": 350},
            ),
            TeamStatLine(
                game_external_id=game_external_id,
                team="away",
                stats={"points": 17, "total_yards": 290},
            ),
        ]
        return AdapterResponse(value=lines, source=self.provider_name)


class FakeWeatherAdapter(WeatherAdapter):
    provider_name = "fake_weather_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_weather(
        self, game_external_id: str, kickoff: datetime
    ) -> AdapterResponse[WeatherConditions]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        conditions = WeatherConditions(
            game_external_id=game_external_id,
            temperature_f=65.0,
            wind_mph=5.0,
            precipitation_pct=0,
            conditions="Clear",
            is_dome=False,
        )
        return AdapterResponse(value=conditions, source=self.provider_name)


class FakeRosterAdapter(RosterAdapter):
    provider_name = "fake_roster_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        entries = [
            RosterEntry(
                team=team, player_external_id="1", player_name="Fake Player",
                position="QB", depth_chart_rank=1,
            )
        ]
        return AdapterResponse(value=entries, source=self.provider_name)


class FakeScheduleAdapter(ScheduleAdapter):
    provider_name = "fake_schedule_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_schedule(self, season_external_id: str) -> AdapterResponse[list[ScheduleEntry]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        entries = [
            ScheduleEntry(
                game_external_id="fake-game-1", home_team="home", away_team="away",
                scheduled_start=datetime(2026, 9, 1, 17, 0), stadium="Fake Stadium",
                status="scheduled",
            )
        ]
        return AdapterResponse(value=entries, source=self.provider_name)


class FakeInjuryAdapter(InjuryAdapter):
    provider_name = "fake_injury_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        reports = [
            InjuryReport(
                game_external_id="fake-game-1", player_external_id="1",
                player_name="Fake Player", team=team or "home", status="questionable",
            )
        ]
        return AdapterResponse(value=reports, source=self.provider_name)


class FakePlayerStatsAdapter(PlayerStatsAdapter):
    provider_name = "fake_player_stats_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_player_stats(self, game_external_id: str) -> AdapterResponse[list[PlayerStatLine]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        lines = [
            PlayerStatLine(
                game_external_id=game_external_id, player_external_id="1",
                player_name="Fake Player", team="home", stats={"passing_yards": 250},
            )
        ]
        return AdapterResponse(value=lines, source=self.provider_name)


class FakeNewsAdapter(NewsAdapter):
    provider_name = "fake_news_provider"

    def __init__(self, *, fail: bool = False):
        self._fail = fail

    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        if self._fail:
            raise ProviderUnavailableError("simulated outage", provider=self.provider_name)
        articles = [
            NewsArticle(
                headline="Fake headline",
                url="https://example.com/fake",
                source="fakenews",
                published_at=datetime(2026, 9, 1),
                related_teams=[team] if team else [],
            )
        ]
        return AdapterResponse(value=articles, source=self.provider_name)
