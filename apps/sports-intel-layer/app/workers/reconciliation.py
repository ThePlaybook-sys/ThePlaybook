"""Postgame bounded-reconciliation schedule (Phase 3E-8, Decision 5).

**APPROVED PRODUCT/ARCHITECTURE DECISION for the current implementation --
not a SportsDataIO-confirmed provider requirement.** PROGRESS.md's
2026-08-10 corrections research cited SportsDataIO's own published
guidance (secondary-source, primary vendor site egress-blocked) suggesting
a *range* ("10min-2h for the first 24h, tracked 48-72h"), but Mac's 3E-8
decision approved a concrete, fixed schedule rather than that range
directly -- the two are related but not identical, and this module
implements only the approved schedule, never presenting it as
vendor-mandated.

**One place these intervals live, so they can be changed centrally without
rewriting the worker (Mac's explicit instruction).** `app.workers.
postgame_worker` never hardcodes an offset -- it only calls
`due_checkpoints`/`is_reconciliation_complete` below.

Deliberately NOT an extension of `app.workers.windows` (kickoff-proximity
classification) -- a different axis entirely (time-since-finalization, not
time-to-kickoff), the same reasoning `app.workers.news_worker` already
applied when it chose not to force itself into that module either.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: CHECKPOINT_OFFSETS[i] = (label, time-since-finalization at which this
#: checkpoint becomes due). "initial" is due at the moment of finalization
#: (offset zero) -- the first fetch, not a "reconciliation" in the
#: corrections sense, but expressed the same way for a uniform schedule.
#: APPROVED PRODUCT/ARCHITECTURE DECISION (Mac, 2026-08-18, 3E-8 Decision
#: 5) -- not provider-confirmed.
CHECKPOINT_OFFSETS: tuple[tuple[str, timedelta], ...] = (
    ("initial", timedelta(0)),
    ("+10m", timedelta(minutes=10)),
    ("+30m", timedelta(minutes=30)),
    ("+2h", timedelta(hours=2)),
    ("+24h", timedelta(hours=24)),
    ("+72h", timedelta(hours=72)),
)

#: The last checkpoint in the schedule -- once this has run, the stored
#: result is treated as authoritative for Phase 3 ingestion purposes
#: (Decision 5), and no further checks are ever due.
_FINAL_CHECKPOINT_LABEL = CHECKPOINT_OFFSETS[-1][0]


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got a naive one: {value!r}")


def due_checkpoints(
    *, now: datetime, finalized_at: datetime, checks_done: frozenset[str]
) -> list[str]:
    """Returns every checkpoint label that is due (elapsed time since
    `finalized_at` has reached or passed its offset) but not yet in
    `checks_done`, in schedule order. Both `now` and `finalized_at` must be
    timezone-aware -- same discipline as `app.workers.windows.
    classify_window`, never a naive-datetime guess."""
    _require_aware(now, "now")
    _require_aware(finalized_at, "finalized_at")

    elapsed = now.astimezone(timezone.utc) - finalized_at.astimezone(timezone.utc)
    return [
        label
        for label, offset in CHECKPOINT_OFFSETS
        if elapsed >= offset and label not in checks_done
    ]


def is_reconciliation_complete(checks_done: frozenset[str]) -> bool:
    """True once the final approved checkpoint has run -- no further
    checks are ever due for this game after that, per Decision 5."""
    return _FINAL_CHECKPOINT_LABEL in checks_done
