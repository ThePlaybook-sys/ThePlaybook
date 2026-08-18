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
    #: Provider's own home/away team representation (e.g. The Odds API's
    #: full team name), Phase 3E-4B. Required, not derived-later: the
    #: deterministic game-linking module (app.persistence.odds_game_linking)
    #: needs both identities -- plus this event's own scheduled kickoff --
    #: to resolve a provider event to games.id the first time it's seen,
    #: before any game_provider_ids mapping exists for it. Provider-neutral
    #: by construction: these are plain team-name/abbreviation strings, the
    #: same shape ScheduleEntry.home_team/away_team already carry -- no
    #: provider-specific field name or structure leaks past this.
    home_team: str
    away_team: str
    #: The event's own scheduled kickoff, as the provider reports it --
    #: distinct from `AdapterResponse.provider_reported_at` (which is when
    #: a *line* last moved, not when the game starts). Required for the
    #: same reason as home_team/away_team: the deterministic game-linking
    #: module's last step is scheduled-start validation against the
    #: internal `games` row it's matched by team identity (Phase 3E-4B/C)
    #: -- a real requirement surfaced by direct inspection while building
    #: 3E-4C, beyond the two fields Mac named explicitly.
    commence_time: datetime
    sportsbook: str
    market_type: str  # 'moneyline' | 'spread' | 'total' | 'prop' -- matches odds_snapshots.market_type
    line_data: dict


class PlayerProp(BaseModel):
    game_external_id: str
    #: See OddsLine.home_team/away_team/commence_time -- same game-identity
    #: requirement, same reasoning (Phase 3E-4B).
    home_team: str
    away_team: str
    commence_time: datetime
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
    #: True = definitively indoor/dome, False = definitively outdoor,
    #: None = unknown -- never defaulted to False (Phase 3E-6, Option A,
    #: null-not-neutral convention). No weather vendor has this information
    #: (it's about our own stadium, not their forecast) -- WeatherAPIWeatherAdapter
    #: always returns None here; the worker layer, which knows the venue's
    #: normalized type, overlays the real value before persisting.
    is_dome: bool | None = None


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
    #: Normalized internal vocabulary (games.season_type check constraint, Phase 3E-1
    #: Decision 1) -- 'preseason' | 'regular' | 'postseason' | None, never a provider's
    #: raw value. Optional: not every sport/provider supplies a season phase.
    season_type: str | None = None
    #: NFL week number at launch (games.week, Phase 3E-1 Decision 1). Optional: not
    #: every sport/provider uses week numbering.
    week: int | None = None
    #: Venue coordinates (games.venue_lat/.venue_long, Phase 3E-6, Option A) --
    #: from the provider's own StadiumDetails.GeoLat/GeoLong. Optional: not every
    #: provider response carries venue metadata; never fabricated when missing.
    venue_lat: float | None = None
    venue_long: float | None = None
    #: Normalized internal vocabulary (games.venue_type check constraint, Phase
    #: 3E-6 Option A) -- 'outdoor' | 'dome' | 'retractable_dome' | None, never a
    #: provider's raw value (e.g. SportsDataIO's "RetractableDome"). Optional:
    #: unknown is a real, distinct state, scoped to exactly what Weather Worker
    #: needs -- no other StadiumDetails fields (capacity, playing surface, city,
    #: state, country) are carried here, since nothing downstream needs them yet.
    venue_type: str | None = None


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
