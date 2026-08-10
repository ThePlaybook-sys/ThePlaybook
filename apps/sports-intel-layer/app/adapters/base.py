"""The shared provider-adapter interface (Volume 2 §8).

Every adapter -- regardless of vendor -- implements one of the ABCs below.
Nothing outside this package (no worker, no agent, no other service) is
allowed to import a provider SDK directly; they only ever depend on these
interfaces and the normalized models in `models.py`. That's the actual
enforcement point of the adapter pattern, not just a naming convention.

One adapter instance serves exactly one DataCategory, even when a single
vendor (e.g. SportsDataIO) backs multiple categories -- that vendor gets
one adapter class per category (sharing an HTTP client if convenient), not
one adapter answering for several categories at once.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.adapters.models import (
    AdapterResponse,
    DataCategory,
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


class ProviderAdapter(ABC):
    """Common shape every category-specific adapter shares."""

    #: Short, stable identifier for this vendor (e.g. "the_odds_api").
    #: Used in cache keys and error attribution -- surfaced to callers only
    #: as metadata (AdapterResponse.source), never as part of the data itself.
    provider_name: str

    #: Which Volume 2 §8 data category this adapter serves.
    category: DataCategory


class OddsAdapter(ProviderAdapter):
    category = DataCategory.ODDS

    @abstractmethod
    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        """Return current odds lines for the given games."""


class PlayerPropsAdapter(ProviderAdapter):
    category = DataCategory.PLAYER_PROPS

    @abstractmethod
    async def fetch_player_props(self, game_external_ids: list[str]) -> AdapterResponse[list[PlayerProp]]:
        """Return current player prop lines for the given games."""


class InjuryAdapter(ProviderAdapter):
    category = DataCategory.INJURIES

    @abstractmethod
    async def fetch_injuries(self, team: str | None = None) -> AdapterResponse[list[InjuryReport]]:
        """Return current injury reports, optionally filtered to one team."""


class WeatherAdapter(ProviderAdapter):
    category = DataCategory.WEATHER

    @abstractmethod
    async def fetch_weather(
        self, game_external_id: str, kickoff: datetime
    ) -> AdapterResponse[WeatherConditions]:
        """Return forecast/current conditions for a single game's venue."""


class RosterAdapter(ProviderAdapter):
    category = DataCategory.ROSTERS

    @abstractmethod
    async def fetch_roster(self, team: str) -> AdapterResponse[list[RosterEntry]]:
        """Return a team's current roster and depth chart."""


class ScheduleAdapter(ProviderAdapter):
    category = DataCategory.SCHEDULES

    @abstractmethod
    async def fetch_schedule(self, season_external_id: str) -> AdapterResponse[list[ScheduleEntry]]:
        """Return the season's game schedule."""


class NewsAdapter(ProviderAdapter):
    category = DataCategory.NEWS

    @abstractmethod
    async def fetch_news(self, team: str | None = None) -> AdapterResponse[list[NewsArticle]]:
        """Return recent news/sentiment articles, optionally filtered to one team."""


class TeamStatsAdapter(ProviderAdapter):
    category = DataCategory.TEAM_STATS

    @abstractmethod
    async def fetch_team_stats(self, game_external_id: str) -> AdapterResponse[list[TeamStatLine]]:
        """Return team-level stat lines for a single game. Scoped to one
        game, not a bulk/season fetch -- this is meant to be called once,
        triggered by that game's status transitioning to final (Volume 2
        §1.1's "download once, reuse everywhere"), not polled repeatedly."""


class PlayerStatsAdapter(ProviderAdapter):
    category = DataCategory.PLAYER_STATS

    @abstractmethod
    async def fetch_player_stats(self, game_external_id: str) -> AdapterResponse[list[PlayerStatLine]]:
        """Return player-level stat lines for a single game. Same
        fetch-once-on-final intent as TeamStatsAdapter.fetch_team_stats."""
