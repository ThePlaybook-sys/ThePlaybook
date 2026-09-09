# Phase 8.5 Pass 2 — `ev_per_dollar` Metric Verification (2026-09-09)

**Required by HQ before exposing "highest value" to any user.** Traced against current source, not prior reports.

## 1. Where it's calculated

`apps/ai-orchestrator/app/features/expected_value.py::compute_ev` — pure, deterministic, no LLM, no I/O. Called during the sequential Decision & Advisory chain (`app/orchestration/sequential.py`), immediately after Probability Modeling produces `modeled_probability` for a candidate. Persisted onto `recommendation_legs.ev_per_dollar` at product-creation time.

## 2. Inputs

`p_model` — Probability Modeling's own `modeled_probability` for that exact candidate (an LLM judgment, not a deterministic prior). `american_odds` — the real, actually-offered price from the `odds_snapshots` row the candidate was generated from (`app/features/candidate_generation.py`) — never a synthetic or de-vigged price.

## 3. What it mathematically represents

```python
decimal_odds = american_to_decimal(american_odds)
ev_per_dollar = p_model * decimal_odds - 1
```

This is the standard expected-value-per-dollar-staked formula: expected net profit on a $1 wager at the given price, under MANSA's own modeled probability. It is genuine expected value — not a return-efficiency ratio, not a risk-adjusted (Sharpe-style) metric, not a Kelly fraction, not a probability itself. The module's own docstring is explicit that this is priced against the *actual offered price* ("correct because it's pricing the actual wager, not a hypothetical fair one") — distinct from the separately-computed, explicitly-labeled-vig-inclusive `raw_probability_edge` field, which this pass does not use or expose.

## 4. Is higher always better?

**Yes, both mathematically and architecturally.** Mathematically: a higher `ev_per_dollar` means a higher expected net profit per dollar staked — an unambiguous, monotonic "better" for this specific metric. Architecturally: `apps/ai-orchestrator/app/features/strategy.py::rank_key` (Decision AM, the Strategy Engine's own real ranking rule for same-market conflict resolution and leg presentation order) already sorts by `-ev_per_dollar` as its **primary, sole** signal — `final_aggregate_confidence` is only a secondary tie-break. This pass's "highest value" selection uses the identical ranking direction the project's own core decision engine already relies on for real recommendation output — not a new interpretation invented for this endpoint.

## 5. Null and negative values

**Null**: `compute_ev` returns `ev_per_dollar=None` only when `american_odds is None` (a missing price) — but `strategy.py::EvaluatedCandidate.ev_per_dollar` is typed as `float`, not `float | None`: a candidate with a null EV never becomes an `EvaluatedCandidate` and therefore never becomes a persisted leg. In practice, every real, persisted `recommendation_legs.ev_per_dollar` is a real float. Pass 2's selection code still defensively skips `None`, per HQ's explicit "never treat NULL as zero" instruction, rather than trusting this invariant blindly.

**Negative**: mathematically possible in `compute_ev`'s raw output (nothing in the formula prevents `p_model * decimal_odds < 1`) — but `strategy.py::qualifies()` requires `ev_per_dollar > 0` **strictly**, as one of exactly two gates (with `final_aggregate_confidence >= 0.55`) before a candidate can ever become an active, persisted `recommendation_products`/`recommendation_legs` row. A real, active leg with `ev_per_dollar <= 0` would contradict this architectural invariant and should never occur — Pass 2's selection code still defensively excludes `<= 0` values rather than assuming the invariant holds forever, matching this project's own "trust nothing that isn't independently verified" discipline (e.g. `unsupported.py`'s own "never assume, always confirm" precedent).

## 6. Can recommendations be fairly ranked against each other by this metric?

**Yes.** Every leg's `ev_per_dollar` is computed against the same "$1 staked" denominator and the real offered price for that exact selection — a unit-consistent, cross-market, cross-game comparable number. This is precisely why Strategy Engine itself already uses it as the sole primary cross-candidate ranking signal (§4 above), not a property this pass had to newly establish.

## 7. Does it represent EV, return efficiency, or something else?

**Genuine expected value**, confirmed by direct reading of the formula and its own module docstring. Not a return-efficiency ratio (which would normalize by stake or bankroll fraction — this doesn't); not risk-adjusted (no variance term enters this formula, `risk.py`'s own `bernoulli_outcome_variance` is a separate, distinct computation); not a probability (bounded differently, and computed *from* `p_model`, not a substitute for it).

## Verdict

**The metric audit supports an honest "highest value" product label.** `ev_per_dollar` is a real, correctly-computed expected value, already the project's own primary real ranking signal, comparable across candidates, and — for any legitimately active, persisted recommendation — architecturally guaranteed positive. Implementation proceeds per this verification. Response-layer terminology (see `app/recommendations.py`'s `ask_recommendation` docstring) states plainly that this reflects MANSA's own modeled expected value, never a guarantee.
