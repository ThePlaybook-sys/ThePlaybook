# Phase 8 Historical Context Assembly V1 (2026-09-15)

MANSA HQ directive: "PHASE 8 HISTORICAL CONTEXT ASSEMBLY V1." Builds the
first real, assembled historical Context Intelligence package -- through
the existing engine, using persisted evidence only, for Jaxon
Smith-Njigba / SEA@NE. **A ONE-GAME historical proof, not the final
multi-game Context Assembly Proof.** No wait for Week 2. No
`build_evidence()` wiring. No prediction/confidence score anywhere in the
new assembly layer.

---

## 1. Assembly object / contract

New module: `apps/ai-orchestrator/app/context_intelligence/context_package.py`.
Zero I/O, zero new computation over raw data -- a pure summary layer over
an already-built `ContextualIntelligenceResult`.

- **`DimensionCompleteness`**: one dimension's verdict --
  `dimension`, `completeness` (`"joined"`/`"partial"`/`"unavailable"`),
  `reason` (the real `insufficient_evidence_reason`, when set),
  `sample_size`, `provenance` (the real `ProvenanceRef` tuple, unchanged).
- **`ContextPackage`**: the package-level summary -- `game_id`,
  `player_id`, `generated_at`, `target_event_timestamp`,
  `joined_dimensions`/`partial_dimensions`/`unavailable_dimensions`
  (sorted tuples of dimension names), `dimension_completeness` (dict of
  the above, one entry per dimension, all ten always present),
  `known_limitations` (deduplicated, sorted real `insufficient_evidence_
  reason` strings), and `intelligence` (the full underlying
  `ContextualIntelligenceResult`, unchanged, always available for a
  caller that wants the raw detail). **No prediction, probability, or
  confidence field exists anywhere on this type** -- proven structurally
  by `test_no_prediction_or_confidence_field_exists_anywhere_on_the_
  package`, which inspects the dataclass's own field names.
- **`assemble_context_package(intelligence, *, player_id, target_event_
  timestamp) -> ContextPackage`**: the one function. Never raises; every
  dimension already present on `intelligence.dimensions` (all ten,
  always, per `engine.py`'s own guarantee) is classified, none skipped.

**Derivation rule (generic, no per-dimension special-casing, requires
zero changes to `weather.py`/`market.py`/`news.py`/`venue.py`/
`unsupported.py`):**

```
if result.data_completeness is not None:   # player_performance already sets this
    completeness = result.data_completeness
elif not result.insufficient_evidence:
    completeness = "joined"
elif result.facts:
    completeness = "partial"               # real target-game evidence found, comparable pool too small
else:
    completeness = "unavailable"           # no real row, no code path -- every unsupported.py stub
                                            #   already produces facts={} unconditionally
```

This rule is derived entirely from fields the four Phase 8.1 dimensions
and `unsupported.py`'s stubs already, correctly compute -- no
retroactive rewrite of any existing dimension module was needed or made.

---

## 2. Point-in-time protections

Inherited, not re-implemented, exactly as the module docstring states:
every dimension already enforces its own point-in-time safety before
`assemble_context_package` ever sees the result --
`player_performance.py`'s explicit `target_event_timestamp` comparison
against each historical game's own `scheduled_start` (unchanged from the
two prior passes), and `weather.py`/`market.py`/`news.py`/`venue.py`'s
real-data-only, current-game-scoped reads (also unchanged). This pass
adds no new point-in-time logic -- it surfaces each dimension's own real
`insufficient_evidence_reason` in `known_limitations` and carries
`target_event_timestamp` verbatim on the package so a reader can see
exactly what moment the package claims to be honest "as of." No future
information leaks into the historical package: the real proof (Section 5)
uses `now = 2026-09-15T10:30:00Z`, strictly after SEA@NE's own kickoff
(2026-09-10T00:20:00Z), and `player_performance`'s own point-in-time rule
(proven again in this pass's tests) would exclude any game whose kickoff
had not yet occurred relative to that timestamp.

---

## 3. Package-level completeness

Independent of confidence, proven directly in the real proof (Section 5):
`market` is `"joined"` with its own real `confidence` computed
separately (a genuine number, not `None`, since its comparable pool
exceeds the sample floor with real recency/consistency signal), while
`player_performance` is ALSO `"joined"` with `confidence=None` (honestly
below its own, differently-scoped sample floor) -- two dimensions, both
`"joined"`, with completely different confidence states, proving the two
concepts are never conflated. **No prediction score is created anywhere**
-- confirmed structurally (Section 1) and by inspection of every test in
this pass.

---

## 4. Player performance semantics preserved

Unchanged from the two prior passes, reconfirmed by the full existing
test suite plus the new real package proof:

- One player + one game = one observation (`sample_size == 1` for JSN in
  the real proof, despite two real raw `player_stats` rows).
- Correction rows collapse to one canonical observation
  (`duplicate_raw_row_count == 2` still disclosed on the single
  observation).
- Raw/correction provenance remains fully visible
  (`provenance[0]["row_count"] == 2`).
- No invented trend/consistency signal -- `player_performance`'s own
  `confidence` stays `None` in the real proof, exactly as designed.

---

## 5. Real JSN / SEA@NE Context Package

Assembled through `build_contextual_intelligence` (the real engine
entry point) + `assemble_context_package` (this pass's new layer)
together, with every Supabase boundary respx-mocked to real, live-queried
DEV values (2026-09-15) -- `test_jsn_sea_ne_real_historical_context_
package`, `tests/context_intelligence/test_engine.py`.

| Dimension | Verdict | Why |
|---|---|---|
| `player_performance` | **JOINED** | 1 real, deduplicated observation (SEA@NE, 2 raw rows collapsed to 1 canonical); real 11 targets/8 receptions/122 yards/1 TD; opponent resolved to "New England Patriots" via the real provider-identity chain. |
| `market` | **JOINED** | Real target-game spread history (opening 3.5 -> latest 3.0) plus a real comparable pool (live-confirmed: 5 distinct other real games with odds history, at least 4 with computable spread movement -- well above `INSUFFICIENT_SAMPLE_FLOOR=2`). |
| `weather` | **PARTIAL** | Real target-game weather found (63.1°F, 0.9mph wind, Overcast, real WeatherAPI observation) -- but only 1 real same-dome-bucket comparable (PHI@WAS) exists, below the floor of 2, so no similarity/confidence score is computed. |
| `venue` | **PARTIAL** | Real venue identity found (Lumen Field, Seattle, WA, outdoor) -- but 0 other real tracked games share this exact venue (live-confirmed), below the floor. |
| `news` | **UNAVAILABLE** | Real news data exists for both teams generally (confirmed by the 2026-09-13 Real History Observation Window pass), but the CURRENT, unmodified `engine.py` news path resolves team_ids via an exact match on `games.home_team`/`away_team` (`resolve_team_ids_by_name`) -- and SEA@NE's real `home_team`/`away_team` are the short codes `"SEA"`/`"NE"`, which do not exactly match `teams.name`'s `"Seattle Seahawks"`/`"New England Patriots"`. **This is the same format-mismatch class of bug the Engine Integration pass fixed for `player_performance`'s opponent resolution -- confirmed here, live, to also affect `news.py`, unfixed by this pass** (see Section 7). |
| `injuries`, `roster_role`, `team_performance`, `depth_lineup`, `game_state_pbp` | **UNAVAILABLE** | Unchanged `unsupported.py` stubs -- real, disclosed, unconditional. |

**Proven directly** (all in `test_jsn_sea_ne_real_historical_context_package`):
- **No duplicate inflation**: `player_performance.sample_size == 1`
  despite 2 real raw rows.
- **No future leakage**: `now` used is strictly after SEA@NE's own
  kickoff; point-in-time exclusion re-confirmed by dedicated tests
  elsewhere in this pass.
- **Opponent resolves deterministically**: `"New England Patriots"`,
  via the real provider-identity chain (Engine Integration pass),
  not text matching.
- **Real performance values remain intact**: 11 targets, 8 receptions,
  122 receiving yards, 1 receiving TD -- read verbatim from the real
  canonical row.
- **Package completeness is independent of confidence**: demonstrated by
  `market` (joined, real confidence computed) vs. `player_performance`
  (joined, `confidence=None`) coexisting correctly in the same package.

---

## 6. Cross-player opponent-identity sanity check (audit only, no new implementation pass)

Per the directive's explicit instruction, this reused the EXISTING
`extract_msf_team_provider_ids`/`resolve_opponent_by_team_id` functions
(Engine Integration pass) against two additional real players/games,
queried live against DEV on 2026-09-15 -- no new implementation:

| Player | Team | Game | `games.home_team`/`away_team` | Real MSF ids | Resolved opponent | home/away |
|---|---|---|---|---|---|---|
| Courtland Sutton | Denver Broncos | KC@DEN | `"KC"`/`"DEN"` | 73/72 | Kansas City Chiefs | away |
| John Williams | Green Bay Packers | MIN@GB | `"MIN"`/`"GB"` | 63/62 | Minnesota Vikings | away |
| (Jaxon Smith-Njigba, for comparison) | Seattle Seahawks | SEA@NE | `"SEA"`/`"NE"` | 79/50 | New England Patriots | home |

All three real `game_events` raw payloads were extracted by the exact
same, unmodified `extract_msf_team_provider_ids` function with zero
per-game branching (`test_cross_player_sanity_extraction_shape_
identical_across_all_three_real_games`), and all three real
`team_provider_ids`/`teams` mappings resolved correctly. **The
opponent-identity chain generalizes** -- confirmed across 3 of the 16
real games (SEA@NE, KC@DEN, MIN@GB), not merely coincidentally correct
for the one proof game. Full generalization across all 16 real games was
not exhaustively re-verified this pass (see Section 7's "smallest next
step").

---

## 7. Tests

**17 new tests (11 assembly-mechanism + 3 cross-player sanity + 1 full
real package proof + 2 route-fixture corrections), full suite 910
passed, zero regressions** (up from 895):

- `test_context_package.py` (new, 11 tests): the generic JOINED/PARTIAL/
  UNAVAILABLE derivation rule (each of the three states individually,
  all three coexisting in one package, the explicit `data_completeness`
  override respected verbatim), every-dimension-classified-exactly-once,
  `known_limitations` deduplication, `to_json` shape, and the structural
  no-prediction-field proof.
- `test_player_performance.py` (+3 tests): the cross-player sanity check
  (Section 6).
- `test_engine.py` (+1 test, plus mock-fixture additions): the full real
  JSN/SEA@NE Context Package proof (Section 5), built on real weather/
  venue/market/odds values gathered live from DEV.

**Full `apps/ai-orchestrator` suite: 910 passed, zero regressions.**

---

## 8. Remaining blockers

- **`news.py` inherits the same `games.home_team`/`away_team`
  format-mismatch bug the Engine Integration pass fixed for
  `player_performance`'s opponent resolution -- confirmed live for
  SEA@NE, not fixed by this pass** (out of this pass's explicit scope;
  flagged here per the blueprint-vs-reality disclosure discipline, not
  silently patched). This means the news dimension will report
  UNAVAILABLE for any game whose `home_team`/`away_team` are stored as
  short codes rather than full names, even when real, relevant news data
  exists for both teams.
- **Still not wired into `build_evidence()` or any recommendation
  path.** Unchanged, per this pass's explicit boundary.
- **Cross-player opponent-identity generalization confirmed for 3 of 16
  real games, not exhaustively for all 16.** Section 6's sanity check is
  real but intentionally small, per the directive's own "do not create a
  separate implementation pass for this" instruction.
- **Market/weather/venue/news `data_completeness` is derived, not
  natively stored** -- `weather.py`/`market.py`/`news.py`/`venue.py`
  themselves still don't set `ContextualDimensionResult.data_completeness`
  directly (only `player_performance.py` does); `context_package.py`'s
  derivation rule computes it correctly today, but a future change to any
  of those four modules' own `insufficient_evidence`/`facts` semantics
  would need to preserve the derivation rule's assumptions.
- **Only one real historical game exists for JSN (and, per the
  2026-09-15 readiness reassessment, for any player)** -- this remains a
  ONE-GAME proof, not the final multi-game Context Assembly Proof,
  exactly as instructed. Not claimed otherwise anywhere in this report.
- **No trend/consistency scoring, no probability/prediction score
  anywhere** -- exactly as instructed, structurally proven.

---

## 9. Exact smallest next step toward `build_evidence()` integration

Two independent, small candidates, neither executed by this pass:

1. **Fix `news.py`'s team-identity resolution using the same
   provider-identity chain** (`resolve_team_identity_for_games`,
   Engine Integration pass) instead of `resolve_team_ids_by_name`'s
   exact-name match -- would make `news` genuinely JOINED for SEA@NE and
   likely most/all of the 16 real games, closing the real gap Section 5
   found live. Small, isolated, does not touch `build_evidence()`.
2. **Wire `ContextPackage`/`ContextualIntelligenceResult` into
   `build_evidence()`** via the one documented line
   (`"contextual_performance": contextual_intelligence.to_json()`,
   `engine.py`'s own docstring) -- still requires separate,
   explicit HQ authorization to reopen Phase 4, per the standing "Do NOT
   reopen Phase 4" instruction reconfirmed by every pass in this series.
   This pass's `ContextPackage` object is now the natural summary a
   caller on the `build_evidence()` side would want first (completeness
   before raw detail), making that eventual wiring smaller when
   authorized, but it is **not** done here.

This document does not execute either. No `build_evidence()` change, no
recommendation change, no schema change, no trend/prediction scoring,
and no fabricated second historical game were made or attempted.
