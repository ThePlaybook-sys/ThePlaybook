"""Historical point-in-time retrieval (Phase 8 Point-in-Time Context
Retrieval pass, 2026-09-09, HQ-authorized). Implements, once, generically,
the audited rule from `docs/ops/phase-8-context-assembly-integration-
design-2026-09-09.md` Section 3:

    captured_at <= target_event_timestamp
    ORDER BY captured_at DESC
    LIMIT 1

-- "the most recent real observation that existed at or before the
moment being reconstructed," never the globally-latest row for an
entity. Pure function over already-fetched rows, no I/O, matching this
package's own `weather.py`/`venue.py`/`market.py`/`news.py` convention
(`app.context_intelligence.__init__`'s own "no LLM calls, I/O only for
real Supabase reads" discipline -- this module has no I/O at all, by
design, so it can be unit-tested without any HTTP mocking).

**This module does NOT fetch rows itself and is NOT wired into
`build_evidence()`, `engine.py`, or any dimension's own compute function
-- an explicitly separate, later, HQ-authorized pass.** A caller
(not built here) would fetch a dimension's full row history the same
"download once" way `context_intelligence_reads.py` already does for
weather/odds/venue, then hand that list to one of the three thin
wrappers below.

**Why this exists as its own module, not inline in weather.py/etc.:**
the same three-line rule is genuinely identical across every snapshot-
shaped table this project has (`weather_snapshots`, `injury_reports`,
`depth_chart_snapshots` -- all `(entity_id, captured_at, payload)`,
per the design doc's own generic statement of the rule). Writing it once
here and reusing it via three one-line wrappers is the direct
alternative to writing three near-identical point-in-time queries by
hand, one per dimension, the way `weather.py`'s own *contextual-
similarity* pool-building logic is understandably dimension-specific
(different fields, different similarity scale) but this specific
lookup is not.

**Event time / observation time / retrieval time, kept distinct (the
design doc's own "single most important discipline"):** `target_event_
timestamp` is the moment being reconstructed (e.g. kickoff) -- never
confused with `now`. `observed_at` on the result is the resolved row's
own `captured_at` -- when the underlying fact was actually recorded,
never confused with either of the other two. `retrieved_at` is `now` --
when this resolution itself ran, always far in the future of the other
two for a genuine historical reconstruction. All three are carried on
`PointInTimeProvenance`, never collapsed into one field.

**`completeness`, defined precisely, not just named (corrected 2026-09-09
per HQ's Point-in-Time Completeness Semantics Correction -- an earlier
version of this module made `completeness` depend on whether a later,
correctly-excluded observation also existed; that was wrong and has been
removed):**

This generic resolver determines exactly one thing: whether an eligible
historical observation was resolved. It never infers evidence
completeness from the mere existence of *later* observations -- a later
observation is normal (providers keep observing after any given moment)
and must simply remain ineligible for this lookup, with no effect on
`completeness` whatsoever.

- `UNAVAILABLE`: zero rows satisfy `captured_at <= target_event_
  timestamp` for this entity -- whether because no rows exist for the
  entity at all, or every row that exists postdates the target. `data`
  is always `None` in this case -- there is never a silent fallback to
  the globally-latest (possibly future) row.
- `JOINED`: at least one eligible row exists. The resolved observation
  is the correct "as of `target_event_timestamp`" answer, full stop --
  whether or not a later observation *also* exists elsewhere in the same
  entity's history is irrelevant to this result and is not tracked here.

`PARTIAL` is a real, reserved value in this vocabulary but is **never
produced by this module**. It belongs to a dimension-specific layer this
pass does not build -- one that knows a dimension's *required evidence
components* (e.g. "this dimension needs both a confirmed status AND a
description field, and only the status resolved") and can determine that
some, but not all, of them are available. That is a different kind of
judgment than this module makes, and must not be collapsed into it. A
future dimension-specific caller may itself decide to report `partial`
by composing multiple `resolve_point_in_time()` results (or other
signals) -- this module's own job stops at "was one eligible historical
observation found."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.context_intelligence.scoring import parse_ts


@dataclass(frozen=True)
class PointInTimeProvenance:
    """Event time / observation time / retrieval time, kept distinct --
    see module docstring. `candidate_row_count` is every row that exists
    for this entity, regardless of timing; `eligible_row_count` is the
    subset satisfying `captured_at <= target_event_timestamp`. Both are
    plain, informational counts -- neither one drives `completeness`,
    which depends only on whether `eligible_row_count > 0`."""

    table: str
    entity_id_field: str
    entity_id: str
    target_event_timestamp: str  # ISO -- the moment being reconstructed
    observed_at: str | None  # ISO -- the resolved row's own captured_at, None iff unavailable
    retrieved_at: str  # ISO -- now, when this resolution ran
    candidate_row_count: int
    eligible_row_count: int


@dataclass(frozen=True)
class PointInTimeResult:
    #: "joined" | "unavailable" -- this module never produces "partial";
    #: see module docstring. "partial" remains a valid, reserved value in
    #: the wider vocabulary for a future dimension-specific layer that
    #: knows required evidence components, not this generic resolver.
    completeness: str
    data: dict | None  # the resolved row, verbatim, never a fabricated/merged value
    reason: str | None  # set iff completeness == "unavailable"
    provenance: PointInTimeProvenance


def resolve_point_in_time(
    observations: list[dict],
    *,
    table: str,
    entity_id_field: str,
    entity_id: str,
    timestamp_field: str,
    target_event_timestamp: datetime | str,
    now: datetime | None = None,
) -> PointInTimeResult:
    """The one generic implementation of the audited rule. `observations`
    may hold rows for many entities at once (the "download once, reuse
    everywhere" shape every other real dimension in this package already
    fetches with) -- this function filters to `entity_id_field ==
    entity_id` itself, exactly like `compute_weather_context` filtering
    `all_weather_rows` down to one `game_id`.

    Determines exactly one thing: whether an eligible historical
    observation (`captured_at <= target_event_timestamp`) was resolved.
    Never falls back to the globally-latest row when no eligible one
    exists: candidates are built ONLY from eligible rows. A row that
    postdates the target is excluded from selection entirely and has NO
    effect on `completeness` -- later observations are normal (a
    provider keeps observing after any given moment) and must simply
    remain ineligible, never treated as evidence of a "partial" result."""
    now = now or datetime.now(timezone.utc)
    target_ts = parse_ts(target_event_timestamp)

    entity_rows = [row for row in observations if row.get(entity_id_field) == entity_id]
    candidate_row_count = len(entity_rows)

    eligible: list[tuple[datetime, dict]] = []
    for row in entity_rows:
        observed_ts = parse_ts(row[timestamp_field])
        if observed_ts <= target_ts:
            eligible.append((observed_ts, row))

    eligible_row_count = len(eligible)

    if not eligible:
        return PointInTimeResult(
            completeness="unavailable",
            data=None,
            reason=(
                f"no real {table} observation exists at or before {target_ts.isoformat()} "
                f"for {entity_id_field}={entity_id!r}"
            ),
            provenance=PointInTimeProvenance(
                table=table,
                entity_id_field=entity_id_field,
                entity_id=entity_id,
                target_event_timestamp=target_ts.isoformat(),
                observed_at=None,
                retrieved_at=now.isoformat(),
                candidate_row_count=candidate_row_count,
                eligible_row_count=0,
            ),
        )

    observed_ts, resolved_row = max(eligible, key=lambda pair: pair[0])

    return PointInTimeResult(
        completeness="joined",
        data=resolved_row,
        reason=None,
        provenance=PointInTimeProvenance(
            table=table,
            entity_id_field=entity_id_field,
            entity_id=entity_id,
            target_event_timestamp=target_ts.isoformat(),
            observed_at=observed_ts.isoformat(),
            retrieved_at=now.isoformat(),
            candidate_row_count=candidate_row_count,
            eligible_row_count=eligible_row_count,
        ),
    )


def resolve_weather_point_in_time(
    weather_snapshot_rows: list[dict], *, game_id: str, target_event_timestamp: datetime | str, now: datetime | None = None
) -> PointInTimeResult:
    """`weather_snapshots(game_id, weather_data, captured_at)` -- the
    real, historical-capable table (never `daily_game_intelligence.
    weather`, which is current-only and must never be used as historical
    truth -- see module docstring and the design doc's own Section 3)."""
    return resolve_point_in_time(
        weather_snapshot_rows,
        table="weather_snapshots",
        entity_id_field="game_id",
        entity_id=game_id,
        timestamp_field="captured_at",
        target_event_timestamp=target_event_timestamp,
        now=now,
    )


def resolve_injury_point_in_time(
    injury_report_rows: list[dict], *, game_id: str, target_event_timestamp: datetime | str, now: datetime | None = None
) -> PointInTimeResult:
    """`injury_reports(game_id, report_data, captured_at)` -- the real,
    historical-capable table (never `daily_game_intelligence.injuries` or
    any "most recent" reader, both current-only)."""
    return resolve_point_in_time(
        injury_report_rows,
        table="injury_reports",
        entity_id_field="game_id",
        entity_id=game_id,
        timestamp_field="captured_at",
        target_event_timestamp=target_event_timestamp,
        now=now,
    )


def resolve_lineup_point_in_time(
    depth_chart_snapshot_rows: list[dict], *, team_id: str, target_event_timestamp: datetime | str, now: datetime | None = None
) -> PointInTimeResult:
    """`depth_chart_snapshots(team_id, depth_chart_data, captured_at)` --
    team-scoped (Phase 8.2 redesign), not game-scoped, so this resolves
    by `team_id`, not `game_id`, unlike the other two. Never
    `players.team_id` (a current-only fast pointer, not a historical
    record) or `roster_memberships` alone for role/depth purposes (that
    table answers "who is on this team," not "what was the depth chart
    role as of this game")."""
    return resolve_point_in_time(
        depth_chart_snapshot_rows,
        table="depth_chart_snapshots",
        entity_id_field="team_id",
        entity_id=team_id,
        timestamp_field="captured_at",
        target_event_timestamp=target_event_timestamp,
        now=now,
    )


__all__ = [
    "PointInTimeProvenance",
    "PointInTimeResult",
    "resolve_point_in_time",
    "resolve_weather_point_in_time",
    "resolve_injury_point_in_time",
    "resolve_lineup_point_in_time",
]
