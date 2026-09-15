"""Rolling 7-day canonical coverage assertion (2026-09-15, HQ-authorized
"CANONICAL SCHEDULE + FINALIZATION HARDENING", Master Refresh V2).

**What changed and why this exists.** Before V2, the 7-day window was a
*persistence boundary*: Master Refresh fetched the full season, threw away
everything outside `[today, today + 7)`, and persisted only the remainder. That
is the mechanism that produced the Week 2 gap -- the schedule was fetched, the
games existed in the response, and they were discarded before they could ever be
written. V2 persists the full season, and the 7-day window becomes an
**assertion** instead: a post-persistence health check that the next week's
canonical coverage is actually complete.

**It asserts reconciliation, not attendance.** An NFL Tuesday or Wednesday
legitimately has zero games, so "every day has at least one game" would be a
false alarm generator. What this asserts is narrower and actually meaningful:
*every game the provider's own schedule says falls in this window has a
canonical `games` row*. Expected comes from the provider payload already in
hand; actual comes from the canonical read Master Refresh already performs.

**Zero additional calls.** Both inputs are already fetched for other reasons --
this module makes no request of its own, provider or database.

**A gap is reported, never repaired.** This module returns findings; it never
writes, never invents a game, and never suppresses a shortfall. Master Refresh
surfaces a gap as a `partial` run so it is visible rather than silently
tolerated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.adapters.models import ScheduleEntry
from app.master_refresh.slate import WINDOW_DAYS


@dataclass(frozen=True)
class CoverageGap:
    day: str
    expected: int
    canonical: int

    def describe(self) -> str:
        return f"{self.day}: provider has {self.expected}, canonical has {self.canonical}"


@dataclass
class CoverageAssertion:
    days_asserted: int = 0
    expected_games: int = 0
    canonical_games: int = 0
    gaps: list[CoverageGap] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.gaps


def _as_date(value: object) -> date | None:
    """Canonical `scheduled_start` comes back from PostgREST as an ISO string;
    a provider entry already carries a real datetime. Accepts both and returns
    `None` for anything unparseable rather than guessing a day."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def assert_rolling_coverage(
    schedule_entries: list[ScheduleEntry],
    canonical_games: list[dict],
    *,
    today: date,
    window_days: int = WINDOW_DAYS,
) -> CoverageAssertion:
    """Compares, per UTC day across `[today, today + window_days)`, how many
    games the provider's schedule carries against how many canonical `games`
    rows exist.

    `schedule_entries` is the FULL-season response (not a pre-filtered slate) --
    windowing happens here so the assertion can never be accidentally fed the
    same filtered list it is supposed to be checking, which would make it
    trivially and uselessly always pass.
    """
    window = [today + timedelta(days=offset) for offset in range(window_days)]
    window_set = set(window)

    expected_by_day: dict[date, int] = {day: 0 for day in window}
    for entry in schedule_entries:
        day = _as_date(entry.scheduled_start)
        if day in window_set:
            expected_by_day[day] += 1

    canonical_by_day: dict[date, int] = {day: 0 for day in window}
    for game in canonical_games:
        day = _as_date(game.get("scheduled_start"))
        if day in window_set:
            canonical_by_day[day] += 1

    gaps = [
        CoverageGap(day=day.isoformat(), expected=expected_by_day[day], canonical=canonical_by_day[day])
        for day in window
        if canonical_by_day[day] < expected_by_day[day]
    ]

    return CoverageAssertion(
        days_asserted=len(window),
        expected_games=sum(expected_by_day.values()),
        canonical_games=sum(canonical_by_day.values()),
        gaps=gaps,
    )
