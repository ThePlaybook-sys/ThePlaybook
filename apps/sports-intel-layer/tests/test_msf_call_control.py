"""Tests for app.workers.msf_call_control (Permanent Box Score Worker
Build, 2026-09-11) -- pure functions, no I/O, no mocking needed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.workers.msf_call_control import (
    FIRST_CHECK_OFFSET,
    FOLLOWUP_CHECK_OFFSET,
    HARD_CAP_ATTEMPTS,
    first_check_at,
    hard_cap_reached,
    next_check_at,
)


def test_first_check_is_kickoff_plus_3h30m():
    kickoff = datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc)
    assert first_check_at(kickoff) == kickoff + timedelta(hours=3, minutes=30)
    assert FIRST_CHECK_OFFSET == timedelta(hours=3, minutes=30)


def test_next_check_is_one_hour_from_now_not_from_kickoff():
    now = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)
    assert next_check_at(now) == now + timedelta(hours=1)
    assert FOLLOWUP_CHECK_OFFSET == timedelta(hours=1)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        first_check_at(datetime(2026, 9, 13, 20, 25))
    with pytest.raises(ValueError):
        next_check_at(datetime(2026, 9, 14, 5, 0))


def test_hard_cap_is_4():
    assert HARD_CAP_ATTEMPTS == 4
    assert hard_cap_reached(4) is True
    assert hard_cap_reached(5) is True
    assert hard_cap_reached(3) is False
    assert hard_cap_reached(0) is False
