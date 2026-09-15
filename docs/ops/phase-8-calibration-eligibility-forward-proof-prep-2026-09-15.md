# Phase 8 — Calibration Eligibility + First Forward Proof (Prep Only)

**Date:** 2026-09-15
**Directive:** MANSA HQ — "PHASE 8 CALIBRATION ELIGIBILITY + FIRST FORWARD PROOF PREP"
**Type:** Eligibility contract (code + tests) + read-only reconnaissance
**Headline:** HQ's correction was correct and is now enforced in code. **No suitable upcoming candidate exists in dev** — the blocker is missing odds for upcoming games, and closing it requires a provider call this pass forbids.

---

## 1. Why the previous "smallest next step" was wrong

The prior pass proposed running a recommendation cycle on an already-finished game
to manufacture the first calibration row. That would have been **post-event
prediction**: a probability produced after kickoff can encode in-game state, a known
final score, or a settled stat line. Scoring it would flatter the model with
information it never had to forecast, and it would have silently poisoned the ledger
at its very first row — the worst possible place, because everything downstream
inherits that first row's legitimacy.

The correction is now a contract enforced in code, not a convention.

---

## 2. The calibration-eligibility rule (exact)

`SettledPrediction.calibration_exclusion_reason` returns `None` only when **all** of
the following hold. Order matters: the timing gate is evaluated *before* the outcome
gate, so a post-event prediction is disqualified as a forecast regardless of how
cleanly it later settled.

| # | Requirement | Exclusion reason if violated |
|---|---|---|
| 1 | `predicted_at` exists | `missing_predicted_at` |
| 2 | event `scheduled_start` exists | `missing_event_scheduled_start` |
| 3 | both timestamps parse | `unparseable_timestamp` |
| 4 | **`predicted_at` < `scheduled_start`** (strict) | `predicted_at_not_before_scheduled_start` |
| 5 | outcome is `WIN` or `LOSS` | `outcome_not_binary` |

Requirements the *read* layer enforces upstream, by construction — a row failing any
of these never becomes a `SettledPrediction` at all: a frozen `modeled_probability`
must exist in `raw_output` (never reconstructed), the frozen candidate / market /
selection / price must exist on `recommendation_legs`, and an authoritative terminal
grade must exist in `recommendation_leg_grade_events`.

**Strictness is deliberate at the boundary.** `predicted_at == scheduled_start` is
excluded: equality is not "before".

Every metric (`brier_score`, `log_loss`, `bucket_breakdown`, and the report) filters
on `is_scoreable`, which is defined as `calibration_exclusion_reason is None`. An
ineligible prediction therefore cannot reach a metric by any path — tested directly
rather than assumed.

---

## 3. Excluded-post-event behavior

**Retained, returned, and reported — never deleted, never filtered away at read
time.** `read_settled_predictions` deliberately still returns a post-event prediction,
carrying the `scheduled_start` that disqualifies it. Dropping it during the read would
hide a process problem (something produced a post-event prediction) behind an
innocuous-looking smaller sample.

`CalibrationReport` surfaces it two ways:

- `excluded_by_reason` — every held-out prediction grouped by reason
- `excluded_post_event` — a dedicated count, called out separately because it is the
  one exclusion indicating a *process* problem rather than an ordinary un-scoreable
  settlement like a push

plus a plain-language note: *"N prediction(s) were made at or after the event's
scheduled start and are excluded from every metric — these are post-event
predictions, not forecasts, and may encode hindsight. They are retained and reported,
never deleted."*

**No new DB table was required.** `scheduled_start` already exists on `games`; the
read layer batch-joins it. Nothing was migrated.

---

## 4. Hindsight backfill — prohibited in the contract

Written into `app.features.calibration`'s module docstring as a standing prohibition,
not guidance: generating predictions after a game ends and treating them as historical
calibration observations is post-event prediction, not forecasting;
`modeled_probability` is never reconstructed later (it is read frozen or the row does
not become a prediction); and no historical/replay path has been proven point-in-time
safe in this codebase, so none may feed this ledger. Synthetic and post-hoc fixtures
may prove plumbing in tests — **they must never increase the real calibration sample
count**, and every test fixture here is hand-built rather than persisted.

---

## 5. Real dev calibration count after the stricter rule

**Still zero — and zero for a more fundamental reason than eligibility.**

| | |
|---|---|
| settled predictions | **0** |
| eligible (scoreable) predictions | **0** |
| excluded post-event | **0** |
| `recommendation_legs` | 0 |
| grade events | 0 |

The stricter rule excluded nothing, because there was nothing to exclude. Every metric
returns `None` and the report says *"an empty ledger, not a calibration finding."*

---

## 6. First real forward proof — reconnaissance (no provider calls, nothing run)

**No suitable upcoming candidate exists.** Measured, not assumed:

| Upcoming game | Kickoff (UTC) | Status | Odds rows |
|---|---|---|---|
| CHI @ GB | 2026-10-11 20:25 | scheduled | **0** |
| SF @ SEA | 2026-10-11 20:25 | scheduled | **0** |
| DET @ ARI | 2026-10-11 20:25 | scheduled | **0** |

Supporting facts:

- Upcoming games in dev: **3**. Upcoming games with any persisted odds: **0**.
- All 1,258 persisted `odds_snapshots` rows belong to **6 games**, the latest of which
  kicked off **2026-09-13 20:25 UTC** — already in the past.
- Newest odds capture anywhere: **2026-09-13 20:15 UTC** (~2 days stale).
- `daily_game_intelligence`: 17 rows. Final games: 1.

**Normal cycle requirements are therefore NOT satisfied** for any upcoming game.
`generate_candidates_for_game` selects a reference sportsbook by walking the
preference list for the first book with *fresh* V1-market data; with zero odds rows
for all three upcoming games it returns
`game_skipped_reason="no_configured_sportsbook_has_fresh_data"` and produces no
candidates at all. Even if rows existed, freshness is bounded by
`max_snapshot_age_seconds` (the kickoff-proximity polling tier plus a 300s
orchestration grace) — at 26 days out that is the FAR tier, ~24h + 5m, which the
current 2-day-old data would also fail.

The three upcoming games are Week 5 on 2026-10-11 — **26 days away**.

---

## 7. LLM call budget for one normal forward cycle (counted from the code)

Per **game**, once: fan-out over `BUILT_AGENTS` — injury_intelligence, weather,
travel_fatigue, rest_days, vegas_line, closing_line_movement = **6 calls**.

Per **candidate**: Probability Modeling + Expected Value + Risk Manager (the shared
chain) = 3, plus Meta Agent in `run_shared_consensus` = 1 → **4 calls**.

`_V1_MARKET_TYPES` is moneyline/spread/total and both sides of each are generated, so
a fully-priced game yields **up to 6 candidates**.

| Scenario | Calls |
|---|---|
| Fan-out (per game) | 6 |
| 6 candidates × 4 | 24 |
| **Baseline total** | **30** |
| \+ Elite second pass (only if an Elite-tier subscriber exists *and* the threshold fires) | +1 per candidate, up to +6 |
| \+ Bankroll Coach (only per user actually needing a stake) | +1 per user per candidate |

**Only 1 of every 4 per-candidate calls — the Probability Modeling call — produces a
calibration prediction.** So a single fully-priced game yields at most 6 calibration
rows for ~30 LLM calls.

---

## 8. Would the resulting prediction satisfy the eligibility contract?

**Yes, if run before kickoff** — and only then:

- `predicted_at` = the probability row's `created_at`, written at cycle time ✓
- `scheduled_start` exists on all three upcoming games ✓
- `predicted_at < scheduled_start` ✓ provided the cycle runs before 2026-10-11 20:25 UTC
- frozen `modeled_probability`, candidate/market/selection/price ✓ (already proven)
- terminal grade ✓ **only after** the game finishes and the postgame grading worker runs
- `WIN`/`LOSS` for binary scoring ✓ for moneyline/spread/total (a push excludes that leg only)

So the prediction becomes *eligible* at cycle time but only *settled* after kickoff
plus grading — which is exactly the shape a legitimate calibration observation must
have.

---

## 9. Plan for the first legitimate calibration observation

1. **Ingest odds for an upcoming game** — the actual blocker. Requires an Odds Worker
   provider call, forbidden this pass; needs separate authorization.
2. **Run one normal recommendation cycle before kickoff**, well inside the freshness
   ceiling (odds captured within the kickoff-proximity tier + 5m grace). Budget ~30
   LLM calls for a fully-priced game; a narrower single-market run costs less.
3. **Wait for the game to actually finish.** No shortcut exists here and none should be
   invented — this waiting period *is* the property that makes the observation valid.
4. **Let the existing postgame grading worker grade it** — unchanged, authoritative.
5. **Read the ledger back** and confirm a real `SettledPrediction` materializes with
   `calibration_exclusion_reason is None`, a frozen `modeled_probability`, and a real
   outcome.

That single row proves the whole chain on genuinely forward-looking data. Calibration
*conclusions* remain far away (n=1 against a 100 product floor, and per-bucket
inference needs far more), and no probability or context adjustment is justified until
then.

---

## 10. Metrics (unchanged, per directive)

Settled count, scoreable count, probability buckets, observed win rate, Brier score,
log loss — all retained, all returning `None` on the empty real sample.

**The 100-observation threshold is now explicitly documented as a product rule, not a
statistical one.** Its comment reads: *"A PRODUCT RULE meaning 'MANSA draws no
conclusions yet' — explicitly NOT a statistically proven sufficiency threshold, and it
must never be described as one. 100 eligible observations does not make a calibration
estimate reliable… Genuine per-bucket inference needs far more than 100, spread across
buckets."*

---

## 11. Tests

**987 passed, zero regressions** (up from 974). 13 new eligibility tests:

- eligible when predicted before kickoff; excluded when after; excluded at exact equality
- timing gate evaluated before the outcome gate
- missing `scheduled_start` / missing `predicted_at` / unparseable timestamp each excluded with their own reason
- a confidently-correct post-event prediction cannot reach Brier, log loss, or any bucket
- report counts post-event exclusions separately and retains the rows
- post-event is distinguished from an ordinary push exclusion
- read layer: `scheduled_start` plumbed through; post-event prediction returned rather than filtered; missing kickoff yields `None` rather than a silent pass

## 12. Operational

- `ai-orchestrator` dev deployment `86a2403f` → **SUCCESS** (verified read-only, no deployment triggered).
- `phase8-context-experiment` remains operational debt only; it blocked nothing in this pass.
