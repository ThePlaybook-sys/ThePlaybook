# Phase 8 Player Performance Context Foundation (2026-09-15)

MANSA HQ directive: "PHASE 8 PLAYER PERFORMANCE CONTEXT FOUNDATION."
Builds the smallest safe player-performance Context Intelligence
foundation the same-day Readiness Reassessment recommended -- a
**ONE-GAME foundation, not the multi-game Context Assembly Proof**, which
the reassessment already established cannot honestly be attempted today
(zero players anywhere have more than one real historical game). No
provider calls, no `build_evidence()` changes, no recommendation wiring,
no Week 2 data manufactured, no injury/lineup/PBP gaps solved.

---

## 1. Module created

Three new files, one extended field on an existing shared type:

- **`apps/ai-orchestrator/app/context_intelligence/observation_identity.py`**
  (new) -- the generic deduplication/observation-identity rule (Section
  2).
- **`apps/ai-orchestrator/app/context_intelligence/player_performance.py`**
  (new) -- the player-performance dimension module itself: `PlayerGameObservation`
  (one per real, deduplicated, point-in-time-eligible player/game pair),
  `resolve_player_game_observations` (pure, no I/O), and
  `compute_player_performance_context` (wraps the above into the shared
  `ContextualDimensionResult` shape).
- **`apps/ai-orchestrator/app/context_intelligence/models.py`** (extended)
  -- `ContextualDimensionResult` gains `data_completeness: str | None =
  None` and the new `DATA_COMPLETENESS_VALUES = ("joined", "partial",
  "unavailable")` constant (Section 3). Defaulted so no existing
  dimension/test was touched.
- **`apps/ai-orchestrator/app/persistence/context_intelligence_reads.py`**
  (extended) -- `read_all_player_stats`/`read_games_by_ids`, matching
  this module's own established "download once" read conventions
  exactly, so the new dimension module is genuinely runnable end to end,
  not merely a standalone compute function nothing can call.

Every field the directive's Section 1 required is present on
`PlayerGameObservation`: player identity (`player_id`/`player_name`),
game identity (`game_id`), event timestamp, opponent, position (when
reliable), the real stat fields (full, verbatim `stats` payload, never
stripped), role/usage signals (a curated real subset, Section on
`_ROLE_USAGE_FIELDS`), source/provenance (`ProvenanceRef`), reliability
limitations (`reliability_limitations`, always populated), and sample
size (at the dimension level, `ContextualDimensionResult.sample_size`).
**No derived metric is invented anywhere** -- every number surfaced is
either a raw persisted field or (for `passYardsPerAtt` etc.) a value the
source provider itself already computed and persisted, never something
this module calculates.

**Not wired into `engine.py`'s `SUPPORTED_DIMENSIONS`, `unsupported.py`'s
stub set, or `build_evidence()`.** Confirmed via `git status`: neither
file was touched by this pass. This is a deliberate boundary decision,
not an oversight -- it mirrors the prior readiness-reassessment pass's own
explicit recommendation to stop short of that wiring, and matches this
directive's own boundary instruction not to touch `build_evidence()` or
recommendation wiring. The module is built to the exact shape `engine.py`
would need to adopt it (a `compute_*_context` function returning
`ContextualDimensionResult`, same as `weather.py`/`venue.py`/`market.py`/
`news.py`) so that a future, separately-authorized pass can wire it in
with a one-line change, exactly as `engine.py`'s own docstring already
documents for `build_evidence()` itself.

---

## 2. Observation identity / deduplication rule

**Root cause investigated live, not assumed.** `apps/sports-intel-layer/
app/persistence/player_stats.py`'s `upsert_player_stat_row_if_changed`
already checks the latest existing row and skips writing when incoming
`stats` is byte-identical (correction-aware by design, matching
`app.persistence.team_stats`'s precedent). A live query against every one
of SEA@NE's 93 duplicated real players confirmed the two rows per player
are genuinely **not** byte-identical: the reliable stat categories
(receiving/rushing/passing volume) match exactly across both real
captures, but `stats.snapCounts`/`stats.miscellaneous.gamesStarted`
differ (e.g. JSN's own two rows: `offenseSnaps=0` in the 2026-09-10
20:38:42 capture, `offenseSnaps=45` in the 2026-09-14 23:02:03 capture)
-- exactly the fields the pipeline's own persisted `stats._unreliable_
fields`/`_unreliable_fields_reason` already self-discloses as unreliable
at this tier. **The persistence layer worked correctly**: it detected a
real difference and correctly preserved both rows rather than silently
overwriting one. The duplicate-row situation is Context Intelligence's
own open question ("which one row represents this game"), not a bug in
the pipeline that built this session's MSF work.

**The rule: most recent `created_at` wins**
(`observation_identity.resolve_canonical_observation`). Reuses the exact
same "latest row by `created_at`" ordering `player_stats.py`'s own
`_latest_player_stats_row` already applies. Generic (not hardcoded to
`player_stats`): takes any list of candidate rows sharing an `id_field`/
`tie_break_field`, returns the canonical row plus a disclosed
`duplicate_row_count` and every raw row's own id (`all_row_ids`) -- no
row is ever deleted, altered, or hidden; `player_performance.py` reads
this result and reports the count/ids in every affected observation's
own `reliability_limitations`.

**`created_at` used here answers a different question than a true
observation timestamp would, and the module docstring says so
explicitly**: safe for tie-breaking among rows that already, unambiguously,
describe the exact same already-completed real game; never reused as an
eligibility filter for whether a game counts as prior evidence relative
to some other target event (that job belongs to `player_performance.py`'s
point-in-time rule, Section 4, which uses the historical game's own
`scheduled_start` instead).

**Proof, JSN/SEA@NE, exactly one observation from two real rows**:
`test_duplicate_rows_collapse_to_exactly_one_observation` and the
dedicated `TestJSNSeaNeRealProof` class (Section 5) both assert
`len(observations) == 1` and `sample_size == 1` against real (not
synthetic) row data, while `duplicate_raw_row_count == 2` and
`provenance[0].row_count == 2` prove the second real row was never
hidden, only correctly excluded from the count.

---

## 3. `data_completeness` contract

Implemented as a new field on the SHARED `ContextualDimensionResult`
(`models.py`), not siloed to `player_performance.py` -- the 2026-09-09
design doc's own recommendation, generic enough for the eventual
multi-game/other-dimension future the directive asked for:

- `"joined"`: a real row/observation exists for the exact target entity
  (or the fact is static/time-invariant), retrieval code exists, nothing
  fabricated.
- `"partial"`: real data exists but with a named caveat.
- `"unavailable"`: no real row, no code path, or schema-only.

**Describes evidence availability, never prediction confidence** -- the
module docstring states this explicitly, and the code proves it:
`compute_player_performance_context` can (and today, always does) return
`data_completeness="joined"` together with `confidence=None` in the same
result (`test_single_observation_is_joined_but_insufficient_for_a_trend`)
-- real evidence was found, but there isn't enough of it yet to say
anything about trend/consistency, and the two facts are never conflated.
`player_performance.py` never produces `"partial"` from the dimension
level itself (matching `point_in_time.py`'s own established discipline
that "partial" is a dimension-specific judgment about which required
evidence *components* are missing -- left to a future pass, not invented
here); individual observations' own `reliability_limitations` carry that
finer-grained nuance instead (e.g. "opponent could not be determined,"
"snapCounts flagged unreliable").

**Missing data is never converted to zero, and confidence is never
inflated because a field merely exists** -- proven directly:
`test_no_observations_is_unavailable_never_zero` asserts `facts == {}`
(not a zero-filled shape) when nothing real exists; every numeric field
that can't be honestly computed (`confidence`, `similarity_score`) stays
`None` regardless of `data_completeness`, including in the "joined" case
with real evidence (Section on `confidence` always being `None` from this
dimension until a real trend/consistency methodology is designed -- named
explicitly in the module docstring as future, separate work).

**Sample coverage** is carried by the existing `sample_size` field,
paired with `data_completeness` rather than duplicated into a new field
-- `sample_size=1, data_completeness="joined"` together tell a consumer
exactly what exists today: real, but narrow.

The four pre-existing real dimensions (`weather.py`/`market.py`/
`news.py`/`venue.py`) and the six `unsupported.py` stubs were **not**
retrofitted with a `data_completeness` value by this pass -- the field
defaults to `None` for them (meaning "not yet classified," never
"unavailable"), keeping this pass's footprint to genuinely new work only,
per its own "smallest safe" scope.

---

## 4. Point-in-time safety rule

**The literal requirement -- a historical game occurring at or after the
target event must never be used -- is enforced deterministically**:
`resolve_player_game_observations` compares each candidate game's own
`games.scheduled_start` against an explicit `target_event_timestamp`,
strictly: `event_ts < target_ts`. A game whose kickoff equals or follows
the target event is excluded outright, never included with a caveat
(`test_game_exactly_at_target_timestamp_is_excluded_not_included` proves
the boundary is strict, not inclusive). A game missing from the caller's
`games_by_id` map is excluded outright too -- point-in-time eligibility
cannot be verified without a real kickoff to compare against, so "exclude,
never guess" applies exactly as `point_in_time.py` already established
for other missing-data cases.

**The fact that `player_stats` carries no observation timestamp is
addressed explicitly, not glossed over.** Unlike `weather_snapshots`/
`injury_reports`/`depth_chart_snapshots` (all handled by the existing
`point_in_time.py`, which resolves against each row's own `captured_at`),
`player_stats` has no such column. This module uses **event/game
chronology** instead -- the historical game's own kickoff, which is
knowable and real regardless of when MANSA happened to ingest the box
score -- exactly what the directive's "use event/game chronology where
defensible" instruction asks for. A completed game's real outcome was
already true the moment that game ended; late ingestion doesn't change
what was factually true, so anchoring eligibility to the game's own
kickoff (rather than to any `player_stats` row's `created_at`) does not
introduce look-ahead bias for THAT decision.

**The limitation this rule cannot close is named, not hidden.**
`PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION` (a module-level constant,
included in every single observation's own `reliability_limitations`,
verbatim, always) states plainly: this guarantees no game occurring at or
after the target event is ever included, but cannot verify finer-grained
timing -- specifically, whether a historical game's box score was
actually captured/known before the target event for two events close in
real time on the same day, since `player_stats` has no true capture
timestamp to check against. This is exactly the directive's own
instruction followed precisely: "if true point-in-time provenance cannot
be guaranteed for a field, label the limitation rather than pretending it
is safe."

---

## 5. JSN one-game proof

`TestJSNSeaNeRealProof` (`tests/context_intelligence/test_player_performance.py`)
runs the real module code against the exact live `player_stats`/`games`
values queried against DEV on 2026-09-15 (verbatim row ids, `created_at`
timestamps, and full `stats` payloads for both real rows -- not
synthesized):

- **Exactly one historical game observation**: `len(observations) == 1`,
  `sample_size == 1`, despite two real raw rows existing.
- **Real performance/usage evidence**: `role_usage_signals["receiving"]
  == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}` --
  the real, verified stat line from Section 3 of the prior readiness
  reassessment.
- **Provenance**: `provenance[0].table == "player_stats"`,
  `provenance[0].row_count == 2` -- both real rows disclosed, canonical
  row correctly identified as the newer one
  (`4ee8eae8-e213-4533-b099-3945d0d3fd41`, 2026-09-14 23:02:03).
- **Completeness**: `data_completeness == "joined"`, `sample_size == 1`,
  `insufficient_evidence == True` (honestly below the 2-game floor --
  this is a one-game foundation, not a trend proof, and the code says so
  itself).
- **Known unavailable context, disclosed rather than fabricated**:
  `opponent is None` (the live-confirmed `games.home_team`/`away_team`
  format mismatch -- `"SEA"`/`"NE"` vs. `teams.name`'s `"Seattle
  Seahawks"`/`"New England Patriots"`), with the exact reason named in
  `reliability_limitations`; the `snapCounts`-unreliable disclosure; the
  duplicate-row disclosure.
- **No duplicate inflation**: `sample_size == 1` and
  `facts["game_count"] == 1` at the dimension level, despite two real
  rows.

---

## 6. Tests

**26 new tests, all passing, zero I/O anywhere in this suite** (every
test is a pure in-memory call, matching this package's own established
convention for compute-layer modules):

- `test_observation_identity.py` (6): single-row no-op, most-recent-wins,
  order-independence, all-row-ids preserved, empty-input raises, custom
  tie-break field.
- `test_player_performance.py` (20): 11 mechanism tests on
  `resolve_player_game_observations` (required-field exposure,
  point-in-time exclusion at and past the boundary, missing-game
  exclusion, other-players'-rows ignored, duplicate collapse, unreliable-
  field handling, opponent success/failure, missing-position disclosure,
  multi-game ordering) + 4 tests on `compute_player_performance_context`
  (unavailable-never-zero, joined-but-insufficient, floor-crossing
  synthetic proof, dimension-level anti-inflation) + 5 in
  `TestJSNSeaNeRealProof` (Section 5, above) + 1 additional point-in-time
  sanity check for the exact proof game.

**Full `apps/ai-orchestrator` suite: 882 passed, zero regressions**
(confirmed by running the entire suite, not just the new files -- the new
`data_completeness` field's default value means no pre-existing test
needed updating).

---

## 7. Remaining limitations (honest, not fixed by this pass)

- **Not wired anywhere.** `engine.py`, `unsupported.py`, and
  `build_evidence()` are all untouched -- this module cannot be exercised
  by any real recommendation or Context Intelligence API call today. That
  wiring remains a separate, later, Phase-4-reopening decision, exactly
  as the directive's boundary requires.
- **Opponent/home-away resolution has a real, disclosed gap.**
  `games.home_team`/`away_team` are free-text and inconsistently
  formatted across real rows (some full team names, some short
  provider-style codes) with no foreign key to `teams` -- exact-match-only
  resolution (reusing `market_integrity.resolve_team_ids_by_name`'s own
  contract) fails for the SEA@NE proof game itself. Not fixed -- flagged
  as "no unrelated cleanup" per this pass's own boundary; the honest fix
  (a `teams.abbreviation` column, or a `games.home_team_id` foreign key)
  is a data-modeling change out of scope here.
- **Position is current/static, not historically tracked.** `players.
  position` is used as a reasonable proxy (position rarely changes within
  a season) but is not independently verified as-of any specific
  historical game -- disclosed in every observation's own
  `reliability_limitations`.
- **No trend/consistency methodology exists yet, even above the sample
  floor.** `confidence`/`similarity_score` are always `None` from this
  dimension today, regardless of `sample_size` -- designing that
  methodology (and deciding whether `RECENCY_HALF_LIFE_DAYS=14.0` is the
  right half-life for player form specifically, flagged not resolved,
  exactly per the 2026-09-09 design doc's own instruction) is future work.
- **Same-day timing precision is not guaranteed** -- see
  `PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION`, Section 4.
- **Injuries, lineup/depth breadth, game-state/PBP are untouched**, exactly
  as instructed -- none of the 2026-09-15 readiness reassessment's other
  open blockers are addressed by this pass.
- **`read_all_player_stats` fetches the whole table.** Fine at today's
  real scale (1,551 rows); a future pass at materially larger scale may
  need a `player_id`-scoped read instead, noted in that function's own
  docstring, not built here.

---

## 8. Exact smallest next Phase 8 step

Two independent, genuinely small next steps exist, and neither depends on
the other:

1. **Wire `player_performance` into `engine.py`'s `SUPPORTED_DIMENSIONS`**
   (move it out of `unsupported.py`'s stub set into a real call in
   `build_contextual_intelligence`, using the new `read_all_player_stats`/
   `read_games_by_ids` reads already built this pass) -- makes the module
   reachable via the existing Context Intelligence API surface
   (`ContextualIntelligenceResult`) for the first time, still **without**
   touching `build_evidence()` or any recommendation path. This is the
   natural, minimal continuation of this pass, requires no new data, and
   was deliberately left undone here per this pass's own explicit
   boundary.
2. **The real Context Assembly Proof itself** remains blocked on real
   time passing, not on code: the first moment any player has 2-3 real
   historical games is once a second real NFL week completes and
   auto-enrolls through the existing, unmodified dispatcher pipeline
   (~2026-09-21/22 for Week 2, per the 2026-09-15 reassessment) --
   **and, per the already-recorded MSF cancellation status (access ends
   2026-09-17), Week 2 will very likely complete after MSF access has
   already ended.** This module is built and tested to accept that data
   the moment it exists, from MSF or (per Section 9 below) any equivalent
   future provider, with zero further code change to `player_performance.py`
   itself.

---

## 9. Future multi-game path (documented, not built)

This module already accepts additional player-game observations with
**zero code change** the moment more real rows exist: `resolve_player_
game_observations` groups by `game_id` and returns one observation per
group already -- a second, third, or Nth real game for the same player
simply produces a longer `observations` list, correctly ordered
oldest-first, each with its own independently-computed
`role_usage_signals`/`reliability_limitations`/provenance.
`compute_player_performance_context`'s `sample_size`/`insufficient_
evidence`/`data_completeness` all already respond correctly to a larger
`observations` list (proven synthetically by
`test_reaching_the_sample_floor_flips_insufficient_evidence_off`, using
two invented games specifically to exercise this mechanism ahead of real
data existing).

**Does not require MSF specifically.** Nothing in `player_performance.py`
or `observation_identity.py` names MySportsFeeds, imports anything
MSF-specific, or assumes MSF's own `stats` field-naming conventions
beyond what's already generic (`targets`/`receptions`/`rushAttempts`/
etc. are standard football stat names, not an MSF-specific schema). A
future provider's normalized rows would only need to land in the same
`player_stats` table shape (`player_id`, `game_id`, `stats` jsonb,
`created_at`) via that provider's own persistence path (the existing
`persist_player_stats`'s own `provider_name` parameter already
demonstrates this project's standing convention for exactly this kind of
provider-neutral widening, established 2026-09-10, unrelated to this
pass) -- this module would pick up those new real rows automatically,
with the same deduplication and point-in-time-safety rules applying
identically regardless of which provider wrote them. `_extract_role_
usage_signals`'s reliance on `stats._unreliable_fields` (a marker this
session's own MSF pipeline introduced) would gracefully no-op for a
provider that never sets that key -- `unreliable = tuple(stats.get(
"_unreliable_fields", ()))` defaults to empty, meaning nothing is
excluded from `role_usage_signals` for a source that doesn't flag
anything, exactly the correct, honest default.
