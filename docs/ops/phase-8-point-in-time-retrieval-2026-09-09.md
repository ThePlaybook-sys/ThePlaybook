# Phase 8 Point-in-Time Context Retrieval (2026-09-09)

**Status: implemented, HQ-authorized.** Real code, pure functions only,
no I/O, not wired into `build_evidence()` or any dimension's compute
function. New module: `apps/ai-orchestrator/app/context_intelligence/
point_in_time.py`.

## What was built

The audited rule (`docs/ops/phase-8-context-assembly-integration-design-
2026-09-09.md` Section 3), implemented once as `resolve_point_in_time()`,
plus three one-line, table-specific wrappers:

- `resolve_weather_point_in_time` — `weather_snapshots`, keyed by `game_id`.
- `resolve_injury_point_in_time` — `injury_reports`, keyed by `game_id`.
- `resolve_lineup_point_in_time` — `depth_chart_snapshots`, keyed by
  `team_id` (team-scoped since the Phase 8.2 redesign, unlike the other
  two — deliberately not defaulted to `game_id`).

All three delegate to the one generic core function — the ordering rule
(`captured_at <= target_event_timestamp`, latest eligible row wins) is
written exactly once, never duplicated per dimension.

## `completeness` semantics — the one judgment call this pass required

HQ asked for `joined | partial | unavailable` without defining `partial`
precisely, and none of the five required test names imply a specific
`partial` scenario. Resolved as follows, recorded here since it's a
judgment call rather than a literal instruction:

- **`unavailable`**: zero rows satisfy `captured_at <= target_event_
  timestamp` for the entity — whether no rows exist at all, or every row
  that exists postdates the target. `data` is always `None`.
- **`joined`**: at least one eligible row exists, and no row for the same
  entity postdates the target either — the resolved observation is
  unambiguously the last known state.
- **`partial`**: at least one eligible row exists (real data IS
  returned) **and** at least one other row for the same entity postdates
  the target too. The future row is never selected — the resolved data
  is still exactly the correct "as of" answer — but this is disclosed
  rather than left indistinguishable from the clean `joined` case, since
  a reader may want to know a later (correctly unused) observation
  exists.

This makes `partial` a genuinely informative, non-arbitrary signal rather
than a guessed freshness threshold (no numeric "how stale is too stale"
constant was invented, matching this project's own "disclosed-
conservative policy constants only where truly needed" discipline).

## Historical correctness

- Never reads `daily_game_intelligence` (current-only, per its own
  migration comment) or any "most recent" reader — this module only ever
  filters an already-fetched row list by `captured_at <= target`, so
  there is no code path that can select a current-only value as
  historical truth.
- Event time (`target_event_timestamp`), observation time (`observed_at`,
  the resolved row's own `captured_at`), and retrieval time (`retrieved_
  at`, `now`) are three distinct `PointInTimeProvenance` fields, never
  collapsed — proven by a dedicated test asserting all three are
  genuinely different values in the same scenario.
- No silent fallback to the latest/current row: candidates are built
  *only* from rows satisfying the audited rule; a future-only row is
  tracked (for `candidate_row_count` and the `partial` disclosure) but is
  structurally never eligible for selection — proven directly by
  `test_only_a_future_observation_exists_never_leaks_backward`.

## Tests

**13 new tests**, `apps/ai-orchestrator/tests/context_intelligence/
test_point_in_time.py`, covering every HQ-required scenario plus the
`partial`/`joined` contrast and each dimension-specific wrapper's own
field wiring:
- exact prior observation → `joined`.
- multiple observations, deliberately out of chronological input order →
  the latest eligible one wins, never the earliest or an input-order
  artifact.
- no observation before event (zero rows, and rows-for-a-different-
  entity) → honest `unavailable`, never an exception or a fabricated
  result.
- future observation must not leak backward — tested in its purest form
  (only a future row exists) and in combination with a real eligible row
  (the future row's payload never appears in `data`, `completeness`
  becomes `partial`).
- a contrast case (multiple eligible rows, nothing future) proving
  `partial` is driven specifically by an excluded future row, not merely
  by there being more than one row.
- timestamp/provenance preservation on both the `joined` and
  `unavailable` paths.
- an ISO-string `target_event_timestamp` input (not only a `datetime`).
- each of the three dimension-specific wrappers, proving correct
  table/entity-field wiring (including that the lineup wrapper ignores a
  game-scoped row entirely, since it keys on `team_id`).

**Full ai-orchestrator suite: 855/855 passing** (842 pre-existing + 13
new), zero regressions.

## Out of scope, exactly as specified

`build_evidence()` was not touched. No provider was called. Gate B was
not touched. No schema was added (no player-game or any other new
table/column). No recommendation logic was changed. Staging/production
were not touched. This module is a complete, tested, reusable building
block with no call site yet — wiring it into `engine.py`/`build_evidence()`
remains a separate, later, explicitly-authorized pass.
