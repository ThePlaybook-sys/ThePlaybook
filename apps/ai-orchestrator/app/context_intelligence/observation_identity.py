"""Generic real-observation deduplication for Context Intelligence
(Player Performance Context Foundation pass, 2026-09-15, HQ-authorized
"MANSA -- PHASE 8 PLAYER PERFORMANCE CONTEXT FOUNDATION"). Root cause
this module addresses: `player_stats` has no uniqueness constraint on
`(player_id, game_id)` and no observation timestamp at all (unlike
`weather_snapshots`/`injury_reports`/`depth_chart_snapshots`, which all
carry `captured_at` and are already handled by `point_in_time.py`) -- so
two real ingestion attempts for the same real game can legitimately leave
two real rows behind for the same player.

**Live-investigated root cause (not assumed): this is not accidental
double-writing.** `apps/sports-intel-layer/app/persistence/player_stats.py`'s
`upsert_player_stat_row_if_changed` already checks the latest existing row
and skips writing when incoming `stats` is byte-identical -- correction-
aware by design, matching `app.persistence.team_stats`'s own precedent.
Live query against SEA@NE (2026-09-10, MSF game 163541, 93 duplicated
players) confirmed the two rows per player are genuinely NOT byte-
identical: the reliable stat fields (targets/receptions/yards/attempts)
match exactly across both captures, but `stats.snapCounts`/`stats.
miscellaneous.gamesStarted` differ (e.g. one capture reports
`offenseSnaps=45`, the other `offenseSnaps=0` for the same real play) --
exactly the fields the pipeline's own persisted `stats._unreliable_
fields`/`_unreliable_fields_reason` already self-discloses as unreliable
at this tier. `upsert_player_stat_row_if_changed` correctly detected a
real difference and correctly preserved both rows rather than silently
overwriting one -- this module's job is Context Intelligence's OWN
question, "which one row represents this game for this player," not a
verdict that the persistence layer did anything wrong. **No row is ever
deleted or modified by this module or by anything built in this pass** --
every duplicate stays exactly where it is in `player_stats`, preserved as
raw historical evidence; this module only decides which one a consumer
should treat as canonical for a single count.

**The rule: most recent `created_at` wins.** Reuses the same "latest row
by `created_at`" ordering `player_stats.py`'s own `_latest_player_stats_row`
already applies for its own correction-aware write decision (`order:
created_at.desc, limit: 1`) -- the newest real capture is the freshest
information this system has about that game, and picking anything else
would silently prefer a possibly-superseded capture. This is a
disclosed-conservative policy choice, not empirically derived, matching
this package's own established convention for undecided numbers/rules
(see `scoring.py`'s own module docstring).

**`created_at` here answers a different question than `point_in_time.py`'s
timestamps -- do not conflate them.** `point_in_time.py` resolves "which
real historical fact was true AS OF some past target moment," using a
row's own `captured_at` as an *event-relative* filter -- using `created_at`
for that purpose would risk look-ahead leakage (a late-arriving row could
wrongly appear "current" for an early target). This module answers a
narrower, safe, retrospective-only question instead: "of N rows that
already, unambiguously, all describe the exact same already-completed
real game, which one do we prefer" -- never used to decide whether a game
is eligible relative to any OTHER game's target timestamp (that job
belongs to `player_performance.py`'s own point-in-time safety rule, which
uses the historical game's own `scheduled_start`, never any `player_stats`
row's `created_at`). Reusing `created_at` for tie-breaking among rows that
all already passed that eligibility check is safe; reusing it to
determine eligibility itself would not be, and this module never does the
latter.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CanonicalObservationResult:
    """`canonical` is the selected row, verbatim, never merged/altered.
    `duplicate_row_count` is the TOTAL number of raw rows found for this
    entity (1 when there was no duplicate at all -- not "0 extra"), so a
    caller can tell "exactly one real capture" from "N real captures,
    with duplicate-row work stripped away to produce one" at a glance.
    `all_row_ids` preserves every raw row's own identifier for a reader
    who wants to go look at the non-canonical rows directly -- nothing
    about this result hides that they exist."""

    canonical: dict
    duplicate_row_count: int
    all_row_ids: tuple[str, ...] = field(default_factory=tuple)


def resolve_canonical_observation(
    candidate_rows: list[dict], *, id_field: str = "id", tie_break_field: str = "created_at"
) -> CanonicalObservationResult:
    """The one generic implementation of "pick the freshest real row when
    more than one exists for the same real-world fact." `candidate_rows`
    must already be filtered to rows describing the SAME entity (e.g. the
    same `(player_id, game_id)` pair) -- this function does no entity
    grouping itself, mirroring `point_in_time.resolve_point_in_time`'s own
    "caller filters, this function only orders/selects" convention.

    Raises `ValueError` for an empty list -- unlike `point_in_time`'s
    resolver (which legitimately returns an "unavailable" result for zero
    eligible rows, because "no historical observation existed yet" is a
    normal real-world outcome), an empty `candidate_rows` here means the
    caller's own entity-grouping already found nothing to deduplicate --
    that is the caller's job to detect and report as its own
    "unavailable" case, not this function's."""
    if not candidate_rows:
        raise ValueError("resolve_canonical_observation requires at least one candidate row")

    ordered = sorted(candidate_rows, key=lambda row: row[tie_break_field], reverse=True)
    canonical = ordered[0]
    all_ids = tuple(row[id_field] for row in candidate_rows if id_field in row)

    return CanonicalObservationResult(
        canonical=canonical,
        duplicate_row_count=len(candidate_rows),
        all_row_ids=all_ids,
    )


__all__ = ["CanonicalObservationResult", "resolve_canonical_observation"]
