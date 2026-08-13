"""Tests for app.master_refresh.rest (Phase 3E-2, Decision 2)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.master_refresh.rest import compute_rest


def test_season_opener_has_null_rest_days_not_zero():
    result = compute_rest(
        current_scheduled_start=datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc), previous_game=None
    )
    assert result == {"rest_days": None, "season_opener": True}


def test_normal_week_rest():
    previous = {"scheduled_start": "2026-09-10T20:00:00+00:00"}
    result = compute_rest(
        current_scheduled_start=datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc), previous_game=previous
    )
    assert result == {"rest_days": 7, "season_opener": False}


def test_short_week_rest():
    previous = {"scheduled_start": "2026-09-14T20:00:00+00:00"}  # Monday night
    result = compute_rest(
        current_scheduled_start=datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc), previous_game=previous
    )
    assert result == {"rest_days": 4, "season_opener": False}


def test_elevated_rest_after_bye_week_no_separate_flag():
    previous = {"scheduled_start": "2026-09-10T20:00:00+00:00"}
    result = compute_rest(
        current_scheduled_start=datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc), previous_game=previous
    )
    # 14 days -- the elevated number itself is the signal, per Decision 2;
    # no is_bye_week_return field.
    assert result == {"rest_days": 14, "season_opener": False}
    assert "is_bye_week_return" not in result


def test_previous_game_as_datetime_object_not_only_string():
    previous = {"scheduled_start": datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)}
    result = compute_rest(
        current_scheduled_start=datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc), previous_game=previous
    )
    assert result["rest_days"] == 7
