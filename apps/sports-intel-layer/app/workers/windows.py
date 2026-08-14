"""Shared kickoff-proximity window classification (Volume 2 §8, Phase 3E-4).

**The single authoritative policy** reused by both:
1. adaptive worker polling cadence decisions (Odds Worker, Player Props
   Worker -- Phase 3E-4D/E), and
2. dynamic cache TTL selection (Decision 4, Phase 3E-4F).

Mac's explicit instruction: "There should be one authoritative window-
classification policy reused by ... worker polling decisions ... cache TTL
selection. Do not create two independent implementations of the same
timing rules." Both callers import `classify_window` from here; neither
computes a proximity-to-kickoff tier on its own.

**Blueprint basis (Volume 2 §8, v4.2/v4.1) -- read directly, not
reconstructed from memory:** Player Props Worker's row states exact window
boundaries: "1 morning snapshot, then ramping frequency through
2h/60min/15min/5min windows before kickoff, stopping at kickoff." Odds
Worker's row describes the same shape qualitatively ("Polling frequency
ramps up as a game's kickoff approaches (infrequent snapshots for games
still days out, every-few-minutes in the final hour, stopping at
kickoff)") and explicitly states: "Mirrors the Player Props Worker's
cadence shape below -- both are the same market-data category and share
the same real-world volatility pattern." That "mirrors" sentence is the
textual basis for applying the exact same six-tier classification to both
workers, rather than inventing a second, different set of numbers for Odds.

**CONFIRMED FROM VOLUME 2 §8:** the four ramp boundaries themselves --
2h, 60min, 15min, 5min before kickoff -- and that polling stops entirely
at kickoff.

**ASSUMED (flagged explicitly, not presented as directly confirmed
Blueprint fact):** the Blueprint states window *boundaries* but never a
numeric polling interval *within* each window, for either worker. This
module treats each boundary as also the polling interval for the tier it
opens (e.g. once inside the 2h-out window, poll every ~60 minutes -- the
width down to the *next* boundary) -- the most direct, non-arbitrary
reading of "ramping frequency through those windows," since the named
numbers are otherwise unused for anything. The "days out"/"1 morning
snapshot" language before the first ramp boundary is operationalized as a
flat 24-hour interval (one snapshot per day), consistent with Master
Refresh's own daily rhythm. The final [5min, 0) tier's interval (2
minutes) is a documented judgment call reading "every-few-minutes in the
final hour" (Odds Worker's own wording) as meaning multiple polls inside
that last 5-minute stretch, not just one. This interpretation is called
out explicitly in the Phase 3E-4 completion report for Mac's confirmation,
not silently treated as settled.

**Timezone/DST correctness (Phase 3E-4G):** `classify_window` requires
both `now` and `kickoff` to be timezone-aware -- a naive datetime raises
`ValueError` immediately rather than silently being treated as UTC or the
server's local time. This is the actual enforcement point of Mac's "Do not
base polling policy on the Railway server's local timezone" instruction:
there is no code path here that ever reads local time at all, aware or
otherwise.

**A real subtlety this module deliberately guards against, found while
writing its own DST tests (Phase 3E-4G):** CPython's own datetime
subtraction does NOT always correctly account for a DST offset change --
per the stdlib docs, "if both are aware and have the same tzinfo
attribute, the common tzinfo attribute is ignored and the base datetimes
are compared" (i.e. a *naive*, wall-clock subtraction). Two
`zoneinfo.ZoneInfo("America/New_York")`-tagged datetimes straddling a
spring-forward/fall-back transition share that same tzinfo object, so a
direct `kickoff - now` on them silently returns the *wall-clock* gap, not
the real elapsed time -- exactly the DST bug this phase's testing
requirement exists to catch. This module never subtracts two aware
datetimes directly: both `now` and `kickoff` are converted to UTC first
(`.astimezone(timezone.utc)`), which forces the subtraction through each
side's actual UTC offset regardless of whether the two inputs happen to
share a tzinfo object. Callers may pass any aware timezone (Eastern,
Pacific, UTC, whatever a provider returns) -- correctness never depends on
which one they chose or on both sides using the same one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum


class Window(str, Enum):
    #: More than 2 hours before kickoff -- "infrequent... days out" / "1
    #: morning snapshot".
    FAR = "far"
    #: (60 min, 2h] before kickoff.
    RAMP_2H = "ramp_2h"
    #: (15 min, 60 min] before kickoff.
    RAMP_60M = "ramp_60m"
    #: (5 min, 15 min] before kickoff.
    RAMP_15M = "ramp_15m"
    #: (0, 5 min] before kickoff -- "every-few-minutes in the final hour".
    RAMP_5M = "ramp_5m"
    #: At or after kickoff -- polling stops (CONFIRMED FROM VOLUME 2 §8).
    STOPPED = "stopped"


#: Window -> poll interval in seconds. `None` means "never poll" (STOPPED).
#: See module docstring for the ASSUMED boundary-as-interval mapping.
_POLL_INTERVAL_SECONDS: dict[Window, int | None] = {
    Window.FAR: 86400,
    Window.RAMP_2H: 3600,
    Window.RAMP_60M: 900,
    Window.RAMP_15M: 300,
    Window.RAMP_5M: 120,
    Window.STOPPED: None,
}

#: Window -> cache TTL in seconds (Decision 4, Phase 3E-4F) -- identical to
#: the poll interval for every actively-polled window, by design: a cached
#: value is considered fresh for exactly as long as until the next poll
#: for that same window would occur. STOPPED is the one deliberate
#: exception: no further polling happens once a game has kicked off (this
#: worker generation covers pregame markets only -- live in-game odds are
#: out of scope, DEFERRED), so the last pregame snapshot's TTL reuses
#: RAMP_5M's short interval rather than being either infinite or zero --
#: a documented judgment call, not a Blueprint-specified number.
_TTL_SECONDS: dict[Window, int] = {
    **{w: v for w, v in _POLL_INTERVAL_SECONDS.items() if v is not None},
    Window.STOPPED: _POLL_INTERVAL_SECONDS[Window.RAMP_5M],
}

_BOUNDARIES: tuple[tuple[timedelta, Window], ...] = (
    (timedelta(minutes=5), Window.RAMP_5M),
    (timedelta(minutes=15), Window.RAMP_15M),
    (timedelta(minutes=60), Window.RAMP_60M),
    (timedelta(hours=2), Window.RAMP_2H),
)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got a naive one: {value!r}")


def classify_window(*, now: datetime, kickoff: datetime) -> Window:
    """Classifies how close `kickoff` is to `now`, into one of the six
    tiers above. Both arguments must be timezone-aware (Phase 3E-4G) --
    raises `ValueError` immediately on a naive datetime rather than
    guessing a timezone.
    """
    _require_aware(now, "now")
    _require_aware(kickoff, "kickoff")

    # Normalize through UTC before subtracting -- see module docstring's
    # "real subtlety" note. Never subtract the two aware inputs directly:
    # if they happen to share a tzinfo object (e.g. both tagged with the
    # same zoneinfo.ZoneInfo across a DST transition), Python's own
    # datetime subtraction silently falls back to a naive wall-clock
    # subtraction instead of accounting for the offset change.
    time_to_kickoff = kickoff.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    if time_to_kickoff <= timedelta(0):
        return Window.STOPPED
    for boundary, window in _BOUNDARIES:
        if time_to_kickoff <= boundary:
            return window
    return Window.FAR


def poll_interval_seconds(window: Window) -> int | None:
    """Seconds between polls for `window`, or `None` if this window should
    never be polled (STOPPED)."""
    return _POLL_INTERVAL_SECONDS[window]


def ttl_seconds(window: Window) -> int:
    """Cache TTL in seconds for data classified into `window` (Decision 4)."""
    return _TTL_SECONDS[window]


def should_poll(*, now: datetime, kickoff: datetime, last_polled_at: datetime | None) -> bool:
    """True if a poll is due right now: `kickoff`'s window has a poll
    interval (isn't STOPPED) and either nothing has been polled yet or at
    least that interval has elapsed since the last poll. Both `now` and
    `kickoff` (and `last_polled_at`, if given) must be timezone-aware.
    """
    if last_polled_at is not None:
        _require_aware(last_polled_at, "last_polled_at")

    window = classify_window(now=now, kickoff=kickoff)
    interval = poll_interval_seconds(window)
    if interval is None:
        return False
    if last_polled_at is None:
        return True
    # Same UTC-normalization requirement as classify_window -- see its
    # docstring's "real subtlety" note.
    elapsed = now.astimezone(timezone.utc) - last_polled_at.astimezone(timezone.utc)
    return elapsed >= timedelta(seconds=interval)
