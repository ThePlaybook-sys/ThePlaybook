"""Deterministic failure backoff for the Odds Worker (2026-09-16, "ODDS
WORKER COST + FAILURE HARDENING").

**The problem this solves.** `app.workers.windows` answers "how close is
kickoff, and is this game due by cadence?" It has no concept of a game that
is polled but cannot be *used* -- an event with no team mapping, a kickoff
outside tolerance, an ambiguous candidate. Cadence alone treats such a game
as due on every tick forever, because cadence was fed from
`odds_snapshots.captured_at` and an unresolved poll writes no snapshot.

This module is the second half of due-selection: cadence says *may*, backoff
says *not yet*. A game is polled only when BOTH agree.

**Why this is separate from `windows.py` rather than folded into it.**
`windows.py` is the shared kickoff-proximity policy -- Player Props Worker
uses the identical instance of it, and Injury Worker extends it. Failure
backoff is not a cadence concept and is not shared with those workers, so
adding it there would widen a module three callers depend on in order to
serve one. Kept separate, `windows.py` stays exactly what its docstring says
it is.

**The schedule.** Exponential, base 15 minutes, doubling, capped at 6 hours:

    failures  1  ->    15m   (one cron tick)
              2  ->    30m
              3  ->     1h
              4  ->     2h
              5  ->     4h
              6+ ->     6h   (cap)

Three deliberate properties:

1. **The base is one cron tick, not less.** A backoff shorter than the cron
   period is indistinguishable from no backoff at all, so 15 minutes is the
   smallest value that can actually change behaviour. The first failure
   therefore costs exactly one skipped tick -- a transient hiccup recovers
   almost immediately.

2. **The cap is 6 hours, not infinity.** A permanently-broken game still
   retries four times a day, so a repair lands within hours without anyone
   re-running anything. This is the directive's "no permanent quarantine
   unless explicitly justified", and nothing here justifies one: the
   2026-09-16 incident was repaired by inserting 15 database rows, after
   which the affected games needed to become due again on their own.

3. **Backoff never makes a call happen.** It can only ever suppress one. A
   game still inside its backoff window is removed from the due set; if the
   due set empties as a result, the worker makes no provider call at all,
   which is the entire economic point.

**ASSUMED, and flagged as such.** No Blueprint volume specifies a backoff
schedule for a provider-side resolution failure -- this concept did not exist
before the 2026-09-16 hardening. The numbers above are an explicit, disclosed
policy default in the same tradition as `MANUAL_SEED_MAX_ATTEMPTS`,
`ADAPTIVE_WEIGHT_LEARNING_RATE` and `THRESHOLD_VERSION`: chosen for stated
reasons, recorded, and never presented as a confirmed Blueprint number.

**Relationship to `MANUAL_SEED_MAX_ATTEMPTS`.** That cap (odds_worker.py,
added 2026-09-07 after an identical incident) excludes a manually-seeded game
after 3 unproductive attempts, and is explicitly documented as "never applied
to a normal Schedule/Master-Refresh-sourced game... those correctly keep
retrying a real, temporarily-unresolved team mapping forever." That judgment
assumed such gaps are transient; the 2026-09-16 gap was permanent and the
"forever" ran literally. This module is the general answer that cap was a
narrow special case of. The cap is left in place and untouched -- it is a
hard exclusion for a bad manual seed, whereas this is a slowdown for any
game, and the two compose without conflict.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Outcome vocabulary, matching the CHECK constraint on
#: `odds_worker_poll_state.last_attempt_outcome` exactly. Kept as constants so
#: a typo is an ImportError here rather than a silently-unmatched branch that
#: would fail OPEN back into every-tick spending.
OUTCOME_SUCCESS = "success"
#: The provider answered, but this game's event could not be resolved to a
#: canonical game (no team mapping, kickoff out of tolerance, ambiguous).
OUTCOME_UNRESOLVED = "unresolved"
#: The provider call itself failed, so nothing could be attributed to this
#: game one way or the other.
OUTCOME_PROVIDER_FAILURE = "provider_failure"

#: First backoff step. One cron tick -- see property 1 above.
BACKOFF_BASE_SECONDS = 900
#: Ceiling. Six hours -- see property 2 above.
BACKOFF_MAX_SECONDS = 21600


def backoff_seconds(consecutive_failure_count: int) -> int:
    """Seconds a game must wait after its last ATTEMPT before it may be
    considered due again, given how many consecutive non-success attempts it
    has accumulated.

    Zero failures means zero wait -- a healthy game is governed purely by
    `app.workers.windows`, exactly as it was before this module existed.
    """
    if consecutive_failure_count <= 0:
        return 0
    # Cap the exponent before shifting, not the result after: a large stored
    # counter (a game that has been broken for weeks) must not build an
    # enormous intermediate value just to be clamped back down.
    steps = min(consecutive_failure_count - 1, 16)
    return min(BACKOFF_BASE_SECONDS << steps, BACKOFF_MAX_SECONDS)


def backoff_elapsed(
    *,
    now: datetime,
    last_attempt_at: datetime | None,
    consecutive_failure_count: int,
) -> bool:
    """True if this game's backoff window has passed, so cadence alone may
    decide whether it is due.

    Returns True for a game with no failures and for a game with no recorded
    attempt at all -- in both cases there is nothing to back off from, and
    this function must never be the reason a never-seen game is skipped.
    """
    if consecutive_failure_count <= 0:
        return True
    if last_attempt_at is None:
        # Failures recorded but no attempt timestamp is not a state this
        # worker can produce. Treating it as "waited long enough" fails
        # toward normal cadence rather than toward silent permanent
        # suppression, which is the safer direction for a scheduling guard.
        return True
    required = backoff_seconds(consecutive_failure_count)
    # Same UTC-normalization discipline as windows.should_poll: never
    # subtract two aware datetimes that might share a tzinfo across a DST
    # transition.
    elapsed = now.astimezone(timezone.utc) - last_attempt_at.astimezone(timezone.utc)
    return elapsed >= timedelta(seconds=required)


def next_failure_count(*, current: int, outcome: str) -> int:
    """The counter to persist after an attempt with `outcome`.

    A success resets to zero unconditionally -- one genuine capture proves
    the game resolves, so whatever was wrong is over and the game returns to
    ordinary cadence immediately. Anything else increments by exactly one.
    """
    if outcome == OUTCOME_SUCCESS:
        return 0
    return current + 1
