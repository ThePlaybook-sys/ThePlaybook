# Phase 8.5 Pass 3 — `market_type` Audit and Market-Specific Filtering (2026-09-09)

**Status: implemented, HQ-authorized.** Extends `POST /v1/recommendations/ask` (Pass 1/2) with a deterministic, filter-before-ranking market constraint. Traced against current source and the live schema — not assumed from prior reports.

## Step 1 — Canonical `market_type` audit

1. **Exact values currently stored.** `recommendation_legs.market_type` — real, DB-enforced: `market_type text not null check (market_type in ('moneyline','spread','total','prop'))` (`supabase/migrations/20260825120000_recommendation_products_schema.sql:137`). In practice, only `'moneyline'`, `'spread'`, `'total'` are ever written — `'prop'` is a schema-allowed value that no candidate-generation path produces (props excluded from `_V1_MARKET_TYPES` since Milestone 4.7, confirmed by grep of `apps/ai-orchestrator/app/features/candidate_generation.py:77`).
2. **Where it originates.** The Odds API's own vendor market keys (`h2h`, `spreads`, `totals`) are normalized into MANSA's canonical vocabulary at the earliest possible point — ingestion — via `_BULK_MARKET_TYPE = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}` (`apps/sports-intel-layer/app/adapters/providers/the_odds_api.py:58-60`), with an explicit `.get(key, "prop")` fallback for anything unrecognized. Persisted to `odds_snapshots.market_type`, carried unchanged through `MarketCandidate` → `EvaluatedCandidate` → `recommendation_legs.market_type`.
3. **Normalized before reaching recommendation legs?** Yes — at ingestion, not read time, not guessed downstream. By the time a value reaches `recommendation_legs`, it has passed through both this normalization step and the DB-level CHECK constraint.
4. **Do spread and total have stable canonical values?** Yes — `"spread"`/`"total"`, single fixed strings, enforced by the same CHECK constraint.
5. **Does moneyline have a stable canonical value?** Yes — `"moneyline"`, identical enforcement, identical normalization mechanism. **No asymmetry was found between moneyline and spread/total anywhere in the pipeline.**
6. **Can common aliases map safely?** Yes, all unambiguous:
   - `moneyline`, `money line` → `moneyline`
   - `spread`, `point spread` → `spread`
   - `total`, `totals`, `over/under`, `over under` → `total` (the industry-standard synonym, matching The Odds API's own `"totals"` vendor key semantics exactly)
   No alias collides with any other MANSA concept (verified by grepping the existing Pass 1/2 phrase lists).
7. **Can an active recommendation have `market_type` NULL or unrecognized?** **No — schema-impossible.** `not null` + the CHECK constraint make this unenforceable at the database level, not merely an application convention.

**Verdict: audit passes cleanly. No ambiguity or contradiction found.** All three markets — moneyline, spread, total — have equally clean, unambiguous, DB-enforced canonical representations. Per Step 6's own conditional gate, this means **moneyline is included in this pass, not deferred** — nothing in the audit distinguishes it from spread/total.

## Step 2 — Request contract extension

Pipeline preserved exactly: `RawUserInput → normalize_request → NormalizedRequest → resolve_intent → ResolvedIntent → build_execution_plan → ExecutionPlan`. Added:

- `MarketType(str, Enum)`: `MONEYLINE`, `SPREAD`, `TOTAL` — the exact three real, ever-written values.
- `ResolvedIntent.market_type: MarketType | None` and `ExecutionPlan.market_type: MarketType | None` — `None` whenever no market constraint was recognized, preserving Pass 1/2 behavior exactly for every request that doesn't name one.

A market constraint is recognized **only alongside a recognized selection-mode phrase** (never as a standalone "market-only" request type) — deliberately not expanding this pass's own scope beyond what HQ authorized.

## Step 3 — Filter before ranking (mandatory rule, implemented as specified)

`_select_highest_confidence_card`/`_select_highest_value_card` (`app/recommendations.py`) both take an optional `market_type` parameter. The check happens **inside the same loop that finds the max**, before any comparison against the running best — a leg from a different market is never even considered a candidate, let alone allowed to win by being globally stronger. Verified by dedicated tests (`test_ask_highest_confidence_spread_filters_before_ranking` et al.) using fixture data deliberately engineered so the globally-strongest leg (moneyline, confidence 0.99) sits in a *different* market than the one requested — the weaker, in-market leg wins every time.

## Step 4 — No fallback (mandatory rule, implemented as specified)

When a market constraint is present and no active leg qualifies for it, the response is the existing honest `insufficientEvidence: true, result: null` shape — **never** a recommendation from a different market, regardless of how strong. Verified by `test_ask_market_specific_request_with_no_qualifying_recommendation_is_honest`, using a slate with only moneyline/spread products and a total-scoped request.

## Step 5 — Terminology

Unchanged distinction: "highest confidence" → `final_aggregate_confidence`; "highest value"/"best value" → `ev_per_dollar`. Response `label`/`no_result_reason` now name the market when one applies (e.g. *"MANSA's highest-confidence spread pick today"*) via a `{market}`-templated string, never altering the underlying metric semantics. No new terminology (safest/guaranteed/certain/most likely to win/best pick/conservative/aggressive) introduced.

## Step 6 — Moneyline gate

**Included.** The Step 1 audit found no asymmetry between moneyline and spread/total — same CHECK-constrained canonical value, same ingestion-time normalization, same real usage in `_V1_MARKET_TYPES`. Deferring it would have had no evidentiary basis.

## Step 7 — Tests

21 new tests (9 pure resolver unit tests in `test_request_intent.py`, 12 endpoint integration tests in `test_recommendations_ask.py`), covering all 14 items HQ specified (A–N) plus the moneyline gate. Full api-gateway suite: **147/147 passing** (126 pre-existing + 21 new), **zero regressions**.

## No provider/worker/recomputation calls

Unchanged from Pass 1/2: the route never imports or calls `call_ai_orchestrator`, never touches Master Refresh, Probability Modeling, or Consensus. Proven by test — zero such mocks registered anywhere in the market-filter test suite; respx fails a test on any unmocked request.

## What was and wasn't done

Implemented exactly the objective HQ authorized: market-specific filtering for moneyline/spread/total, filter-before-rank, no fallback, honest no-result. **Not implemented, deliberately**: Top N, parlays, player-specific requests, conservative/aggressive modes, a "best pick" definition, LLM parsing, on-demand computation, multi-sport expansion beyond this audit, any schema migration (none was needed — every value used already existed and was already enforced), staging/production changes.
