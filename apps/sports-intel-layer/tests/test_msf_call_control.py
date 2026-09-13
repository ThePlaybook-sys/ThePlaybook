"""Tests for app.workers.msf_call_control (Permanent Box Score Worker
Build, 2026-09-11) -- pure functions, no I/O, no mocking needed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.workers.msf_call_control import (
    FIRST_CHECK_OFFSET,
    FOLLOWUP_CHECK_OFFSET,
    HARD_CAP_ATTEMPTS,
    cache_aware_next_check_at,
    first_check_at,
    hard_cap_reached,
    next_check_at,
    parse_cache_control_max_age,
    parse_retry_after_seconds,
    retry_after_aware_next_check_at,
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


# ============================================================================
# Cache/rate-aware scheduling (Pre-Live Worker Hardening, 2026-09-13)


def test_parse_cache_control_max_age_handles_the_real_msf_header_shape():
    """The exact real value Gate B's own captured response headers
    carried: 'no-transform, max-age=10800' (3 hours)."""
    assert parse_cache_control_max_age("no-transform, max-age=10800") == 10800


def test_parse_cache_control_max_age_case_and_whitespace_tolerant():
    assert parse_cache_control_max_age("  MAX-AGE=60  ") == 60
    assert parse_cache_control_max_age("public,max-age=120,immutable") == 120


def test_parse_cache_control_max_age_absent_or_malformed_is_none():
    assert parse_cache_control_max_age(None) is None
    assert parse_cache_control_max_age("") is None
    assert parse_cache_control_max_age("no-cache") is None
    assert parse_cache_control_max_age("max-age=not-a-number") is None
    assert parse_cache_control_max_age("max-age=-5") is None


def test_parse_retry_after_seconds_integer_form():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    assert parse_retry_after_seconds("120", now=now) == 120


def test_parse_retry_after_seconds_http_date_form():
    now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    http_date = "Sun, 13 Sep 2026 12:02:00 GMT"
    assert parse_retry_after_seconds(http_date, now=now) == 120


def test_parse_retry_after_seconds_absent_or_malformed_or_past_is_none():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    assert parse_retry_after_seconds(None, now=now) is None
    assert parse_retry_after_seconds("", now=now) is None
    assert parse_retry_after_seconds("not-a-value", now=now) is None
    assert parse_retry_after_seconds("0", now=now) is None
    assert parse_retry_after_seconds("-5", now=now) is None
    past_date = "Sun, 13 Sep 2026 11:00:00 GMT"
    assert parse_retry_after_seconds(past_date, now=now) is None


def test_cache_aware_next_check_extends_beyond_default_when_longer():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    result = cache_aware_next_check_at(now=now, cache_max_age_seconds=10800)  # 3h > 1h default
    assert result == now + timedelta(hours=3)


def test_cache_aware_next_check_never_shortens_below_default():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    result = cache_aware_next_check_at(now=now, cache_max_age_seconds=60)  # 1min << 1h default
    assert result == next_check_at(now)  # floor at the normal 1h cadence


def test_cache_aware_next_check_with_no_header_matches_default():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    assert cache_aware_next_check_at(now=now, cache_max_age_seconds=None) == next_check_at(now)


def test_retry_after_aware_next_check_extends_beyond_default_when_longer():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    result = retry_after_aware_next_check_at(now=now, retry_after_seconds=7200)  # 2h > 1h default
    assert result == now + timedelta(hours=2)


def test_retry_after_aware_next_check_never_shortens_below_default():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    result = retry_after_aware_next_check_at(now=now, retry_after_seconds=30)
    assert result == next_check_at(now)


def test_retry_after_aware_next_check_with_no_header_matches_default():
    now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    assert retry_after_aware_next_check_at(now=now, retry_after_seconds=None) == next_check_at(now)
