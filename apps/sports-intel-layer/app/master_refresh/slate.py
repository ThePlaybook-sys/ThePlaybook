"""Slate-window filtering (Phase 3E-2/3E-3).

**MASTER REFRESH OPERATING HORIZON, approved by Mac 2026-08-13 (Volume 2
§8 v4.4):** `[today, today + 7 days)` UTC. Every game with `scheduled_start`
in that window is refreshed on every run -- a Thursday game is already
prepared by the preceding Tuesday's run, not only on the Thursday itself.
This is the canonical statement of the horizon; do not silently
reinterpret it elsewhere. It governs Master Refresh's own game-identity/
`daily_game_intelligence`-assembly work only -- it does not change any
specialized worker's own cadence (Odds/Player Props/Injuries/Weather/News
are not polled continuously for 7 days; see Volume 2 §8's cadence table).
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
