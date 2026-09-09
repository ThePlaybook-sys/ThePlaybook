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

## `completeness` semantics — corrected 2026-09-09

**This section replaces an earlier, incorrect version of this document.**
The first implementation made `completeness` depend on whether a later
(correctly-excluded) observation also existed for the same entity —
`joined` when nothing postdated the target, `partial` when something
did. HQ corrected this: a later post-event observation is normal
(providers keep observing after any given moment) and must never make a
correctly resolved historical observation `partial`. The generic
resolver's job is narrower than that: determine only whether an eligible
historical observation was resolved.

- **`unavailable`**: zero rows satisfy `captured_at <= target_event_
  timestamp` for the entity — whether no rows exist at all, or every row
  that exists postdates the target. `data` is always `None`.
- **`joined`**: at least one eligible row exists. The resolved
  observation is the correct "as of" answer, full stop — whether or not
  a later observation *also* exists elsewhere in the entity's history is
  irrelevant to this result and is no longer tracked as a distinct
  signal.

**`partial` is a real, reserved value in the wider vocabulary but is
never produced by this generic module.** It is reserved for a future,
dimension-specific layer (not built in this pass) that knows a
dimension's *required evidence components* and can determine that some,
but not all, of them are available — a genuinely different kind of
judgment than "was one eligible historical observation found," which is
all this module answers.

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
  *only* from rows satisfying the audited rule; a future row is counted
  in `candidate_row_count` (an informational total, not a completeness
  signal) but is structurally never eligible for selection — proven
  directly by `test_only_a_future_observation_exists_never_leaks_backward`.

## Tests

**13 tests**, `apps/ai-orchestrator/tests/context_intelligence/
test_point_in_time.py`, covering every HQ-required scenario and each
dimension-specific wrapper's own field wiring:
- exact prior observation → `joined`.
- multiple observations, deliberately out of chronological input order →
  the latest eligible one wins, never the earliest or an input-order
  artifact.
- no observation before event (zero rows, and rows-for-a-different-
  entity) → honest `unavailable`, never an exception or a fabricated
  result.
- future observation must not leak backward — tested in its purest form
  (only a future row exists, `completeness` is `unavailable`) and in
  combination with a real eligible row (the future row's payload never
  appears in `data`, and `completeness` resolves `joined` — corrected
  2026-09-09; a prior version of this test asserted `partial` here,
  which was wrong).
- a paired test proving `completeness` is identically `joined` whether
  or not a later observation exists elsewhere in the entity's history —
  the corrected semantics stated directly, not just implied.
- timestamp/provenance preservation on both the `joined` and
  `unavailable` paths.
- an ISO-string `target_event_timestamp` input (not only a `datetime`).
- each of the three dimension-specific wrappers, proving correct
  table/entity-field wiring (including that the lineup wrapper ignores a
  game-scoped row entirely, since it keys on `team_id`).

**Full ai-orchestrator suite: 855/855 passing** (842 pre-existing + 13
in this module), zero regressions, both before and after the semantics
correction.

## Out of scope, exactly as specified

`build_evidence()` was not touched. No provider was called. Gate B was
not touched. No schema was added (no player-game or any other new
table/column). No recommendation logic was changed. Staging/production
were not touched. This module is a complete, tested, reusable building
block with no call site yet — wiring it into `engine.py`/`build_evidence()`
remains a separate, later, explicitly-authorized pass.
