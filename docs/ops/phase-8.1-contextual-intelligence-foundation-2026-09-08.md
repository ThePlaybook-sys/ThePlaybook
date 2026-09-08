# Phase 8.1 — Contextual Intelligence, Foundation Pass (2026-09-08)

**Status: built, tested, zero schema changes, not wired into Phase 4.** DEV only. Zero SportsDataIO calls. No staging/prod. No Phase 7.2/7.3. No Phase 4 modification. No Milestone 5.6. No invented data anywhere — every unsupported dimension is an explicit, named insufficient-evidence result, never a silent omission or a fixture-backed guess.

---

## 1. New modules/tables/functions

**Zero new tables, zero migrations.** Every dimension reads tables Phase 8.0.5 already confirmed REAL + ACTIVE (`odds_snapshots`, `weather_snapshots`, `news_article_history`, `venues`/`games`) — nothing new to persist, matching HQ's explicit "stateless/re-derived, not one persisted row per player" instruction taken to its natural conclusion: this pass persists nothing at all.

**New package, `apps/ai-orchestrator/app/context_intelligence/`:**
- `models.py` — `ContextualDimensionResult`, `ContextualIntelligenceResult` (shared output shape, every dimension, supported or not).
- `scoring.py` — shared deterministic math: `recency_weight`, `numeric_similarity`, `weighted_mean`, `dispersion`, `confidence_score`. All constants disclosed-conservative policy defaults (`RECENCY_HALF_LIFE_DAYS=14`, `MIN_SAMPLE_FOR_FULL_CONFIDENCE=8`, `INSUFFICIENT_SAMPLE_FLOOR=2`), matching `app.features.market_integrity.THRESHOLD_VERSION`'s own disclosure discipline — real numbers this system needs today, openly marked as policy choices, never presented as calibrated from real data (today's real sample sizes are single digits everywhere).
- `weather.py` — `compute_weather_context` (pure function).
- `market.py` — `compute_market_context` (pure function).
- `news.py` — `compute_news_context` (pure function).
- `venue.py` — `compute_venue_context` (pure function).
- `unsupported.py` — `UNSUPPORTED_DIMENSIONS`, `insufficient_evidence_result` — the six fixed stubs.
- `engine.py` — `build_contextual_intelligence` (the one public async entry point, real I/O, zero writes).

**New persistence, `apps/ai-orchestrator/app/persistence/context_intelligence_reads.py`** (read-only, additive, does not modify or import from any Phase 4/Milestone 7.1 persistence module): `read_all_weather_snapshots`, `read_all_odds_snapshots`, `read_game_venue_context`, `read_venue`, `read_games_sharing_venue`.

**Reused, not duplicated, from already-built code:** `app.features.market.compute_line_movement`/`LineMovementFeatures` (Milestone 4.5), `app.features.market_integrity.classify_market_movement`/`movement_windows`/`check_explanatory_evidence`/`EXPLANATORY_EVIDENCE_LOOKBACK` (Milestone 7.1, pure functions only — the write path and orchestrator, `write_market_monitoring_event`/`assess_game_market_integrity`, are deliberately never called, since wiring that capability into a real caller is explicitly reserved for Milestone 7.2), `app.persistence.market_integrity.resolve_team_ids_by_name`/`read_news_article_history_for_teams` (Milestone 7.1), `app.persistence.odds_snapshots.read_odds_snapshots` (Milestone 4.5).

## 2. Supported dimensions implemented

**A. Weather** — comparable pool: other real `weather_snapshots` rows sharing the exact same `is_dome` bucket (`True`/`False`/`None` — SoFi's unresolved roof stays its own bucket, never coerced). Per-field numeric similarity (temperature/wind/precipitation) against disclosed scale constants, recency-weighted, confidence from sample size × recency × consistency. Fixture rows excluded via the real `weather_data.source == "weatherapi"` marker Phase 8.0.5 Weather Activation introduced.

**B. Market** — this game's own `LineMovementFeatures`/classification (reused verbatim), cross-game comparable pool restricted to point-based (spread/total) movement magnitude (moneyline price movement is reported in `facts` but excluded from the pooled similarity — disclosed as a standing confounder, not silently done). Explanatory-evidence presence for any real qualifying (WATCH/ELEVATED/SEVERE) movement, reusing Milestone 7.1's pure `check_explanatory_evidence` against real weather + news evidence.

**C. News** — real `news_article_history` rows for the game's two teams (via the existing team-name resolver). "Similarity" is explicitly redefined for this dimension (documented, not hidden) as the fraction of real articles that temporally cluster with a real market-movement window, reusing Milestone 7.1's own `EXPLANATORY_EVIDENCE_LOOKBACK`. Every result carries a standing, unconditional confounder: temporal proximity is never evidence of causation. Category/type is explicitly declared unsupported (no ingestion column exists, and this engine will not run an LLM or a hand-rolled keyword heuristic to invent one).

**D. Venue** — real `venues`/`games.venue_id`/`.venue_type`, the sport-agnostic architecture Phase 8.0.5 Pass 2 built, reused with zero redesign. "Similarity" here is literal venue identity (1.0 when any comparable shares the exact `venue_id`, disclosed as not a computed distance), sample size is the count of other real tracked games at that same venue.

## 3. Insufficient-evidence behavior

Every one of the six named-unsupported dimensions (`player_performance`, `injuries`, `roster_role`, `team_performance`, `depth_lineup`, `game_state_pbp`) runs through `engine.build_contextual_intelligence` on **every** call, exactly like the four real ones — the difference is entirely in the result, never in whether it appears. Each returns the identical `ContextualDimensionResult` shape with `insufficient_evidence=True`, a real named reason traced directly to Phase 8.0.5's own closeout matrix (e.g., injuries names the specific real blocker — the account's open/unpaid invoice — not a generic "no data" placeholder), `sample_size=0`, and every score field `None` (never a fabricated `0.0` standing in for "we don't know"). No query is ever attempted against `players`/`player_stats`/`team_stats`/`roster_memberships`/`depth_chart_snapshots`/`injury_reports`/`game_events` — there is nothing real to read, and attempting a read against a fixture-only table would risk surfacing fixture data as though it were real.

The four REAL dimensions also produce `insufficient_evidence=True` results whenever real sample size is genuinely too small (`< INSUFFICIENT_SAMPLE_FLOOR = 2`) — today's real data volume means this fires often even for supported dimensions (e.g., a game whose only comparable is one other real game). This is intentional and correct, not a bug: honest scarcity, not false confidence.

## 4. Sample/similarity/recency/confidence design

- **Sample size**: the literal count of real comparable data points used, excluding the target's own row(s). Never inflated, never estimated.
- **Recency weighting**: exponential decay, `0.5 ** (age_days / 14)` per comparable, averaged across the pool. A comparable observed today weights 1.0; one 14 days old weights 0.5.
- **Similarity**: dimension-specific by design, each explicitly documented — numeric normalized-distance averaging for weather/market, literal-identity for venue, temporal-clustering ratio for news. No single universal formula was forced across dimensions that don't share a common notion of "similar."
- **Confidence**: `sample_factor × avg_recency_weight × consistency`, three independent `[0,1]` factors multiplied so any one weak factor honestly caps the result — never additive, which would let a large-but-scattered-and-stale sample look artificially confident. `consistency = 1 - dispersion` (coefficient of variation across the pool's own similarity scores) — a genuinely mixed/contradictory comparable pool suppresses confidence even at adequate sample size (verified by a dedicated test).
- **All four constants are disclosed-conservative policy defaults**, versioned implicitly via the module's own `SCORING_VERSION = "v1-provisional"` string, matching `THRESHOLD_VERSION`'s own precedent — a future recalibration against real accumulated data becomes a new version, never a silent redefinition.

## 5. Provenance handling

Every dimension result carries a `provenance: tuple[ProvenanceRef, ...]` — real table name, real provider name (`"weatherapi"`/`"the_odds_api"`/`"gnews"`, `None` when the table has no single-provider concept), real row count, and the real earliest/latest timestamp actually used. An insufficient-evidence/unsupported result carries an empty provenance tuple (there is nothing to cite) rather than a fabricated reference. This is the concrete, machine-checkable trail behind every non-empty confidence/similarity number this pass produces.

## 6. Sport-agnostic boundaries

Every table this pass reads is already sport-agnostic by construction (`venues` since Phase 8.0.5 Pass 2; `weather_snapshots`/`odds_snapshots`/`news_article_history` carry no sport-specific columns at all). This pass's own new code introduces **zero** sport-specific literals, constants, or table/column names anywhere — not even a single named edit point of the kind `_SPORT_PATH`/`_SPORT_QUALIFIER` needed in Phase 8.0.5's provider adapters, because none of this pass's logic depends on which sport a game belongs to. `games.sport`/`.sport_id` are never read by this package. No NBA feature or NBA-specific code was begun, per HQ's explicit instruction.

## 7. Exact future integration point into Probability Modeling

**Not wired in this pass — a clean, documented seam only**, per HQ's "Do NOT reopen Phase 4" instruction. `app/agents/probability_modeling.py`'s `ProbabilityModelingAgent.build_evidence` (Milestone 4.6) currently returns:

```python
{"candidate": {...}, "upstream_findings": [...], "participation": {...}}
```

A later, separately-authorized pass would add exactly one new key:

```python
"contextual_performance": contextual_intelligence.to_json(),
```

where `contextual_intelligence` is this pass's own `ContextualIntelligenceResult`, built once per `SequentialDecisionContext.game_id` before the sequential Decision & Advisory chain runs — the same point `AgentContext`/`odds_history`/`line_movement` are already composed today (`app.agents.context.build_agent_context`). This pass touches no committee-agent count, routing, consensus, or recommendation-behavior code; `probability_modeling.py` itself is unmodified (confirmed via `git status` — every file this pass touched is new).

## 8. Tests added/results

**58 new tests**, all passing, covering every scenario HQ named:

| Scenario | Where |
|---|---|
| Sufficient evidence | `test_weather.py::test_sufficient_evidence_consistent_pool...`, `test_market_dimension.py::test_sufficient_evidence_with_similar_movement_pool`, `test_venue.py::test_sufficient_venue_history...` |
| Insufficient evidence | Every dimension's own dedicated test, plus all 6 unsupported dimensions in `test_unsupported.py` |
| Sparse history | `test_weather.py::test_sparse_history_below_floor...`, `test_market_dimension.py::test_sparse_comparable_pool...`, `test_venue.py::test_sparse_venue_history...` |
| Stale history | `test_weather.py::test_stale_history_lowers_confidence_via_recency` |
| Mixed/contradictory context | `test_weather.py::test_mixed_contradictory_pool_lowers_confidence_via_dispersion` |
| Missing weather | `test_engine.py::test_missing_weather_still_produces_full_result_for_other_dimensions` |
| Dome game | `test_weather.py::test_dome_game_buckets_against_other_domes_only`, `test_unresolved_roof_type_bucketed_separately_never_coerced` |
| No relevant news | `test_news.py::test_no_relevant_news_is_insufficient_evidence` |
| Market movement with no explanatory context | `test_market_dimension.py::test_market_movement_with_no_explanatory_context` |

Plus: scoring primitives (`test_scoring.py`, 12 tests), full end-to-end engine assembly against mocked real-shaped I/O (`test_engine.py`, 3 tests, including a zero-real-data run proving all ten dimensions still appear), and persistence read-boundary tests (`test_context_intelligence_reads.py`, 7 tests). **No LLM call anywhere in this package or its tests** — every test is a deterministic assertion against a pure function or mocked HTTP response.

Full suite: **842/842 ai-orchestrator tests passing** (784 pre-existing + 58 new), zero regressions — confirmed via `git status` that no pre-existing file was modified.

## 9. Remaining data blockers

Unchanged from Phase 8.0.5's own closeout audit, restated here because this pass's own insufficient-evidence results are the direct, load-bearing consequence of them:

- **Player/roster identity** — `players`/`player_provider_ids` fixture-only/empty.
- **Injuries** — BALLDONTLIE entitlement blocked on the account's open invoice.
- **Roster/depth** — persistence code complete, never invoked against a live provider.
- **Player/team stats** — fixture-linked only; real capture gated on the reserved final SportsDataIO call.
- **Game events/PBP** — genuinely zero rows, blocked on the 2026-09-09/10 live-game validation window.

## 10. Recommendation for Phase 8.2

1. **Wire this pass's `contextual_performance` key into `build_evidence`** — the one-line, already-documented integration point in §7 — as its own small, explicitly-scoped pass (reopens Phase 4 deliberately, with HQ's sign-off, not as a side effect of anything else).
2. **Close the roster/depth gap next**, not player stats — `app.persistence.roster_ingestion` (sports-intel-layer) is already complete code sitting unused; wiring one real `RosterAdapter` call is a smaller lift than the reserved-SportsDataIO-call decision player stats depends on, and would upgrade `roster_role`/`depth_lineup` from insufficient-evidence to real.
3. **Do not build player-level or team-stats contextual dimensions until real data exists** — this pass's own `unsupported.py` stubs are the correct, honest placeholder until then; building against fixtures now would only need to be torn out later.
4. **Revisit `SCORING_VERSION`'s constants once real sample sizes grow** (more real games, more real weather/odds/news history accumulating daily) — `RECENCY_HALF_LIFE_DAYS`/`MIN_SAMPLE_FOR_FULL_CONFIDENCE`/`INSUFFICIENT_SAMPLE_FLOOR` are disclosed-provisional, not final; a future pass with real accumulated volume can reconsider them deliberately, bumping the version rather than silently redefining it.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls; no staging/prod; no Phase 7.2/7.3 (Milestone 7.1's pure functions reused, its write path/orchestrator never called); no Phase 4 modification (`probability_modeling.py` and every other Phase 4 file untouched, confirmed via `git status`); no Milestone 5.6; no invented data (every unsupported dimension explicit, every fixture excluded by its own real provenance marker); no player-level contextual claim anywhere (all six player/roster/stats/PBP-adjacent dimensions are fixed insufficient-evidence stubs); no LLM call anywhere in the engine.
