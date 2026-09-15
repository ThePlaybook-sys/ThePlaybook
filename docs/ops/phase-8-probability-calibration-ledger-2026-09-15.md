# Phase 8 — Probability Calibration Ledger

**Date:** 2026-09-15
**Directive:** MANSA HQ — "PHASE 8 PROBABILITY CALIBRATION LEDGER"
**Type:** Infrastructure (measurement only) — no probability tuning, no context weights, no EV/Kelly/Risk change, no provider calls
**Headline:** No new prediction table was needed. The ledger is a **join**, not a store. Real settled predictions today: **0**.

---

## 1. Existing grading architecture found

The directive's correction was right — grading/finalization infrastructure already
exists and is mature. Inspected before writing anything:

| Layer | What it already freezes |
|---|---|
| `recommendation_legs` | The bet: `candidate_key`, `game_id`, `market_type`, `selection`, `sportsbook`, `american_odds`, `point`, `decimal_odds`, `ev_per_dollar`, `final_aggregate_confidence`, `consensus_snapshot_id`, `created_at` |
| `recommendation_agent_outputs` | The prediction: `raw_output` jsonb (`modeled_probability`, `confidence_in_probability`), `prompt_name`/`prompt_version`, `model_name`/`provider`/`used_fallback`, `candidate_key`, `created_at` |
| `recommendation_leg_grade_events` | The outcome: `outcome`, `authoritative_result`, `graded_at`, `grading_version`, `is_correction`, `corrects_grade_event_id`, `correction_source` |
| `recommendation_product_grade_events` | Per-product rollup (`MIXED_SETTLED`, `NOT_APPLICABLE`, leg counts) |
| `app.features.grading` | `GRADING_VERSION = "v1"`, `LEG_OUTCOMES`, `grade_leg`, `rollup_product_outcome` |
| `app.persistence.postgame_grading` | `read_latest_leg_grade_event`, `persist_leg_grade` (create-or-correct) |

**Live-verified before designing:** every table in that chain already carries a
DB-level append-only trigger — `trg_block_rao_update`,
`trg_block_recommendation_leg_update`, `trg_block_recommendation_product_mutation`,
`trg_block_leg_grade_event_update`, `trg_block_consensus_snapshot_update`. Corrections
are new rows pointing at what they supersede, never UPDATEs.

---

## 2. Extended, not replaced — and why

**No new calibration table was created.** Every field the directive listed already
exists, frozen at decision time, in tables the database itself forbids mutating. A
new table would have added a second, mutable-by-default copy of already-immutable
data — strictly worse for the one property that matters most here ("do not let later
prompt/model/context changes mutate historical prediction records").

What was actually missing was never storage. It was **the join**, plus one field.

**The one real gap: contextual dimensions at decision time.** `raw_output` holds the
agent's *output*; `contextual_evidence` is its *input*, and was never persisted. Closed
with **zero schema change** by writing a `context_provenance` sibling key into the
existing `raw_output` jsonb on the probability row — mirroring the `"deterministic"`
sibling key `cycle.py` already writes for the EV/Risk steps. It inherits
`trg_block_rao_update` immutability for free and needed no migration.

---

## 3. The immutable prediction snapshot contract

`app.features.calibration.SettledPrediction` — every field copied from an
already-frozen row, nothing recomputed:

| Field | Source |
|---|---|
| `candidate_key`, `recommendation_id`, `recommendation_leg_id`, `game_id` | `recommendation_legs` |
| `market_type`, `selection`, `sportsbook`, `american_odds`, `point` | `recommendation_legs` (frozen at creation) |
| `sportsbook_implied_probability` | derived deterministically from the frozen `american_odds` via the existing `app.features.probability.implied_probability` |
| **`modeled_probability`** | `raw_output->'probability_output'->>'modeled_probability'` — **frozen when the decision was made, never reconstructed** |
| `confidence_in_probability` | same row |
| `model_name`, `provider` | `recommendation_agent_outputs` (Milestone 5.3, Decision AV) |
| `prompt_name`, `prompt_version` | `recommendation_agent_outputs` (Milestone 4.8) |
| `predicted_at` | `recommendation_agent_outputs.created_at` |
| `context_provenance` | admitted dimensions + completeness/sample_size, captured at decision time; `None` for predictions made before capture existed — honestly absent, never backfilled |
| `outcome`, `graded_at`, `grading_version`, `grade_event_id` | `recommendation_leg_grade_events` |
| `grade_is_correction`, `corrects_grade_event_id` | same row |

---

## 4. Linkage: prediction → final grade

```
recommendation_legs
   ├── (recommendation_id, candidate_key) ──▶ recommendation_agent_outputs
   │                                          filtered to agent = probability_modeling_agent
   │                                          (the only agent whose raw_output has a modeled_probability)
   └── id ─────────────────────────────────▶ recommendation_leg_grade_events
                                              latest row per (leg, grading_version), created_at desc
```

The "latest row" rule mirrors `read_latest_leg_grade_event`'s existing definition of
"current" exactly — not a second opinion about what a grade means. **Existing grading
semantics are untouched**: this module reads grades, never computes or overrides one.

**Unsupported grading cases stay unsupported.** Nothing is filtered by market type;
a leg whose market cannot be graded simply has no terminal grade event and therefore
never becomes a settled prediction. No player-prop grading support is invented.

---

## 5. Correction handling

A correction supersedes by being a *newer row*, so taking the latest row makes the
correction authoritative automatically. Crucially, the correction chain travels
forward into the ledger rather than being flattened: `grade_is_correction` and
`corrects_grade_event_id` are carried on every `SettledPrediction`, so a calibration
run over corrected history stays auditable — you can always see that a given
prediction is being scored against a revised grade, and which grade it revised.

Tested: a `LOSS` correction of an original `WIN` yields `outcome="LOSS"`,
`grade_is_correction=True`, `corrects_grade_event_id="ge-1"`.

---

## 6. Real historical rows available after implementation

**Zero.** Measured against live dev with the actual join, not inferred:

| | |
|---|---|
| `recommendation_legs` | **0** |
| legs with a frozen prediction | **0** |
| settled predictions (WIN/LOSS/PUSH/VOID) | **0** |
| scoreable predictions (WIN/LOSS) | **0** |
| `recommendation_leg_grade_events` | **0** (0 corrections) |
| `recommendation_products` | 0 |
| `recommendations` | 4 (legacy/fixture rows, none candidate-scoped) |

The ledger is built, tested and correct — and currently empty. That is a data
reality, not an implementation gap: no recommendation cycle has yet produced legs
that were later graded in dev.

---

## 7. Calibration metrics currently computable

All implemented and unit-tested in `app.features.calibration`:

- **count of settled predictions** — plus scoreable count and the excluded-by-outcome breakdown
- **predicted probability buckets** — 0.05-wide across [0, 1] (Volume 4 §5's own "0.55–0.60, 0.60–0.65" language is a subset); empty buckets omitted rather than reported as 0%
- **observed win rate by bucket** — with `mean_predicted_probability` and `calibration_gap` alongside it, since calibration is the *comparison*
- **Brier score** — mean squared error, `None` when nothing is scoreable
- **log loss** — mean negative log likelihood, with a disclosed `1e-15` clamp for ln(0) (numerical hygiene only; Brier uses the unclamped value)

**On the real sample (n=0): every metric returns `None`, and the report says so in
words** — "No settled predictions exist yet… this is an empty ledger, not a
calibration finding." `CalibrationReport.conclusions_justified` is `False` below
`MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS = 100` (disclosed-conservative, explicitly not
empirically derived), and at small n the metrics are still computed with a note that
they are "arithmetically correct and evidentially meaningless."

**PUSH / VOID_NO_ACTION are never coerced into a win or loss.** A push scored as a
loss would silently defame a correct model. They are excluded from the denominator
and reported separately. `PENDING_MISSING_DATA` never enters the ledger at all.

---

## 8. Tests / regressions

**974 passed, zero regressions** (up from 939). 35 new:

- 23 — calibration math: scoreability, push/void exclusion, hand-computed Brier and log loss, the 0.25 coin-flip baseline, clamp behavior and that Brier ignores the clamp, bucket boundaries, empty-bucket omission, empty-ledger honesty, small-sample refusal, and the floor crossing.
- 10 — the join: full prediction↔grade linkage, empty ledger, pending grade excluded, leg without prediction skipped, ungraded (unsupported-market) leg skipped, correction authority + chain visibility, provenance carried forward, provenance honestly `None`, missing agent row fails loud, read failure raises rather than returning a partial ledger.
- 2 — provenance capture through the real JSN/SEA@NE `cycle.py` path (real dimensions with real completeness/sample_size; blocked dimensions absent; `None` when no package attached; probability output untouched).

---

## 9. Remaining data limitations

1. **No settled predictions exist** — the binding constraint. Nothing can be calibrated until real cycles produce graded legs.
2. **`context_provenance` is forward-only.** Predictions made before today carry `None`. It is never backfilled.
3. **Player props remain ungradeable**, so player-performance-influenced predictions cannot enter the ledger even once props exist upstream. Unchanged by design.
4. **The 100-prediction floor is a disclosed judgment**, not a statistically derived threshold; per-bucket inference will need far more than 100 spread across buckets.
5. **Correlated outcomes are not modeled.** Multiple legs on the same game are not independent; Brier and log loss treat them as if they were. Real inference will need to account for this.
6. `read_settled_predictions` issues per-leg reads (a `limit` caps the scan). Fine at current volume; will need batching before it is run over a full season.

---

## 10. Smallest next step toward actual probability calibration

**Run one real recommendation cycle end-to-end in dev and let it grade.** The ledger,
the metrics and the provenance capture are all in place; what is missing is a single
settled row. Concretely: produce `recommendation_legs` from a real cycle on a game
that has already finished, let the existing postgame grading worker write the leg
grade event, then read the ledger back and confirm a real `SettledPrediction`
materializes with a frozen `modeled_probability` and a real outcome.

That single row proves the whole chain on real data. Calibration *conclusions* remain
far away (n=1 of a needed 100+), and no probability or context adjustment is justified
until then — but the measurement pipeline stops being theoretical the moment it exists.
