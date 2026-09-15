# Phase 8 build_evidence() Context Integration (2026-09-15)

MANSA HQ directive: "PHASE 8 BUILD_EVIDENCE CONTEXT INTEGRATION." The
authorized implementation of the same-day Admission Decision
(`docs/ops/phase-8-context-probability-model-admission-decision-
2026-09-15.md`) -- integrates exactly the four admitted dimensions
(venue, player_performance, market, weather) into
`ProbabilityModelingAgent.build_evidence`. No news fix, no injury/PBP/
lineup work, no new scoring, no recommendation-logic change, no provider
calls.

---

## 1. Exact `build_evidence()` changes

Two files touched, both minimal and additive:

- **`apps/ai-orchestrator/app/agents/committee_context.py`**:
  `SequentialDecisionContext` gains one new, defaulted field --
  `context_package: ContextPackage | None = None`. Appended after every
  existing optional field; every real production construction site
  (`app/orchestration/cycle.py`, the only real caller) uses keyword args
  and never sets it, so it defaults to `None` there today, unchanged.
- **`apps/ai-orchestrator/app/agents/probability_modeling.py`**:
  rewritten to add `ADMITTED_CONTEXT_DIMENSIONS` (the explicit allowlist)
  and a new private `_build_contextual_evidence` helper; `build_evidence`
  gained exactly three new lines --

  ```python
  if context.context_package is not None:
      evidence["contextual_evidence"] = _build_contextual_evidence(context.context_package)
  ```

  Every existing field (`candidate`/`upstream_findings`/`participation`)
  is byte-for-byte unchanged code -- the diff only adds, never edits, the
  three original dict entries.

No other file was modified: `sequential_base.py`, `app/orchestration/
cycle.py`, `app/orchestration/fanout.py`, `probability_output.py`, and
every other consumer of `SequentialDecisionContext`/`build_evidence`
are untouched.

---

## 2. `contextual_evidence` contract

```python
ADMITTED_CONTEXT_DIMENSIONS: tuple[str, ...] = ("venue", "player_performance", "market", "weather")
```

**The one explicit allowlist gate** -- a dimension name absent from this
tuple can never reach `contextual_evidence`, regardless of what
`ContextPackage`/`engine.py`'s own `SUPPORTED_DIMENSIONS` carry today or
grow to carry later. Admission is never inferred from `engine.py`
support alone (per HQ's explicit instruction) -- widening this tuple
requires a new, explicit, separately-authorized admission decision.

Shape, for each admitted dimension present and not `"unavailable"`:

```python
{
    "target_event_timestamp": "...",  # from ContextPackage, verbatim
    "dimensions": {
        "<name>": {
            "completeness": "joined" | "partial",     # verbatim, never re-derived, never coerced
            "sample_size": <int>,
            "facts": {...},                            # the dimension's own real facts, verbatim
            "provenance": [{"table":..., "source":..., "row_count":..., "earliest_at":..., "latest_at":...}, ...],
            "limitations": [<standing confounders>, <insufficient_evidence_reason if set>],
            "point_in_time_caveat": "...",              # every admitted dimension carries one, see Section 5
        },
        ...
    },
    "known_limitations": [...],  # ContextPackage's own deduplicated list, carried at package level
}
```

An admitted dimension resolving `"unavailable"` for a specific candidate
is simply **absent** from `dimensions` -- never a zero-filled or
fabricated-empty entry. A blocked dimension (`news`/`injuries`/
`roster_role`/`team_performance`/`depth_lineup`/`game_state_pbp`) is
**structurally unable to appear** -- the allowlist loop only ever
iterates `ADMITTED_CONTEXT_DIMENSIONS`, never `context_package.
dimension_completeness`'s own keys, so a blocked dimension's presence or
completeness state in the underlying package is irrelevant to whether it
reaches the payload (proven directly, Section 4).

**No prediction/probability/confidence field exists anywhere in this
contract** -- `completeness` describes evidence availability only;
nothing reads it into, or presents it as, a numeric score. Proven
structurally (`test_no_confidence_field_anywhere_in_contextual_evidence`,
recursive dict-key scan, not a naive substring search that would
false-positive on caveat prose that legitimately discusses the word
"confidence" as documentation).

---

## 3. JSN real proof

`test_jsn_sea_ne_context_reaches_build_evidence`
(`tests/context_intelligence/test_engine.py`) runs the full real chain --
`build_contextual_intelligence` -> `assemble_context_package` ->
`ProbabilityModelingAgent().build_evidence()` -- against the exact same
real, live-queried DEV values (2026-09-15) every prior pass in this
series used. Confirms directly:

- `contextual_evidence` exists on the returned evidence dict.
- `venue` present.
- `player_performance` present, with the real, exact stat line:
  `role_usage_signals["receiving"] == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}`.
- `market` present, `completeness == "joined"`, real non-empty facts.
- `weather` present, `completeness == "partial"`.
- `news`, `injuries`, `roster_role`, `team_performance`, `depth_lineup`,
  `game_state_pbp` all **absent** -- `set(ce["dimensions"].keys())` is a
  subset of `ADMITTED_CONTEXT_DIMENSIONS`.
- `player_performance`'s `sample_size == 1` -- no duplicate inflation,
  despite the real observation's own `duplicate_raw_row_count == 2`
  (both real raw rows still disclosed, never hidden, never double-counted).
- No `confidence`/`probability_score` key anywhere in `contextual_evidence`
  (recursive key scan).
- `candidate`/`upstream_findings`/`participation` are **byte-identical**
  between the call with `context_package` set and an otherwise-identical
  call without it -- proving no existing probability-output field changes
  as a side effect of this integration.

---

## 4. Restriction enforcement proof

Fifteen dedicated mechanism tests
(`tests/agents/test_probability_modeling_context_integration.py`), plus
the real proof above:

- **player_performance**: `test_player_performance_sample_size_and_
  duplicate_tracking_preserved` -- `sample_size == 1` (one-game evidence,
  never a trend), `duplicate_raw_row_count`/`canonical_row_id`/
  `reliability_limitations` all preserved verbatim inside `facts`.
  `test_player_performance_unresolved_opponent_does_not_fabricate_context`
  -- a `None` opponent passes through as real `None`, never guessed,
  while the rest of the observation (real stats) is still admitted.
  `test_player_performance_carries_its_own_point_in_time_caveat` --
  the same-day-precision limitation travels into `point_in_time_caveat`.
- **market**: `test_market_and_weather_carry_the_comparable_pool_live_
  only_caveat` -- the standing caveat (Section 5) is present verbatim.
  `test_partial_dimension_is_admitted_as_partial_never_coerced_to_joined`
  covers the shared completeness-integrity rule (market and weather
  alike). Scale-mixing prohibition (moneyline never blended into
  point-movement similarity) is enforced inside `market.py` itself,
  unchanged by this pass, and the real facts admitted here are copied
  verbatim from that already-correct computation.
- **weather**: same live-only caveat test; fixture-exclusion (only
  `weather_data.source == "weatherapi"` rows ever produce a real target
  reading) is enforced inside `weather.py` itself, unchanged, and
  verified indirectly via the real proof's own `PARTIAL` classification
  (a real, non-fixture reading was found).
- **venue**: `test_venue_carries_a_static_facts_caveat_not_silently_
  omitted` -- explicitly states venue's zero point-in-time risk rather
  than silently omitting a caveat field.
- **Shared, all dimensions**: `test_unavailable_admitted_dimension_is_
  absent_not_zero_filled`, `test_provenance_carried_forward_verbatim_
  not_flattened`, `test_no_confidence_field_anywhere_in_contextual_
  evidence`.

---

## 5. Look-ahead protection

**Preserved, not re-implemented, exactly per the Admission Decision.**
Each dimension's own point-in-time rule is unchanged code
(`player_performance.py`'s explicit `target_event_timestamp` comparison;
`venue.py`'s static, risk-free facts). **The market/weather comparable-
pool gap identified in the Admission Decision is carried forward
explicitly, not silently assumed resolved**: every admitted `market`/
`weather` entry in `contextual_evidence` carries a standing
`point_in_time_caveat` stating plainly that the comparable-pool evidence
(`similarity_score`/`confidence`, built from whole-table reads with no
time filter) is authorized only for the one real caller shape this
codebase has today -- a live call, where no future-dated comparable
observation can exist -- and **has NOT been verified safe for
backtesting or historical reconstruction**.

**This codebase has no historical/replay-mode detection mechanism as of
this pass** -- confirmed by search; no flag, parameter, or code path
anywhere distinguishes a "live" `build_evidence()` call from a
hypothetical future "replay" one. Per the directive's own instruction
("do not silently make this historical-backtest-safe if it is not"),
this pass does **not** invent such a detection mechanism (that would be
new scope well beyond "integrate the admitted dimensions") -- instead,
the caveat is written into the evidence payload itself, so any future
replay-mode implementation is put on notice at the exact point it would
need to check, rather than discovering the gap by inference. This is
recorded here as a disclosed, open limitation (Section 8), not a
resolved one.

---

## 6. Regression results

- **Existing callers without `ContextPackage` behave exactly as before**:
  `test_no_context_package_omits_contextual_evidence_entirely` proves
  `"contextual_evidence" not in evidence` and the evidence dict's key set
  is exactly `{"candidate", "upstream_findings", "participation"}` --
  unchanged from before this pass. `test_existing_fields_unchanged_
  regardless_of_context_package` proves the three existing fields are
  identical whether or not a package is attached.
- **Recommendation outputs remain unchanged**: no file in `app/
  orchestration/`, `app/agents/sequential_base.py`, `app/agents/
  probability_output.py`, `app/agents/expected_value_agent.py`, `app/
  agents/risk_manager.py`, or `app/agents/bankroll_coach.py` was
  touched. The one real production construction site
  (`app/orchestration/cycle.py:163`) is unchanged and never sets
  `context_package` -- confirmed via `git status` and direct inspection.
- **No provider calls**: every test in this pass uses respx-mocked
  Supabase boundaries or pure in-memory fixtures; zero real network
  calls anywhere.
- **Blocked dimensions cannot enter through future engine expansion
  accidentally**: `test_future_engine_expansion_cannot_silently_widen_
  admission` proves a `ContextPackage` carrying an entirely new,
  hypothetical dimension name (simulating a future `engine.py` addition)
  still cannot reach `contextual_evidence` -- the allowlist loop only
  ever iterates the four names in `ADMITTED_CONTEXT_DIMENSIONS`, never
  the package's own dimension set.
- **Existing probability tests remain green**: `tests/agents/
  test_sequential_agents.py` (29 tests, including every pre-existing
  `ProbabilityModelingAgent`/`build_evidence` test), `tests/orchestration/
  test_cycle.py`, `tests/orchestration/test_sequential.py`, `tests/
  orchestration/test_prompt_provenance.py` all pass unmodified.

**Full `apps/ai-orchestrator` suite: 926 passed, zero regressions**
(up from 910; +16 new: 15 mechanism tests + 1 real `build_evidence`
proof).

---

## 7. Blocked-dimension exclusion proof

Three independent proofs, all passing:

1. `test_blocked_dimension_never_appears_even_when_joined_in_the_
   package` -- a synthetic `ContextPackage` with `news` marked
   `"joined"` (deliberately, to prove the allowlist -- not completeness
   -- is what excludes it) still never appears in `contextual_evidence`.
2. `test_admitted_dimensions_constant_is_exactly_the_four_from_the_
   admission_decision` -- `ADMITTED_CONTEXT_DIMENSIONS == ("venue",
   "player_performance", "market", "weather")`, and the six blocked
   names are structurally disjoint from it.
3. The real JSN proof (Section 3) -- all six blocked/unsupported
   dimension names confirmed absent from the real, live-data-derived
   `contextual_evidence` payload.

---

## 8. Remaining limitations

- **The market/weather comparable-pool point-in-time gap is disclosed,
  not closed.** No replay-mode detection exists in this codebase; the
  caveat is documentation-level protection (visible in every admitted
  payload), not a structural/code-level block. A future historical-
  backtest harness must itself check for and respect this caveat --
  nothing in `build_evidence()` can currently stop it from being ignored.
- **`news`'s team-identity bug remains unfixed**, exactly as instructed
  -- `news` stays blocked (C) until that separate, independently-
  authorizable fix happens.
- **Injuries/roster_role/team_performance/depth_lineup/game_state_pbp
  remain blocked**, exactly as instructed -- no work was done on any of
  them.
- **No trend/consistency scoring exists for `player_performance`** --
  `sample_size` will remain 1 for every real player until a second real
  historical game exists (still blocked on real time, per every prior
  pass's own conclusion).
- **This integration is consumption-only.** Nothing in this pass wires
  the real orchestrator (`app/orchestration/cycle.py`) to actually
  *construct* a `ContextPackage` for a live candidate -- `context_
  package` stays `None` for every real production call today. Wiring
  that construction (fetching the real engine result and assembling a
  package as part of the actual recommendation cycle) is a distinct,
  separate task from what this pass was authorized to do
  ("integrate... into build_evidence()," not "wire context assembly into
  the orchestrator") -- named explicitly as the next step below.

---

## 9. Smallest next Phase 8 step after successful integration

**Wire `app/orchestration/cycle.py` (or wherever a candidate's
`SequentialDecisionContext` is first constructed) to actually build a
real `ContextPackage` for live candidates** -- the one remaining gap
between "the plumbing exists and is proven correct" (this pass) and "a
real recommendation actually carries contextual evidence" (not yet
true for any live call today). This is squarely a recommendation-
orchestration change, correctly out of this pass's own scope (which was
`build_evidence()` only), and would need its own explicit authorization
-- including a decision on exactly when/how `player_id` (required for
`player_performance`) is determined for a given candidate, since not
every market type is player-scoped.

Separately and independently: fixing `news`'s team-identity resolution
(reusing `resolve_team_identity_for_games`, already built) remains
available as its own small, isolated task whenever HQ authorizes it --
still not bundled into this pass or the one above.

This document's own implementation makes no recommendation-logic change,
no probability-calculation change, no invented weight, no context-
derived confidence, and no provider call -- confirmed by the regression
suite (Section 6) and the structural proofs (Sections 3-4, 7).
