"""Tests for app.master_refresh.slate (Phase 3E-2)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.adapters.models import ScheduleEntry
from app.master_refresh.slate import filter_slate_window


def _entry(day: int, hour: int = 20) -> ScheduleEntry:
    return ScheduleEntry(
        game_external_id=f"g-{day}-{hour}",
        home_team="A",
        away_team="B",
        scheduled_start=datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc),
        status="scheduled",
    )


def test_includes_today_and_excludes_before_today():
    entries = [_entry(8), _entry(9)]  # 8th is before, 9th is "today"
    result = filter_slate_window(entries, today=date(2026, 9, 9))
    assert [e.game_external_id for e in result] == ["g-9-20"]


def test_includes_full_window_excludes_day_after_window():
    entries = [_entry(9), _entry(15), _entry(16)]  # window_days=7 -> [9, 16)
    result = filter_slate_window(entries, today=date(2026, 9, 9), window_days=7)
    assert [e.game_external_id for e in result] == ["g-9-20", "g-15-20"]


def test_empty_slate_returns_empty_list():
    entries = [_entry(1)]
    result = filter_slate_window(entries, today=date(2026, 9, 9))
    assert result == []


def test_thursday_game_included_from_tuesday_run():
    # A run on Tuesday the 8th should still pick up a Thursday-the-10th game.
    entries = [_entry(10)]
    result = filter_slate_window(entries, today=date(2026, 9, 8))
    assert len(result) == 1
