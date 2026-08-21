"""Deterministic travel/fatigue feature engineering (Milestone 4.4,
Decision 5). Geographic distance and timezone-shift calculation are
application math here -- never something the Travel & Fatigue Agent
asks a model to compute or recall. The agent consumes `TravelFeatures`
as an already-computed fact and reasons only about football
significance (Decision 6's raw-fact/AI-reasoning separation, applied to
this category specifically).

**Reference-data inspection performed before writing this, per explicit
instruction not to create a brittle duplicated stadium knowledge base if
an existing canonical source already owns it.** Checked: does any
existing table normalize venue/stadium identity? No -- Volume 3 v4.9's
own note is direct evidence this was already decided deliberately:
"games gains venue_lat/venue_long/venue_type... Option A chosen over a
dedicated stadiums reference table... judged sufficient given the
league's small (~30) venue count." This project has never normalized
stadium data into its own table; venue facts live directly, per-game, on
`games` itself. `_STADIUM_REFERENCE` below extends that same accepted
precedent to timezone/international-venue identity specifically (the one
piece `games.venue_lat/venue_long/venue_type` don't capture) -- one
small, explicitly-labeled static reference dataset, not a duplicated ad
hoc lookup scattered through code. A stadium name absent from this table
produces `None` for `timezone_shift_hours`/`is_international_game` --
unknown, never guessed -- while `travel_distance_miles` (computed purely
from already-stored coordinates) is entirely unaffected by a
reference-lookup miss.

**Provenance of `_STADIUM_REFERENCE`'s data, stated plainly:** public,
well-established NFL venue/timezone knowledge -- the same provenance tier
`app.persistence.team_backfill.TEAM_BACKFILL` (sports-intel-layer)
already uses for team names ("public, standard NFL naming -- not
fabricated, and not preserved from synthetic seed values"). Not
fixture-confirmed against a live SportsDataIO payload (no live call was
made or authorized for this). Keyed by stadium name text, matching
`games.stadium`/`daily_game_intelligence.stadium.name` exactly as
Schedule ingestion already populates it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

_EARTH_RADIUS_MILES = 3958.8


@dataclass(frozen=True)
class StadiumReference:
    timezone: str  # IANA zone name -- resolves DST correctly via zoneinfo, never a hardcoded raw UTC offset
    is_international: bool


#: Public NFL venue/timezone reference data (see module docstring for
#: provenance). 30 unique current-stadium entries covering all 32 teams
#: (MetLife Stadium shared by Giants/Jets, SoFi Stadium shared by
#: Rams/Chargers) plus a small set of recurring international venues.
_STADIUM_REFERENCE: dict[str, StadiumReference] = {
    "Highmark Stadium": StadiumReference("America/New_York", False),
    "Hard Rock Stadium": StadiumReference("America/New_York", False),
    "Gillette Stadium": StadiumReference("America/New_York", False),
    "MetLife Stadium": StadiumReference("America/New_York", False),
    "M&T Bank Stadium": StadiumReference("America/New_York", False),
    "Paycor Stadium": StadiumReference("America/New_York", False),
    "Huntington Bank Field": StadiumReference("America/New_York", False),
    "Acrisure Stadium": StadiumReference("America/New_York", False),
    "NRG Stadium": StadiumReference("America/Chicago", False),
    "Lucas Oil Stadium": StadiumReference("America/New_York", False),
    "EverBank Stadium": StadiumReference("America/New_York", False),
    "Nissan Stadium": StadiumReference("America/Chicago", False),
    "Empower Field at Mile High": StadiumReference("America/Denver", False),
    "Arrowhead Stadium": StadiumReference("America/Chicago", False),
    "Allegiant Stadium": StadiumReference("America/Los_Angeles", False),
    "SoFi Stadium": StadiumReference("America/Los_Angeles", False),
    "AT&T Stadium": StadiumReference("America/Chicago", False),
    "Lincoln Financial Field": StadiumReference("America/New_York", False),
    "Commanders Field": StadiumReference("America/New_York", False),
    "Soldier Field": StadiumReference("America/Chicago", False),
    "Ford Field": StadiumReference("America/New_York", False),
    "Lambeau Field": StadiumReference("America/Chicago", False),
    "U.S. Bank Stadium": StadiumReference("America/Chicago", False),
    "Mercedes-Benz Stadium": StadiumReference("America/New_York", False),
    "Bank of America Stadium": StadiumReference("America/New_York", False),
    "Caesars Superdome": StadiumReference("America/Chicago", False),
    "Raymond James Stadium": StadiumReference("America/New_York", False),
    "State Farm Stadium": StadiumReference("America/Phoenix", False),
    "Levi's Stadium": StadiumReference("America/Los_Angeles", False),
    "Lumen Field": StadiumReference("America/Los_Angeles", False),
    # Recurring international venues (NFL London/Frankfurt/Mexico City/
    # Sao Paulo games) -- a game's actual `stadium`/`venue_lat`/`venue_long`
    # reflect the true one-off international venue for that week, never a
    # team's normal home stadium, per Schedule ingestion's own per-game
    # venue capture (Volume 3 v4.9).
    "Tottenham Hotspur Stadium": StadiumReference("Europe/London", True),
    "Wembley Stadium": StadiumReference("Europe/London", True),
    "Deutsche Bank Park": StadiumReference("Europe/Berlin", True),
    "Estadio Azteca": StadiumReference("America/Mexico_City", True),
    "Neo Quimica Arena": StadiumReference("America/Sao_Paulo", True),
}


def lookup_stadium_reference(stadium_name: str | None) -> StadiumReference | None:
    """Returns `None` -- unknown, never guessed -- for a missing or
    unrecognized stadium name."""
    if stadium_name is None:
        return None
    return _STADIUM_REFERENCE.get(stadium_name)


def haversine_miles(lat1: float, long1: float, lat2: float, long2: float) -> float:
    """Great-circle distance in miles between two lat/long points.
    Deterministic application math (Decision 5/8) -- never LLM
    arithmetic."""
    lat1_r, long1_r, lat2_r, long2_r = (radians(v) for v in (lat1, long1, lat2, long2))
    d_lat = lat2_r - lat1_r
    d_long = long2_r - long1_r
    a = sin(d_lat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(d_long / 2) ** 2
    return _EARTH_RADIUS_MILES * 2 * asin(sqrt(a))


def timezone_shift_hours(previous_stadium: str | None, current_stadium: str | None, *, at: datetime) -> float | None:
    """Hours of timezone shift between the previous game's venue and the
    current one, evaluated `at` a specific aware instant so DST is
    resolved correctly via `zoneinfo` rather than a hardcoded raw offset.
    Returns `None` -- never a guessed number -- if either stadium is
    unresolvable in `_STADIUM_REFERENCE`."""
    if at.tzinfo is None:
        raise ValueError("timezone_shift_hours requires a timezone-aware `at` datetime")
    prev_ref = lookup_stadium_reference(previous_stadium)
    curr_ref = lookup_stadium_reference(current_stadium)
    if prev_ref is None or curr_ref is None:
        return None
    prev_offset = at.astimezone(ZoneInfo(prev_ref.timezone)).utcoffset()
    curr_offset = at.astimezone(ZoneInfo(curr_ref.timezone)).utcoffset()
    return (curr_offset - prev_offset).total_seconds() / 3600.0


def is_international_game(stadium_name: str | None) -> bool | None:
    """Returns `None` -- unknown, never guessed -- for a stadium not in
    `_STADIUM_REFERENCE`."""
    ref = lookup_stadium_reference(stadium_name)
    if ref is None:
        return None
    return ref.is_international


def count_consecutive_road_games(recent_games: list[dict], *, team: str) -> int:
    """Pure calculation over an already-fetched, most-recent-first list
    of a team's recent games (each a dict with `home_team`/`away_team`).
    Counts consecutive away appearances starting from the most recent
    game, stopping at the first home game or the end of the list.

    **Not yet wired to a live data source in Milestone 4.4** -- no
    persistence reader collecting "a team's recent game history" exists
    yet (this is the one Travel & Fatigue feature Mac's own instruction
    flagged as "where reliably derivable," softer than the others). This
    function is built and tested now so the calculation itself is proven
    deterministic and correct; `TravelFatigueAgent` receives `None` for
    this field until a future milestone adds the recent-games reader.
    """
    count = 0
    for game in recent_games:
        if game.get("away_team") == team:
            count += 1
        elif game.get("home_team") == team:
            break
        else:
            break
    return count


@dataclass(frozen=True)
class TravelFeatures:
    travel_distance_miles: float | None
    timezone_shift_hours: float | None
    is_international_game: bool | None
    consecutive_road_games: int | None


def compute_travel_features(
    *,
    current_venue_lat: float | None,
    current_venue_long: float | None,
    current_stadium: str | None,
    previous_venue_lat: float | None,
    previous_venue_long: float | None,
    previous_stadium: str | None,
    kickoff_at: datetime,
    consecutive_road_games: int | None = None,
) -> TravelFeatures:
    """Composes the full deterministic travel/fatigue feature set from
    already-available raw facts. Each field independently degrades to
    `None` on missing input -- a coordinate gap never blocks the
    timezone/international calculations, and vice versa."""
    distance = None
    if None not in (current_venue_lat, current_venue_long, previous_venue_lat, previous_venue_long):
        distance = haversine_miles(previous_venue_lat, previous_venue_long, current_venue_lat, current_venue_long)
    return TravelFeatures(
        travel_distance_miles=distance,
        timezone_shift_hours=timezone_shift_hours(previous_stadium, current_stadium, at=kickoff_at),
        is_international_game=is_international_game(current_stadium),
        consecutive_road_games=consecutive_road_games,
    )
