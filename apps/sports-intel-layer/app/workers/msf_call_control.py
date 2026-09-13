"""MSF completed-game boxscore call-control policy (Permanent Box Score
Worker Build, 2026-09-11, HQ-authorized).

**The already-approved policy, not a fresh number** -- exactly the
schedule HQ's Sunday Ingestion Preflight Correction pass locked in
(`docs/ops/phase-8-sunday-ingestion-preflight-correction-2026-09-10.md`):
first eligibility check at kickoff+3h30m, subsequent not-ready follow-up
checks spaced ~1 hour apart, hard cap 4 scheduled completion checks per
game. One place these numbers live, reused by
`app.workers.msf_postgame_worker`, which never hardcodes an offset --
same "one place, not scattered" convention `app.workers.reconciliation`
already established for SportsDataIO's own, differently-shaped
checkpoint schedule (a different concern, a different cadence, correctly
NOT unified with this module -- see that module's own docstring for why
`app.workers.windows` wasn't reused there either).

**Distinct from `app.workers.windows`/`app.workers.reconciliation`
deliberately**: `windows.py` classifies *pre*-kickoff proximity (a
different axis, time-*to*-kickoff); `reconciliation.py` is SportsDataIO's
own approved +10m/+30m/+2h/+24h/+72h post-finalization schedule, a
different provider with a different, already-locked cadence. This
module is MSF's own *is-it-even-finished-yet* completion-check schedule,
measured from kickoff (not from finalization -- finalization is exactly
what these checks are trying to discover), and governs the ONE thing
`app.workers.reconciliation` deliberately never touches: whether to make
another live provider call at all.

**`attempt_count` distinguishes provider checks from internal processing
retries (HQ's explicit rule 3 requirement).** Every function here counts
in units of "one completed provider-check attempt" -- a bounded local
transient-retry loop inside a single check (see
`app.workers.msf_postgame_worker`'s own fetch wrapper) is NOT a second
attempt for this module's purposes; it's part of making attempt N
happen at all. Internal processing (identity activation, stat
persistence) retries after a successful capture are a completely
separate concern this module has no opinion on -- those never touch
`attempt_count`, and a game resuming from `validated` state makes zero
new provider calls in the first place.

## Cache/rate-aware scheduling (Pre-Live Worker Hardening, 2026-09-13)

Known real MSF evidence (Gate B's own captured response headers, Sunday
Ingestion Preflight Correction's own audit): `Cache-Control:
no-transform, max-age=10800` (a 3-hour CDN edge cache) on every MSF
boxscore response this project has ever captured. "Do not blindly
schedule a new provider check one hour later if the previous response
advertises a longer valid cache interval" -- `cache_aware_next_check_at`
below extends (never shortens) the default `FOLLOWUP_CHECK_OFFSET` to
respect a real, provider-advertised `max-age` when it's longer.

A 429 response's own `Retry-After` header gets the identical treatment
via `retry_after_aware_next_check_at` -- extends, never shortens, the
default cadence. Both functions are pure extensions of `next_check_at`
itself: with no signal present, behavior is byte-identical to before
this pass. **Neither function changes `HARD_CAP_ATTEMPTS` or
`attempt_count` semantics in any way** -- they only ever affect WHEN the
next already-budgeted check happens, never whether one happens or how
many total checks a game gets. 5xx/network failures are deliberately
untouched by either function -- rule 3's "bounded transient retry policy
remains separate" is enforced structurally: `_default_fetch_boxscore`
only ever populates `retry_after_seconds` on an actual 429, and
`cache_max_age_seconds` only ever on an actual 200 (see
`app.workers.msf_postgame_worker`'s own `BoxscoreFetchResult`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: APPROVED (Sunday Ingestion Preflight Correction, 2026-09-10): the
#: first completion check is not fired at kickoff -- MSF's own confirmed
#: 3-hour CDN edge cache plus a realistic average completion time makes
#: an earlier check unlikely to reveal anything, so the first check is
#: deliberately deferred this far past kickoff.
FIRST_CHECK_OFFSET = timedelta(hours=3, minutes=30)

#: APPROVED: every subsequent not-ready follow-up is spaced ~1 hour after
#: the check that found the game not yet COMPLETED.
FOLLOWUP_CHECK_OFFSET = timedelta(hours=1)

#: APPROVED hard ceiling: no more than 4 scheduled completion checks are
#: ever made for one game, regardless of outcome (not-ready, transient
#: failure, or otherwise) -- reaching this cap without a COMPLETED result
#: escalates rather than silently continuing to poll forever.
HARD_CAP_ATTEMPTS = 4

#: Bounded LOCAL transient retries within a single check attempt (rule 3:
#: "transient transport/server failures are separate from not-ready...
#: bounded local transient retries only"). Deliberately small and
#: immediate (no artificial backoff sleep added -- disclosed, not a
#: silent omission: a real network round trip already provides natural
#: spacing, and this worker's own cadence is hourly-at-tightest, so an
#: in-process sleep would only slow down a diagnostic/test run for no
#: real benefit). Exhausting these within one tick is what turns a
#: transient failure into that tick's own recorded outcome -- it does
#: NOT by itself burn through `HARD_CAP_ATTEMPTS` faster than a single
#: normal check would.
MAX_LOCAL_TRANSIENT_RETRIES = 2


def first_check_at(kickoff: datetime) -> datetime:
    """The UTC instant a game's first completion check becomes eligible.
    `kickoff` must be timezone-aware."""
    if kickoff.tzinfo is None or kickoff.tzinfo.utcoffset(kickoff) is None:
        raise ValueError(f"kickoff must be a timezone-aware datetime, got a naive one: {kickoff!r}")
    return kickoff.astimezone(timezone.utc) + FIRST_CHECK_OFFSET


def next_check_at(now: datetime) -> datetime:
    """The UTC instant the next not-ready follow-up check becomes
    eligible, measured from `now` (the check that just found the game
    not yet COMPLETED) -- not from kickoff again."""
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError(f"now must be a timezone-aware datetime, got a naive one: {now!r}")
    return now.astimezone(timezone.utc) + FOLLOWUP_CHECK_OFFSET


def hard_cap_reached(attempt_count: int) -> bool:
    """True once `attempt_count` has reached the approved ceiling --
    the caller must stop scheduling further automatic checks and
    escalate instead."""
    return attempt_count >= HARD_CAP_ATTEMPTS


def parse_cache_control_max_age(value: str | None) -> int | None:
    """Parses the `max-age` directive (seconds) out of a `Cache-Control`
    header value. Tolerant of other directives and whitespace (e.g. the
    exact real value MSF has been observed to send, `"no-transform,
    max-age=10800"`), case-insensitive on the directive name. Returns
    `None` if absent, malformed, or negative -- never fabricated, never
    guessed."""
    if not value:
        return None
    for part in value.split(","):
        part = part.strip()
        if part.lower().startswith("max-age="):
            raw = part.split("=", 1)[1].strip()
            try:
                seconds = int(raw)
            except ValueError:
                return None
            return seconds if seconds >= 0 else None
    return None


def parse_retry_after_seconds(value: str | None, *, now: datetime) -> int | None:
    """Parses a `Retry-After` header value -- either delta-seconds (the
    common real-world form) or an HTTP-date (RFC 7231) -- into whole
    seconds from `now`. Returns `None` if absent, unparseable, or would
    resolve to a non-positive delay -- never fabricated, never negative."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        seconds = int(value)
        return seconds if seconds > 0 else None
    try:
        from email.utils import parsedate_to_datetime

        target = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta_seconds = (target - now.astimezone(timezone.utc)).total_seconds()
    return int(delta_seconds) if delta_seconds > 0 else None


def cache_aware_next_check_at(*, now: datetime, cache_max_age_seconds: int | None) -> datetime:
    """`next_check_at(now)`, extended (never shortened) to respect a
    provider-advertised `Cache-Control` `max-age` when it's longer than
    the default follow-up offset. With `cache_max_age_seconds=None`
    (no header, or an unparseable one), behavior is identical to
    `next_check_at`."""
    default_next = next_check_at(now)
    if cache_max_age_seconds is None:
        return default_next
    cache_based_next = now.astimezone(timezone.utc) + timedelta(seconds=cache_max_age_seconds)
    return max(default_next, cache_based_next)


def retry_after_aware_next_check_at(*, now: datetime, retry_after_seconds: int | None) -> datetime:
    """`next_check_at(now)`, extended (never shortened) to respect a 429
    response's own `Retry-After` -- never schedules sooner than the
    already-approved cadence, but waits longer when the provider
    explicitly asks for it. With `retry_after_seconds=None`, behavior is
    identical to `next_check_at`."""
    default_next = next_check_at(now)
    if retry_after_seconds is None:
        return default_next
    retry_based_next = now.astimezone(timezone.utc) + timedelta(seconds=retry_after_seconds)
    return max(default_next, retry_based_next)


__all__ = [
    "FIRST_CHECK_OFFSET",
    "FOLLOWUP_CHECK_OFFSET",
    "HARD_CAP_ATTEMPTS",
    "MAX_LOCAL_TRANSIENT_RETRIES",
    "first_check_at",
    "next_check_at",
    "hard_cap_reached",
    "parse_cache_control_max_age",
    "parse_retry_after_seconds",
    "cache_aware_next_check_at",
    "retry_after_aware_next_check_at",
]
