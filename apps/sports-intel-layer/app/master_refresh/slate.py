"""Slate-window filtering (Phase 3E-2).

**Interpretive choice, flagged explicitly rather than silently decided:**
Mac's approved scope calls for "today's-slate filtering," but NFL games
cluster on Thursday/Sunday/Monday -- a literal single-calendar-day filter
would mean Master Refresh's `daily_game_intelligence` assembly step does
nothing at all on most days of the week, which doesn't match how the
Blueprint describes the table being used (agents reading current-week
intelligence, not only literally-today's). This module instead filters to
a rolling window: every game with `scheduled_start` in
[today, today + WINDOW_DAYS) UTC, refreshed on every run. This means a
Thursday game is refreshed by Tuesday's run onward, not only on the
Thursday itself. WINDOW_DAYS=7 covers a full NFL week between runs.

This is a judgment call within already-approved scope, reported back for
correction if a literal single-day filter was actually intended.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.adapters.models import ScheduleEntry

#: See module docstring -- covers one full NFL week from any run date.
WINDOW_DAYS = 7


def filter_slate_window(
    entries: list[ScheduleEntry], *, today: date, window_days: int = WINDOW_DAYS
) -> list[ScheduleEntry]:
    """Returns the subset of `entries` whose `scheduled_start` (UTC) falls
    in [today, today + window_days)."""
    window_end = today + timedelta(days=window_days)
    return [e for e in entries if today <= e.scheduled_start.date() < window_end]
