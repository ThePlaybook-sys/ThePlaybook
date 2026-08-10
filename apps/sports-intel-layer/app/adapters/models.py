"""Normalized data models every provider adapter returns, regardless of vendor.

These shapes are deliberately provider-agnostic: nothing here encodes any
vendor's field names or response format. `AdapterResponse` wraps each
category's payload in the same envelope Volume 3 §4.1's `daily_game_intelligence`
table expects per-category (value/source/confidence/last_updated/status), so
Master Refresh can write adapter output into it with minimal translation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


class DataCategory(str, Enum):
    ODDS = "odds"
    PLAYER_PROPS = "player_props"
    INJURIES = "injuries"
    WEATHER = "weather"
    ROSTERS = "rosters"
    SCHEDULES = "schedules"
    NEWS = "news"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    NEEDS_REFRESH = "needs_refresh"
    STALE = "stale"


T = TypeVar("T")


class AdapterResponse(BaseModel, Generic[T]):
    """The envelope every adapter call returns, regardless of category.

    Mirrors daily_game_intelligence's per-category jsonb metadata shape
    (value/source/confidence/last_updated/status) so Master Refresh can
    write this straight into that table without a separate translation step.
    """

    value: T
    source: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False
    status: FreshnessStatus = FreshnessStatus.FRESH


class OddsLine(BaseModel):
    game_external_id: str
    sportsbook: str
    market_type: str  # 'moneyline' | 'spread' | 'total' | 'prop' -- matches odds_snapshots.market_type
    line_data: dict


class PlayerProp(BaseModel):
    game_external_id: str
    sportsbook: str
    player_external_id: str
    player_name: str
    prop_type: str  # e.g. 'player_pass_tds'
    line: float
    over_odds: int | None = None
    under_odds: int | None = None


class InjuryReport(BaseModel):
    game_external_id: str
    player_external_id: str
    player_name: str
    team: str
    status: str  # 'out' | 'doubtful' | 'questionable' | 'probable' | 'active'
    description: str | None = None


class WeatherConditions(BaseModel):
    game_external_id: str
    temperature_f: float | None = None
    wind_mph: float | None = None
    precipitation_pct: float | None = None
    conditions: str | None = None
    is_dome: bool = False


class RosterEntry(BaseModel):
    team: str
    player_external_id: str
    player_name: str
    position: str
    depth_chart_rank: int | None = None


class ScheduleEntry(BaseModel):
    game_external_id: str
    home_team: str
    away_team: str
    scheduled_start: datetime
    stadium: str | None = None
    status: str  # matches games.status check constraint


class NewsArticle(BaseModel):
    headline: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None
    related_teams: list[str] = Field(default_factory=list)
