"""Tests for app.workers.windows (Phase 3E-4F/G) -- the single shared
kickoff-proximity classification reused by both adaptive worker polling
cadence and dynamic cache TTL selection.

Covers Mac's explicit 3E-4G test list: Eastern/Central/Mountain/Pacific
games, Sunday early window, Sunday late window, Sunday night, Monday
night, Thursday night, games crossing a UTC calendar boundary, and
daylight-saving-time behavior -- plus the ramp/TTL boundary behavior
itself and the naive-datetime rejection that enforces "never based on the
Railway server's local timezone."
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.workers.windows import (
    InjuryWindow,
    Window,
    classify_injury_window,
    classify_window,
    injury_poll_interval_seconds,
    injury_ttl_seconds,
    poll_interval_seconds,
    should_poll,
    should_poll_injuries,
    ttl_seconds,
)

EASTERN = ZoneInfo("America/New_York")
CENTRAL = ZoneInfo("America/Chicago")
MOUNTAIN = ZoneInfo("America/Denver")
PACIFIC = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Naive datetimes rejected -- the actual enforcement of "never based on the
# Railway server's local timezone."
# ---------------------------------------------------------------------------


def test_naive_now_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_window(now=datetime(2026, 9, 13, 12, 0), kickoff=datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc))


def test_naive_kickoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_window(now=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc), kickoff=datetime(2026, 9, 13, 17, 0))


def test_naive_last_polled_at_is_rejected_by_should_poll():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(hours=5)
    with pytest.raises(ValueError, match="timezone-aware"):
        should_poll(now=now, kickoff=kickoff, last_polled_at=datetime(2026, 9, 13, 10, 0))


# ---------------------------------------------------------------------------
# Ramp boundaries -- exact tier transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "time_to_kickoff,expected",
    [
        (timedelta(days=4), Window.FAR),
        (timedelta(hours=2, seconds=1), Window.FAR),
        (timedelta(hours=2), Window.RAMP_2H),
        (timedelta(minutes=61), Window.RAMP_2H),
        (timedelta(minutes=60), Window.RAMP_60M),
        (timedelta(minutes=16), Window.RAMP_60M),
        (timedelta(minutes=15), Window.RAMP_15M),
        (timedelta(minutes=6), Window.RAMP_15M),
        (timedelta(minutes=5), Window.RAMP_5M),
        (timedelta(seconds=1), Window.RAMP_5M),
        (timedelta(0), Window.STOPPED),
        (timedelta(minutes=-90), Window.STOPPED),  # mid-game, well after kickoff
    ],
)
def test_classify_window_boundaries(time_to_kickoff, expected):
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    kickoff = now + time_to_kickoff
    assert classify_window(now=now, kickoff=kickoff) == expected


def test_stopped_window_has_no_poll_interval_and_never_polls():
    assert poll_interval_seconds(Window.STOPPED) is None
    now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
    kickoff = now - timedelta(minutes=5)  # already kicked off
    assert should_poll(now=now, kickoff=kickoff, last_polled_at=None) is False


def test_ttl_matches_poll_interval_for_every_actively_polled_window():
    for window in Window:
        if window is Window.STOPPED:
            continue
        assert ttl_seconds(window) == poll_interval_seconds(window)


def test_stopped_window_ttl_reuses_final_ramp_interval_not_infinite_or_zero():
    assert ttl_seconds(Window.STOPPED) == poll_interval_seconds(Window.RAMP_5M)


# ---------------------------------------------------------------------------
# should_poll -- interval-elapsed behavior
# ---------------------------------------------------------------------------


def test_should_poll_true_when_never_polled_and_window_is_active():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(hours=1)
    assert should_poll(now=now, kickoff=kickoff, last_polled_at=None) is True


def test_should_poll_false_when_interval_has_not_elapsed():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(minutes=10)  # RAMP_15M tier -- 300s interval
    last_polled_at = now - timedelta(seconds=100)
    assert should_poll(now=now, kickoff=kickoff, last_polled_at=last_polled_at) is False


def test_should_poll_true_once_interval_has_elapsed():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(minutes=10)  # RAMP_15M tier -- 300s interval
    last_polled_at = now - timedelta(seconds=301)
    assert should_poll(now=now, kickoff=kickoff, last_polled_at=last_polled_at) is True


# ---------------------------------------------------------------------------
# Real NFL kickoff slots, across all four continental US timezones the
# league plays in, converted through zoneinfo (never a naive/local-time
# shortcut) -- Mac's explicit 3E-4G test list.
# ---------------------------------------------------------------------------


def test_sunday_early_window_eastern():
    # 1:00 PM Eastern (EDT, mid-September) Sunday early window.
    kickoff = datetime(2026, 9, 13, 13, 0, tzinfo=EASTERN)
    now = kickoff - timedelta(hours=3)
    assert classify_window(now=now, kickoff=kickoff) == Window.FAR


def test_sunday_late_window_central():
    # 3:05 PM Central (CDT) late-window game.
    kickoff = datetime(2026, 9, 13, 15, 5, tzinfo=CENTRAL)
    now = kickoff - timedelta(minutes=10)
    assert classify_window(now=now, kickoff=kickoff) == Window.RAMP_15M


def test_sunday_night_football_mountain():
    # SNF broadcast slot, 8:20 PM Eastern -- viewed here from a Mountain-
    # timezone game (kickoff itself expressed in Mountain local time).
    kickoff = datetime(2026, 9, 13, 18, 20, tzinfo=MOUNTAIN)
    now = kickoff - timedelta(minutes=1)
    assert classify_window(now=now, kickoff=kickoff) == Window.RAMP_5M


def test_monday_night_football_pacific():
    kickoff = datetime(2026, 9, 14, 20, 15, tzinfo=PACIFIC)
    now = kickoff - timedelta(hours=1, minutes=30)
    assert classify_window(now=now, kickoff=kickoff) == Window.RAMP_2H


def test_thursday_night_football_eastern():
    kickoff = datetime(2026, 9, 17, 20, 15, tzinfo=EASTERN)
    now = kickoff - timedelta(hours=25)
    assert classify_window(now=now, kickoff=kickoff) == Window.FAR


def test_game_crossing_utc_calendar_boundary():
    """An 8:20 PM Eastern (EST, so UTC-5) kickoff lands at 01:20 UTC the
    *next* calendar day -- classify_window must reason in true elapsed
    time, never accidentally compare only date-portions across that UTC
    midnight crossing."""
    kickoff_eastern = datetime(2026, 11, 8, 20, 20, tzinfo=EASTERN)  # after DST ends Nov 1, 2026 -- EST (UTC-5)
    kickoff_utc = kickoff_eastern.astimezone(timezone.utc)
    assert kickoff_utc.date() == datetime(2026, 11, 9).date()  # confirms the UTC-day crossing actually happens

    now = kickoff_eastern - timedelta(minutes=10)
    assert classify_window(now=now, kickoff=kickoff_eastern) == Window.RAMP_15M
    # Same instant, expressed in UTC instead -- must classify identically.
    assert classify_window(now=now.astimezone(timezone.utc), kickoff=kickoff_utc) == Window.RAMP_15M


# ---------------------------------------------------------------------------
# Daylight-saving-time transition correctness (2026: spring forward March
# 8, fall back November 1).
# ---------------------------------------------------------------------------


def test_dst_fall_back_produces_different_utc_instants_for_same_wall_clock_time():
    """1:00 PM Eastern the day before DST ends (EDT, UTC-4) and 1:00 PM
    Eastern the day DST ends (EST, UTC-5) are different UTC instants
    despite an identical wall-clock reading -- classify_window must key
    off the real elapsed time, not the wall-clock string."""
    pre_fallback = datetime(2026, 10, 31, 13, 0, tzinfo=EASTERN)  # EDT
    post_fallback = datetime(2026, 11, 1, 13, 0, tzinfo=EASTERN)  # EST, after 2am fallback

    assert pre_fallback.utcoffset() == timedelta(hours=-4)
    assert post_fallback.utcoffset() == timedelta(hours=-5)

    # Same "now" instant relative to each kickoff -- both 90 minutes out --
    # must classify identically despite the underlying UTC offset differing.
    assert classify_window(now=pre_fallback - timedelta(minutes=90), kickoff=pre_fallback) == Window.RAMP_2H
    assert classify_window(now=post_fallback - timedelta(minutes=90), kickoff=post_fallback) == Window.RAMP_2H


def test_dst_spring_forward_boundary_does_not_corrupt_elapsed_time():
    """A game whose polling window straddles the spring-forward transition
    (2am -> 3am on March 8, 2026, one hour skipped on the Eastern wall
    clock) must still compute a correct elapsed/remaining time.

    Note: naively subtracting these two datetimes directly (`kickoff -
    now`) is the exact CPython pitfall documented in windows.py's module
    docstring -- both share the same `ZoneInfo` tzinfo object, so a direct
    subtraction silently returns the wall-clock gap (12h) rather than the
    true 11h elapsed (2am->3am was skipped). Comparing via UTC is the only
    reliable way to state the expected gap in this test, exactly as
    classify_window itself now does internally.
    """
    kickoff = datetime(2026, 3, 8, 13, 0, tzinfo=EASTERN)  # EDT, after the 2am spring-forward
    now = datetime(2026, 3, 8, 1, 0, tzinfo=EASTERN)  # EST, before the spring-forward
    assert kickoff.astimezone(timezone.utc) - now.astimezone(timezone.utc) == timedelta(hours=11)
    assert classify_window(now=now, kickoff=kickoff) == Window.FAR


def test_classify_window_correct_despite_shared_tzinfo_object_across_dst_boundary():
    """Regression test for the exact bug windows.py's docstring documents
    finding: two datetimes sharing the same ZoneInfo tzinfo object,
    straddling a DST transition, where naive subtraction would silently
    give the wrong tier. `now` is 11 real hours before `kickoff` (11h ==
    FAR's threshold is >2h, so this must classify as FAR); a naive
    wall-clock subtraction would read it as exactly 12 wall-clock hours,
    which -- while still FAR here -- proves the underlying arithmetic is
    right, not just coincidentally landing in the same tier."""
    kickoff = datetime(2026, 3, 8, 13, 0, tzinfo=EASTERN)
    now = datetime(2026, 3, 8, 1, 0, tzinfo=EASTERN)
    assert now.tzinfo is kickoff.tzinfo  # confirms this is really the shared-object case
    assert classify_window(now=now, kickoff=kickoff) == Window.FAR

    # A second case where the wrong (naive, wall-clock) arithmetic would
    # actually flip the classification into a different tier than the
    # correct UTC-normalized arithmetic -- proves this isn't just "FAR
    # either way." Naive: 2h0m wall-clock gap -> RAMP_2H boundary exactly.
    # Correct (UTC-normalized): 1h0m real gap, one hour skipped -> RAMP_60M.
    kickoff2 = datetime(2026, 3, 8, 3, 0, tzinfo=EASTERN)  # 3:00 AM EDT (just after spring-forward)
    now2 = datetime(2026, 3, 8, 1, 0, tzinfo=EASTERN)  # 1:00 AM EST (just before spring-forward)
    assert now2.tzinfo is kickoff2.tzinfo
    assert classify_window(now=now2, kickoff=kickoff2) == Window.RAMP_60M


def test_all_four_continental_us_timezones_agree_when_the_instant_is_identical():
    kickoff_utc = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
    now_utc = kickoff_utc - timedelta(minutes=45)
    classifications = {
        classify_window(now=now_utc.astimezone(tz), kickoff=kickoff_utc.astimezone(tz))
        for tz in (EASTERN, CENTRAL, MOUNTAIN, PACIFIC, timezone.utc)
    }
    assert classifications == {Window.RAMP_60M}


# ============================================================================
# Injury Worker cadence (Phase 3E-5) -- classify_injury_window/
# should_poll_injuries/injury_poll_interval_seconds/injury_ttl_seconds.
# Day-of-week reference: 2026-09-13 is a Sunday (matches the Sunday-kickoff
# tests above), so 2026-09-16/17/18 are Wed/Thu/Fri and 2026-09-14/15/19
# are Mon/Tue/Sat -- verified via `date(...).strftime("%A")` before writing
# these, not assumed from a calendar lookup.
# ============================================================================


def test_injury_naive_now_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_injury_window(
            now=datetime(2026, 9, 16, 12, 0), kickoff=datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)
        )


def test_injury_naive_kickoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_injury_window(
            now=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc), kickoff=datetime(2026, 9, 20, 17, 0)
        )


def test_injury_naive_last_polled_at_is_rejected():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    kickoff = now + timedelta(days=4)
    with pytest.raises(ValueError, match="timezone-aware"):
        should_poll_injuries(now=now, kickoff=kickoff, last_polled_at=datetime(2026, 9, 15, 10, 0))


@pytest.mark.parametrize(
    "now_date,expected",
    [
        (datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), InjuryWindow.INFREQUENT),  # Monday
        (datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc), InjuryWindow.INFREQUENT),  # Tuesday
        (datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc), InjuryWindow.ACTIVE_WEEK),  # Wednesday
        (datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc), InjuryWindow.ACTIVE_WEEK),  # Thursday
        (datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), InjuryWindow.ACTIVE_WEEK),  # Friday
        (datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc), InjuryWindow.INFREQUENT),  # Saturday
    ],
)
def test_classify_injury_window_day_of_week_gating_far_from_kickoff(now_date, expected):
    # Kickoff is Sunday 2026-09-20 17:00 UTC -- always well beyond the 2h
    # final-ramp boundary for every `now` tested here, so day-of-week
    # gating alone determines the tier.
    kickoff = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)
    assert classify_injury_window(now=now_date, kickoff=kickoff) == expected


@pytest.mark.parametrize(
    "time_to_kickoff,expected",
    [
        (timedelta(hours=2), InjuryWindow.FINAL_RAMP),
        (timedelta(minutes=91), InjuryWindow.FINAL_RAMP),
        (timedelta(minutes=90), InjuryWindow.INACTIVE_LIST),  # the CONFIRMED ~90-minute boundary
        (timedelta(minutes=1), InjuryWindow.INACTIVE_LIST),
        (timedelta(0), InjuryWindow.STOPPED),
        (timedelta(minutes=-90), InjuryWindow.STOPPED),  # mid-game, well after kickoff
    ],
)
def test_classify_injury_window_final_ramp_boundaries(time_to_kickoff, expected):
    # `now` is a Sunday itself here -- proves these boundaries apply
    # regardless of day-of-week, exactly like the override test below.
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    kickoff = now + time_to_kickoff
    assert classify_injury_window(now=now, kickoff=kickoff) == expected


def test_classify_injury_window_just_beyond_final_ramp_falls_back_to_day_of_week():
    # 2h + 1s out on a Sunday (not Wed/Thu/Fri) -- beyond the final ramp,
    # so day-of-week gating resumes and this Sunday is INFREQUENT.
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)  # Sunday
    kickoff = now + timedelta(hours=2, seconds=1)
    assert classify_injury_window(now=now, kickoff=kickoff) == InjuryWindow.INFREQUENT


def test_injury_final_ramp_overrides_day_of_week_on_any_day():
    # Monday (would otherwise be INFREQUENT), but kickoff is 30 minutes
    # away -- Mac's explicit requirement: "increased polling approaching
    # kickoff" applies on any day, no Blueprint-stated day exemption.
    now = datetime(2026, 9, 14, 19, 30, tzinfo=timezone.utc)  # Monday
    kickoff = now + timedelta(minutes=30)
    assert classify_injury_window(now=now, kickoff=kickoff) == InjuryWindow.INACTIVE_LIST


def test_injury_stopped_window_has_no_poll_interval_and_never_polls():
    assert injury_poll_interval_seconds(InjuryWindow.STOPPED) is None
    now = datetime(2026, 9, 20, 20, 0, tzinfo=timezone.utc)
    kickoff = now - timedelta(minutes=5)  # already kicked off
    assert should_poll_injuries(now=now, kickoff=kickoff, last_polled_at=None) is False


def test_injury_ttl_matches_poll_interval_for_every_actively_polled_window():
    for window in InjuryWindow:
        if window is InjuryWindow.STOPPED:
            continue
        assert injury_ttl_seconds(window) == injury_poll_interval_seconds(window)


def test_injury_stopped_window_ttl_reuses_inactive_list_interval_not_infinite_or_zero():
    assert injury_ttl_seconds(InjuryWindow.STOPPED) == injury_poll_interval_seconds(InjuryWindow.INACTIVE_LIST)


def test_injury_active_week_interval_is_once_daily():
    # The one CONFIRMED number in the whole injury cadence -- "roughly
    # once daily Wednesday-Friday" -- is a literal 24h interval.
    assert injury_poll_interval_seconds(InjuryWindow.ACTIVE_WEEK) == 86400


def test_injury_infrequent_interval_is_looser_than_active_week():
    # ASSUMED (no Blueprint number for "infrequent") but must be
    # directionally correct: looser than the active-window cadence, since
    # that asymmetry is the entire point of the Blueprint's own wording.
    assert injury_poll_interval_seconds(InjuryWindow.INFREQUENT) > injury_poll_interval_seconds(
        InjuryWindow.ACTIVE_WEEK
    )


def test_injury_final_ramp_intervals_monotonically_tighten_toward_kickoff():
    assert (
        injury_poll_interval_seconds(InjuryWindow.ACTIVE_WEEK)
        > injury_poll_interval_seconds(InjuryWindow.FINAL_RAMP)
        > injury_poll_interval_seconds(InjuryWindow.INACTIVE_LIST)
    )


def test_should_poll_injuries_true_when_never_polled_and_window_is_active():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # Wednesday
    kickoff = now + timedelta(days=4)
    assert should_poll_injuries(now=now, kickoff=kickoff, last_polled_at=None) is True


def test_should_poll_injuries_false_when_interval_has_not_elapsed():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # Wednesday, ACTIVE_WEEK -- 86400s interval
    kickoff = now + timedelta(days=4)
    last_polled_at = now - timedelta(hours=1)
    assert should_poll_injuries(now=now, kickoff=kickoff, last_polled_at=last_polled_at) is False


def test_should_poll_injuries_true_once_interval_has_elapsed():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # Wednesday, ACTIVE_WEEK -- 86400s interval
    kickoff = now + timedelta(days=4)
    last_polled_at = now - timedelta(seconds=86401)
    assert should_poll_injuries(now=now, kickoff=kickoff, last_polled_at=last_polled_at) is True


def test_injury_window_dst_safety_reuses_classify_window_utc_normalization():
    # Same DST subtlety as test_dst_spring_forward_boundary_does_not_corrupt_elapsed_time
    # above, proven directly against classify_injury_window rather than
    # assumed inherited: two datetimes sharing the same ZoneInfo tzinfo
    # object straddling spring-forward must not fall back to a naive
    # wall-clock subtraction.
    kickoff = datetime(2026, 3, 8, 3, 0, tzinfo=EASTERN)  # 3:00 AM EDT (just after spring-forward)
    now = datetime(2026, 3, 8, 1, 0, tzinfo=EASTERN)  # 1:00 AM EST (just before spring-forward)
    assert now.tzinfo is kickoff.tzinfo
    # Naive (wrong) wall-clock gap: 2h0m -> FINAL_RAMP boundary exactly.
    # Correct (UTC-normalized) real gap: 1h0m, one hour skipped by the
    # spring-forward transition -> INACTIVE_LIST.
    assert classify_injury_window(now=now, kickoff=kickoff) == InjuryWindow.INACTIVE_LIST
