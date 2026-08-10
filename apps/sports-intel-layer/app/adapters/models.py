"""Normalized data models every provider adapter returns, regardless of vendor.

These shapes are deliberately provider-agnostic: nothing here encodes any
vendor's field names or response format. `AdapterResponse` carries the
normalized source/provenance metadata every downstream consumer needs to
later reconstruct why a piece of information was used -- who supplied it,
when we fetched it, when the provider itself says it was current, and
whether it came live or from cache. It deliberately does NOT compute
derived values like The Playbook's own confidence or freshness/status;
those belong to whichever downstream milestone actually has the context
to compute them correctly (see `AdapterResponse`'s own docstring below).
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
    TEAM_STATS = "team_stats"
    PLAYER_STATS = "player_stats"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    NEEDS_REFRESH = "needs_refresh"
    STALE = "stale"


T = TypeVar("T")


class AdapterResponse(BaseModel, Generic[T]):
    """The envelope every adapter call returns, regardless of category.

    Provides the normalized source/provenance information downstream
    intelligence processing needs -- not a direct mirror of every field
    daily_game_intelligence's per-category metadata shape carries.
    Specifically:

    - `source` / `fetched_at` / `provider_reported_at` / `from_cache` are
      facts this envelope directly observes about the fetch itself, and
      belong here.
    - `confidence` is deliberately NOT a field on this envelope. The
      Playbook's own confidence (feeding the AI Transparency Meter's
      data_quality dimension) is a downstream-derived value, computed at
      whichever milestone owns that computation -- conflating it with a
      raw adapter response would risk mistaking a provider's own reported
      confidence (if one ever exists) for The Playbook's confidence, which
      would be a real correctness bug, not just an API nicety. If a
      specific provider later exposes a meaningful confidence value worth
      preserving, that gets handled deliberately as provider-supplied
      metadata, not silently folded into this field.
    - `status` (freshness) exists here as a field for later milestones to
      set, but computing it requires comparing against the Volume 2 §8
      cadence table and call history for a specific entity -- a stateful,
      cross-call computation a single adapter fetch can't perform on its
      own. That logic belongs to Milestone E (Master Refresh + scheduled
      workers), not this envelope; it's intentionally never set to
      anything but the default here.
    """

    value: T
    source: str
    #: When The Playbook actually retrieved this data.
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    #: When the provider itself says the underlying data was current/
    #: updated, if and only if the provider exposes such a timestamp.
    #: Never fabricated -- null is a valid, expected value when a provider
    #: doesn't supply one. Deliberately distinct from `fetched_at`: a line
    #: can move minutes before we poll it, and reconstructing "what was
    #: true when" needs both timestamps, not just ours.
    provider_reported_at: datetime | None = None
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


class TeamStatLine(BaseModel):
    game_external_id: str
    team: str
    #: Common cross-sport fields only, matching team_stats.stats jsonb --
    #: deliberately not a typed per-field model here. Volume 3's own
    #: extension-table pattern (player_stats_nfl alongside player_stats)
    #: is how sport-specific typed fields get added later, at the DB layer,
    #: not by hardcoding one sport's stat names into this adapter contract.
    stats: dict


class PlayerStatLine(BaseModel):
    game_external_id: str
    player_external_id: str
    player_name: str
    team: str
    stats: dict
