# MANSA End-to-End Decision Flow Audit (2026-09-08)

**Status: read-only audit and architecture mapping. No code, schema, migration, worker cadence, or provider-call change was made by this pass.** HQ directive: trace the complete real journey of a user request through MANSA, distinguishing what's actually implemented from what the Blueprint describes, without implementing anything new. Compiled from four parallel, independent, file:line-citing codebase traces (repo `/home/user/ThePlaybook`, services `apps/api-gateway`, `apps/sports-intel-layer`, `apps/ai-orchestrator`, `apps/workers`) plus this session's own Phase 8.4/8.4E/Context-Assembly-Proof findings.

Status vocabulary used throughout, consistently:
- **IMPLEMENTED AND WORKING** — real code, reachable, exercised by a real path.
- **IMPLEMENTED BUT NOT CONNECTED** — real code exists and is correct, but nothing invokes it (no route, no cron target, no caller).
- **PARTIALLY IMPLEMENTED** — real code exists but only handles part of the real requirement, or runs against fixture/incomplete data.
- **DOCUMENTED ONLY** — described in `docs/blueprint/` (or a name-string placeholder in code), no real implementation.
- **MISSING** — not built, not documented as in-progress, no placeholder.

---

## 1. Executive Summary

MANSA today is a **cron-driven, pre-computation pipeline with a thin read-only user-facing surface** — not a conversational, on-demand answer system. A logged-in user never asks MANSA anything in real time; they open a dashboard that displays `recommendation_products` rows a backend `Recommendation Worker` cron cycle already computed and persisted, for whichever NFL games happen to be on today's `master_refresh_runs` slate. There is no sport/league/game/market parameter anywhere in the user-facing API, no intent resolution, no chat/NL endpoint reachable from any real route, and no parlay logic at all.

Underneath that surface, the real pipeline (Master Refresh → Recommendation Worker → 6-of-17 real fan-out agents → Probability Modeling (LLM) → deterministic Consensus/EV/Risk/Strategy Engine → Explainability → Postgame Grading) is genuinely built, tested, and wired for its NFL-only, single-candidate-at-a-time scope. Its single biggest internal gap is that a second, more sophisticated evidence layer — **Context Intelligence** (`apps/ai-orchestrator/app/context_intelligence/`) — is real, tested, and already reads real `news_article_history`/`venues` tables the fan-out committee itself never touches, but is **explicitly, self-documented as unwired** from Probability Modeling. This is the exact gap the newly-locked **Context Assembly Proof** (Volume 4 §8.6 v5.15, this session's prior pass) exists to close before that wiring is trusted — and the proof itself cannot yet be executed, because real per-game player performance data (the dimension it depends on most) doesn't exist anywhere in this schema yet.

**The first place a real beta user's request actually breaks down is Stage 1→2**: there is no mechanism to receive "what is the best NFL pick this weekend?" as a question at all. The user instead receives whatever the backend already decided to compute, with no way to ask for "the safest bet," "three picks," or a parlay — those distinctions don't exist anywhere in the system today.

---

## 2. Complete End-to-End Flow Diagram

```
[Cron: cron-master-refresh]                    [Cron: cron-recommendation-worker]
        │                                                │
        ▼                                                ▼
run_master_refresh                          run_recommendation_worker_cycle
 (sports-intel-layer)                              (apps/workers)
   │  - fetch schedule → games                         │  - read latest master_refresh_runs
   │  - per-team roster fetch                           │  - read games.status='scheduled'
   │  - assemble daily_game_intelligence                │
   │    (odds/props/injury/weather/news/rest/venue)      ▼
   │                                          run_game_recommendation (ai-orchestrator)
   ▼                                                     │
 [odds_snapshots, injury_reports, weather_snapshots,    │  1. idempotency check (cycle_completed_at)
  news_article_history, team_stats, player_stats,       │  2. run_fan_out — 6-of-17 real Context & Data agents
  venues, daily_game_intelligence] — Supabase            │     (injury/weather/travel/rest/vegasline/closingline)
                                                          │     ⚠ Context Intelligence engine (weather/market/
                                                          │       news/venue, real, tested) exists but is NOT
                                                          │       called from here — separate, unwired path
                                                          │  3. generate_candidates_for_game (odds_snapshots →
                                                          │     up to 6 MarketCandidate: ML/spread/total × H/A)
                                                          │  4. per candidate: Probability Modeling (LLM,
                                                          │     sees only fan-out outputs + candidate, never
                                                          │     raw evidence) → EV → Risk → Consensus (deterministic)
                                                          │     → optional Elite reconciliation → Bankroll Coach
                                                          ▼
                                          Strategy Engine (qualify: confidence≥0.55, EV>0)
                                                          │  → recommendation_products / recommendation_legs
                                                          │  → Explainability (why_selected/risks/limitations)
                                                          │  → Lifecycle event (ACTIVATED)
                                                          ▼
                                   [User] GET /v1/recommendations/today (api-gateway, JWT auth)
                                          — reads already-persisted rows only, computes nothing
                                                          │
                                              (game plays out, in real time — nothing captured in-game)
                                                          ▼
                                   [Cron/event] Postgame Grading — grade_leg/rollup_product_outcome
                                          → recommendation_leg_grade_events / product_grade_events
                                          (Adaptive Weighting: proposes only, never mutates agent weight)
```

**No box above represents a live, user-triggered computation.** Every AI/probability/consensus step happens on a fixed backend cadence, before any user ever asks anything.

---

## 3. Current Implementation Map (by stage)

### Stage 1 — User Request

**Real endpoints** (`apps/api-gateway`, all behind Supabase-JWT `Authorization: Bearer` except `/health` and demo routes): `GET /health`; `GET/PATCH /v1/user/profile`; `GET /v1/recommendations/today`, `GET /v1/recommendations`, `GET /v1/recommendations/{display_id}`, `GET /v1/recommendations/{display_id}/reconstruction`; `GET /v1/track-record`; `GET /v1/user/subscription`; `GET /v1/system/freshness`; demo routes (`POST /v1/demo/login` + operator-token-gated scenario endpoints, pure proxies to sports-intel-layer's internal demo router).

**Auth trace**: `apps/api-gateway/app/auth.py:53-74` forwards the raw bearer token to Supabase Auth's `/auth/v1/user` (delegates JWT verification, doesn't do it itself), then defense-in-depth confirms the `user_profiles` row still exists. The resulting `CurrentUser(id, email)` is used only for tier-gating within api-gateway (`app/entitlement.py:62-75`) — **user identity never reaches `ai-orchestrator` or `sports-intel-layer`**; those services only ever see `game_id`/`correlation_id` from cron/worker calls authenticated by a shared internal token.

**No endpoint anywhere accepts sport, league, game, or market.** `/today` and the list route take only `since`/`until`/`limit` date-window params; `/{display_id}` takes only an opaque system-assigned ID.

**Chat/NL/conversation/session-memory: DOCUMENTED ONLY.** The only non-doc hit for "chat" is `apps/frontend/components/marketing/ConversationalPreview.tsx` — a non-interactive marketing mockup whose own docstring states *"do not wire chat/parlay backend behavior yet... nothing here claims to be a live feature."* No `nl_engine` module, no `conversations` table, no `session_preferences` column exists anywhere. The full spec lives only in `docs/blueprint/v3.0-amendments-conversational-intelligence.md`.

**Can the system distinguish the 8 example questions ("best pick," "best NFL pick," "three picks," "build a parlay," "NFL-only parlay," "combine NFL and NBA," "safest bet," "highest value")? No — none of this exists.** The user only ever receives whichever `recommendation_products` rows the Recommendation Worker already computed for today's slate; there is no mechanism to request a different shape, scope, or ranking criterion.

**Verdict: recommendation *feed* (pre-computed, read-only) = IMPLEMENTED AND WORKING. Conversational/on-demand question-answering = DOCUMENTED ONLY, not built.**

### Stage 2 — Intent Resolution

**MISSING entirely.** No intent taxonomy, classifier, or routing logic exists in code anywhere. This is architecturally clean territory — nothing needs to be undone, but nothing exists to build on either. Proposed taxonomy for future implementation (not built, listed per HQ's request):

| Intent | Exists today? |
|---|---|
| Best single recommendation | Implicit only — it's the only shape the pipeline ever produces per game |
| Ranked recommendations / "give me three" | MISSING — no ranking-and-return-N logic anywhere |
| Single-game analysis | Partially implicit (`/v1/recommendations/{display_id}` returns one product) |
| Market-specific analysis | MISSING |
| Player-prop analysis | MISSING — props explicitly deferred from candidate generation |
| Parlay (any kind) | MISSING (Stage 12) |
| "Safest"/"highest confidence" | MISSING — no query path orders by confidence, only by date |
| "Highest value" | MISSING — no query path orders by EV |
| General game question | MISSING |
| Evidence explanation request | Partially implicit — `/reconstruction` returns stored explanation data, but only for an already-known `display_id`, never in response to a live question |

Architecturally, intent resolution belongs at the api-gateway layer (translating a user question into a query against already-computed `recommendation_products`) for anything the backend has already computed, and would need genuinely new backend computation (on-demand candidate evaluation) for anything outside today's precomputed slate — that distinction itself doesn't exist as a concept in the code today.

### Stage 3 — Sport and Scope Resolution

**Real, forward-looking schema exists and is unused in practice.** `supabase/migrations/20260807211306_sports_data_tables.sql` defines a genuine normalized multi-sport core — `sports`, `leagues`, `seasons`, with `games.sport_id`/`games.league_id` FKs alongside a legacy `games.sport text default 'nfl'` column. **No application code queries by `sport_id`/`league_id` anywhere** (zero hits outside migrations/tests); `apps/sports-intel-layer/app/persistence/schedule.py:111` writes the legacy column as the literal string `"nfl"` on every game upsert.

**Named-constant convention confirmed and consistently NFL-only**: `_SPORT_KEY = "americanfootball_nfl"` (`the_odds_api.py:51`), `_SPORT_PATH = "nfl"` (`balldontlie.py:78`) — both explicitly commented as "the one edit point" for a future second sport, itself proof no second sport is wired.

**Verdict: multi-sport core = IMPLEMENTED BUT NOT CONNECTED at the DB layer; every application code path (adapters, persistence writes, persistence reads, worker eligibility) = single-sport (NFL) in practice, by construction, not by an explicit gate.**

**Proposed decision tree for future multi-sport scope resolution** (not built):

```
User request arrives
  │
  ├─ Sport named explicitly? ──yes──> restrict analysis to that sport
  │                                    (needs: sport_id actually threaded through
  │                                     adapters/persistence/reads — none of which
  │                                     exist today)
  │
  └─ Sport not named ──> today: system is single-sport, so this branch is moot
                          future: ask user vs. use all eligible sports vs.
                          apply a stored preference — none of these three
                          options exist in code; this is a genuine future
                          product decision, not resolved by this audit

Parlay request
  │
  ├─ Same game? ──> needs same-game correlation modeling (MISSING, Stage 12)
  ├─ Same sport, multiple games? ──> needs cross-game independence assumption
  │                                   validation (MISSING)
  └─ Cross-sport? ──> needs a canonical candidate model that isn't NFL-scoped
                       by construction (MISSING — MarketCandidate has no
                       sport field at all, see Stage 5)
```

**Where the current architecture becomes insufficient for parlays, precisely**: `MarketCandidate` (Stage 5) has no sport/league field; `recommendation_products`/`recommendation_legs` have no sport/league field either — a cross-sport parlay couldn't even be represented in the current schema, let alone reasoned about probabilistically. Per HQ's explicit instruction, **no joint-probability math is proposed here** — this is named as an unresolved future requirement, not invented.

### Stage 4 — Opportunity Discovery

| Worker | Cadence | Writes to | Status |
|---|---|---|---|
| Master Refresh (schedule/roster/DGI assembly) | Triggered via `POST /v1/internal/master-refresh/run` | `games`, `daily_game_intelligence` | IMPLEMENTED AND WORKING |
| Odds Worker | Adaptive 24h→2min as kickoff nears | `odds_snapshots` (append-only, trigger-enforced) | IMPLEMENTED AND WORKING |
| Weather Worker | Flat 15 min, stop at kickoff (+4h in-game) | `weather_snapshots` (append-only) | IMPLEMENTED AND WORKING |
| News Worker | Flat 4h per team | `daily_game_intelligence.news` + `news_article_history` | IMPLEMENTED AND WORKING |
| Injury Worker (SportsDataIO) | Day-of-week + kickoff-proximity tiers | `injury_reports` | **IMPLEMENTED BUT NOT CONNECTED** — no internal HTTP endpoint wired |
| Injury Worker (BALLDONTLIE, DEV) | One-shot only, not recurring | `injury_reports` | IMPLEMENTED AND WORKING (one-shot), but entitlement-BLOCKED (Sep 5 invoice, per Phase 8.4E) |
| Player Props Worker | Same tiers as Odds | `odds_snapshots` (market_type='prop') | **IMPLEMENTED BUT NOT CONNECTED** — `cron_dispatch.py` explicitly documents this gap |
| Pregame Worker | T-minus-5 coordination | (coordinates the above) | **IMPLEMENTED BUT NOT CONNECTED** |
| Postgame Ingestion Worker | Event-triggered on game-final | `team_stats`, `player_stats` (idempotent, NOT append-only) | **IMPLEMENTED BUT NOT CONNECTED** |

This last row is a critical, previously under-emphasized finding: **the reason `team_stats`/`player_stats` hold only 2 fixture-pattern rows each is not (only) provider access — the ingestion worker that would persist real post-game stats has no internal endpoint wired to invoke it at all**, independent of any MySportsFeeds/BALLDONTLIE gate. This is immediately fixable — see §12.

**CURRENT STATE vs. HISTORICAL EVIDENCE, clearly distinguished**: `daily_game_intelligence` (one upserted row per game — current state only) vs. `odds_snapshots`/`injury_reports`/`weather_snapshots`/`news_article_history`/`player_stats`/`team_stats` (append-only or insert-tracked history). Master Refresh and Pregame Worker write the former; the specialized workers write the latter.

### Stage 5 — Candidate Generation

**Yes — a single canonical candidate model exists**: `MarketCandidate` (`apps/ai-orchestrator/app/features/candidate.py:21-33`) — `game_id, sportsbook, market_type, selection, american_odds, point, observed_at`, plus a deterministic `candidate_key()`. **No sport/league field.**

- **Created by**: `generate_candidates_for_game` (`candidate_generation.py`) — reads `odds_snapshots`, picks a reference sportsbook, applies a freshness ceiling derived from the poll cadence, emits up to 6 candidates (home/away × moneyline/spread/total). Player props explicitly deferred.
- **Consumed by**: the per-candidate evaluation loop → Probability Modeling → Consensus → Strategy Engine → `EvaluatedCandidate`.
- **Eligibility gates found**: `games.status == 'scheduled'` only; a market is skipped if its latest odds snapshot is missing or stale; a game is skipped entirely if no sportsbook has fresh data. **No sport eligibility gate** — the system is single-sport by construction, not by a checked condition.
- **`daily_game_intelligence` is NOT the candidate object** — it's a pregame context bundle (current-state odds/props/weather/injuries/news/rest/stadium), explicitly excluding any AI/recommendation output. The real "opportunity" unit is `MarketCandidate`, generated from history (`odds_snapshots`), not from DGI's single-latest-snapshot fields.

**Verdict: IMPLEMENTED AND WORKING** — this is one of the most solid, fully-wired parts of the real pipeline.

### Stage 6 — Evidence Assembly

**Two independent evidence paths exist — this is the audit's single most important structural finding.**

- **Path A (legacy, wired)**: `build_agent_context` → `AgentContext` → the 6 real fan-out agents → real recommendation cycle.
- **Path B (new, unwired)**: `build_contextual_intelligence` → `ContextualIntelligenceResult` → consumed only by its own tests (Stage 7).

| Source | Table | DATA EXISTS | DATA IS USED (by real committee) |
|---|---|---|---|
| Odds / market movement | `odds_snapshots` | LIVE — real, ~130+ rows | ✅ IMPLEMENTED AND WORKING (VegasLine/ClosingLineMovement agents) |
| Weather | `weather_snapshots` | LIVE — real rows flowing | ✅ IMPLEMENTED AND WORKING (via `daily_game_intelligence`, WeatherAgent) |
| Injuries | `injury_reports` | PARTIAL/BLOCKED — 1 fixture row; real adapter blocked on BALLDONTLIE entitlement | ✅ plumbing works (InjuryIntelligenceAgent queries DGI every cycle) — but has only fixture-quality data to carry today |
| Venue (lat/long, travel) | `games.venue_lat/long`, `venues` | LIVE — 5 real rows | ✅ travel/timezone wired (TravelFatigueAgent); ❌ the dedicated `venues` table itself is read ONLY by Path B (unwired) |
| News | `news_article_history` | LIVE — 97+ real rows, 4h cadence | ❌ **IMPLEMENTED BUT NOT CONNECTED** — read only by Path B; zero fan-out agents consume it |
| Player identity | `players`, `player_provider_ids` | MISSING/fixture-only (6 seed rows, 0 real provider ids) | ❌ MISSING |
| Roster / lineup-depth | `roster_memberships`, `depth_chart_snapshots` | MISSING (code ready, never invoked live) | ❌ MISSING |
| Player / team stats | `player_stats`, `team_stats` | MISSING/fixture-only (2 rows each) | ❌ MISSING |
| Game events / PBP | `game_events` | MISSING (0 rows, deliberately deferred) | ❌ MISSING |

**The DATA EXISTS vs. DATA IS USED distinction, made explicit per HQ's instruction**: `news_article_history` and the `venues` table are real, populated, and actively growing — and completely invisible to the actual recommendation-generating committee today. This is not a data gap; it's a wiring gap, and (per §12) one of the cheapest to close.

### Stage 7 — Context Intelligence

**Real engine exists**: `build_contextual_intelligence` (`apps/ai-orchestrator/app/context_intelligence/engine.py`). Supported dimensions (real queries): **weather, market, news, venue** — all four genuinely query real tables and produce a fully-specified `ContextualDimensionResult` (confidence/similarity/recency/provenance, `None` rather than fabricated when insufficient). Unsupported dimensions (honest, explicit stubs, never silently omitted): **player_performance, injuries (real reason: BALLDONTLIE entitlement blocked), roster_role, team_performance, depth_lineup, game_state_pbp** — each returns a real `insufficient_evidence=True` result with an exact, quoted reason via `unsupported.py`.

**Confirmed: this integration remains intentionally unwired.** The engine's own module docstring names the exact future one-line change needed inside `ProbabilityModelingAgent.build_evidence` and explicitly states it is NOT wired in this pass. A repo-wide grep confirms zero references from any Probability Modeling/sequential/orchestration file. **Per HQ's explicit instruction, this audit does not wire it.**

**What must happen before this can safely be activated — the newly-locked Context Assembly Proof (Volume 4 §8.6 v5.15, this session's prior pass) is exactly that precondition**: before Context Intelligence → Probability Modeling wiring is trusted, MANSA must demonstrate a real Context Assembly Proof (2-3 real historical Hunter Henry games, every dimension classified JOINED/PARTIAL/UNAVAILABLE against real data). The Context Readiness Matrix locked in that same pass shows **real per-game player performance is BLOCKED** — the exact dimension `player_performance`/`game_state_pbp` need — so neither the proof nor this wiring can proceed today, independent of this audit's own findings, which confirm the same picture from the code side rather than the data side.

**Verdict: IMPLEMENTED BUT NOT CONNECTED**, with an explicit, already-locked gate (Phase 8.1 Gate) blocking the connection until real substrate exists.

### Stage 8 — Probability Modeling

**Real entry point**: `ProbabilityModelingAgent.build_evidence` (`apps/ai-orchestrator/app/agents/probability_modeling.py`) — returns exactly `candidate` (identity/odds), `upstream_findings` (the 6 fan-out agents' outputs), `participation` (committee-completeness metadata). **It never sees raw evidence directly** — only the fan-out committee's already-summarized outputs; that assembly happened one step earlier (`build_agent_context`).

**No deterministic probability prior is computed before the LLM call.** `modeled_probability` is produced entirely by the LLM, anchored only to candidate identity/odds and upstream committee findings. The de-vigged/implied probability is computed only *after*, purely for EV math — never fed back into the model's own evidence.

**Missing-data behavior**: partial committee participation is treated as expected and disclosed (not an error) — the LLM is instructed to weigh only present findings and never treat a `null` fact as neutral. If the LLM call itself fails, the whole sequential chain (Probability → EV → Risk) is marked failed for that candidate, never silently proceeding.

**Context Intelligence's entry point**: exactly the one-line addition named in the engine's own docstring, inside this file's `build_evidence` — not yet made (Stage 7).

**Documentation vs. reality gap**: the Blueprint (Volume 4 §2.5) describes Probability Modeling eventually incorporating contextual-impact evidence; today it incorporates only fan-out-committee output and candidate identity.

**Verdict: IMPLEMENTED AND WORKING** for its current, narrower scope; the eventual Context Intelligence integration remains DOCUMENTED ONLY / gated.

### Stage 9 — AI Committee

**12 real agents against a documented 22.** Fan-out (Context & Data): 6 real (Injury Intelligence, Weather, Travel & Fatigue, Rest Days, Vegas Line, Closing Line Movement) out of 17 configured — the other 11, **including every "Matchup & Form" agent (Offensive/Defensive Matchup, Team Form, Player Prop) and Sharp Money/Public Betting, exist only as name-strings in `CONFIGURED_AGENTS` — DOCUMENTED ONLY, not real code.** Sequential (Decision & Advisory): 4 real (Probability Modeling, EV, Risk Manager — deliberately degraded, Bankroll Coach). Meta/Elite: 2 real (Meta Agent, Elite Reconciliation).

`committee_completeness` (6/17 for fan-out) is computed live and persisted every cycle — honestly tracked, not hidden.

**Consensus Engine: IMPLEMENTED AND WORKING**, deterministic, candidate-anchored (not game-level vote); a real, previously-corrected "Elite second-pass variance threshold" (0.10, replacing an unreachable 0.25) triggers a second pass only for elite-tier subscribers on high-disagreement candidates.

**Can the committee currently evaluate a "complete" candidate? No — only a partial one.** Every recommendation today is built from 6 of 17 possible Context & Data signals; matchup/form/player-prop analysis (arguably central to "is this a good bet") simply doesn't exist yet. This is the real handoff break for Stage 9: **Evidence → Probability Modeling → Committee → Decision works end-to-end, but the "Committee" step is running at roughly a third of its documented designed width.**

### Stage 10 — Final Recommendation

**Canonical model exists**: `recommendation_products`/`recommendation_legs`. Real fields: `market_type`, `selection`, `sportsbook`, `american_odds`/`point`/`decimal_odds`, `ev_per_dollar`, `final_aggregate_confidence` — all on the **leg**, not the product. **`recommendation_products` itself has no sport/league/confidence/probability/price field** — only `game_id`, `recommendation_type`, `scope`, and linkage IDs. Evidence summary/risks/counterarguments/data-limitations/provenance are real but live in a **separate** table (`recommendation_product_explanations`/`recommendation_leg_explanations`), not on the product/leg row itself. Timestamp: implicit (`created_at` default), not an explicit named field in the payloads inspected.

**`run_game_recommendation` traced end-to-end** (`apps/ai-orchestrator/app/orchestration/recommendation_worker.py`): game existence check → idempotency check → fan-out cycle → participation metadata → candidate generation → per-candidate evaluation (Probability→EV→Risk→Consensus→optional Elite→per-subscriber Bankroll Coach) → mark cycle complete. Strategy Engine finalization and Explainability generation happen in a separate, subsequent orchestration step (`strategy_finalize`), not inside this function itself.

**Verdict: IMPLEMENTED AND WORKING**, with sport/league notably absent from the schema everywhere it would need to exist for multi-sport support.

### Stage 11 — User Explanation

**A real, deterministic Explainability Engine exists and is wired** (`app/features/explainability.py`, `app/orchestration/explainability.py`) — `why_selected`, `strongest_evidence`, `biggest_risks`, `data_limitations`, `rejected_alternatives`, `would_change_mind_if` (verbatim-quoted from the top agent, never synthesized), `contributing_agents` (with full model/prompt provenance).

**The FACT / INFERENCE / MODEL OUTPUT / INSUFFICIENT EVIDENCE four-way taxonomy HQ asked about does not exist as such — DOCUMENTED ONLY.** The real, code-enforced classification is a *different*, three-way scheme (`EvidenceClassification`: `data_backed | inference | assumption`), applied per-agent-output, not as an explanation-level category. This is a real, disclosed gap between what future MANSA product copy should say and what the current code actually distinguishes.

### Stage 12 — Parlay Architecture

**MISSING, and self-documented as inactive in the real code's own comments** — not merely absent. `explainability.py` and `candidate.py` both contain live prose stating parlay combination "is not currently active" and that "no correlation or combined-probability calculation exists in this system." No `same_game_parlay`/`multi_game_parlay`/`cross_sport_parlay` class, table, or function exists anywhere.

**Architectural requirements before MANSA can responsibly recommend parlays** (per HQ's framing, no math invented here): (1) a canonical candidate/recommendation model that carries a sport/league field (currently absent, Stage 5/10); (2) an explicit decision tree for same-game vs. multi-game vs. cross-sport combination (Stage 3's proposed tree); (3) a real correlation/joint-probability model — **explicitly named as an unresolved future requirement, not built or approximated here**, per HQ's explicit "do not invent joint probability, do not use multiplication as a shortcut" instruction.

### Stage 13 — Outcome and Learning Loop

**Postgame Grading: IMPLEMENTED AND WORKING** — `grade_leg`/`rollup_product_outcome` (deterministic, market-type-aware), wired to a real internal endpoint. Records: recommendation/leg identity, frozen `authoritative_result`, `outcome`, `grading_version`. **Evidence-at-decision-time and actual odds are not re-recorded at grading time** — they're inherited by reference from the already-frozen `recommendation_legs`/`recommendation_agent_outputs` rows, an architecture choice (not a gap) consistent with this project's append-only, "grading is status-blind" discipline. **Calibration and user feedback: MISSING** — no column anywhere in the grading module.

**Adaptive Weighting: IMPLEMENTED, but PROPOSE-ONLY by design** — the real formula (learning_rate=0.25, ±10% clamp, sample_size≥200, 90-day window) computes a proposed weight, but `applied_weight` is always `None`; nothing anywhere writes `agents.current_weight`. The module's own code discloses that **zero real graded recommendations exist yet** to evaluate it against — implementation-validated only, not empirically validated.

**Milestone 5.6 Lifecycle: IMPLEMENTED AND WORKING, not schema-only.** `persist_lifecycle_event` is real and actively called for `ACTIVATED` events from the real Time Machine orchestration path. `WITHDRAWN`/`SOFT_DELETED` exist in the schema but no call site writes them yet in the code inspected. **`trigger_type` (the richer vocabulary from this session's Milestone 5.6 lock, Volume 3 §5G/Volume 4 §9.7) does not exist in the codebase at all** — confirming it remains exactly what the Blueprint says it is: DESIGN LOCKED, NOT YET IMPLEMENTED. The real, currently-implemented column is the older `event_type`.

### Stage 14 — Beta User Journey (proposed, FUTURE — not implemented)

| Step | Status |
|---|---|
| User arrives / signs up | CURRENTLY REAL (Supabase Auth, `user_profiles`) |
| Selects preferred sports | PLANNED — no UI/schema field found for this |
| Asks MANSA a question | PLANNED — no entry point exists (Stage 1) |
| Intent is resolved | PLANNED — no taxonomy/classifier exists (Stage 2) |
| Scope is resolved (sport/game/market) | PLANNED — schema exists (Stage 3), no application wiring |
| Eligible opportunities discovered | CURRENTLY REAL (Master Refresh + specialized workers, partially connected — Stage 4) |
| Evidence assembled | PARTIALLY REAL — Path A wired, Path B (Context Intelligence) built but unwired (Stage 6-7) |
| Data sufficiency checked | PARTIALLY REAL — freshness/eligibility gates exist for candidates; no per-question sufficiency check exists since there's no question to check against |
| Probability/committee evaluation | PARTIALLY REAL — real and working, at 6/17 fan-out width (Stage 8-9) |
| Recommendation produced | CURRENTLY REAL, but always pre-computed, never on-demand (Stage 10) |
| Explanation | PARTIALLY REAL — real mechanism, different taxonomy than the future FACT/INFERENCE spec (Stage 11) |
| User feedback | PLANNED — no column/endpoint exists |
| Outcome capture | CURRENTLY REAL for win/loss/push grading; PLANNED for calibration/feedback (Stage 13) |

---

## 4. Gap Map (highest-impact gaps, not exhaustive)

1. **No question-answering entry point exists at all** — the single largest gap between the product vision and reality.
2. **Context Intelligence (news/venue/weather/market dimensions) is built and real but completely unwired from Probability Modeling** — the cheapest-to-close structural gap in the whole pipeline, gated behind the Context Assembly Proof for the dimensions that still need real data (player performance), but the weather/market/news/venue dimensions could arguably be wired sooner since their own substrate is already real (a decision for HQ, not made here).
3. **11 of 17 fan-out agents (all Matchup & Form) are name-strings only.**
4. **Postgame Ingestion Worker (team_stats/player_stats capture) has no internal HTTP endpoint** — independent of any external provider gate, this alone keeps those tables fixture-only.
5. **No sport/league field exists on `MarketCandidate`, `recommendation_products`, or `recommendation_legs`** — a structural blocker for both real multi-sport support and any cross-sport parlay.
6. **Parlay logic, correlation modeling, and joint probability are entirely absent** (expected/correct per HQ's scope).
7. **FACT/INFERENCE/MODEL OUTPUT/INSUFFICIENT EVIDENCE taxonomy doesn't exist** — a real, disclosed gap between planned product copy and current code.
8. **Zero real graded recommendations exist to validate Adaptive Weighting or produce real calibration/user-feedback data.**

---

## 5. Data-Flow Map

See §2's diagram and Stage 4/6 tables above — CURRENT STATE (`daily_game_intelligence`) vs. HISTORICAL EVIDENCE (`odds_snapshots`, `injury_reports`, `weather_snapshots`, `news_article_history`, `player_stats`, `team_stats`) is a real, consistently-applied distinction throughout the codebase, not just a documentation convention.

## 6. Decision-Flow Map

Evidence (Path A only) → Probability Modeling (LLM, no deterministic prior, no Context Intelligence) → per-candidate Consensus (deterministic) → Strategy Engine qualification → Explainability → persisted recommendation. The chain does not break mechanically anywhere in this sequence — it is fully wired end-to-end for the 6-of-17-agent, NFL-only, no-parlay scope it currently has. The "break" is one of *completeness*, not *connectivity*: the pipeline is real and running, just narrower than the product vision describes.

## 7. Multi-Sport Readiness Assessment

Schema-ready, application-not-ready. `sports`/`leagues`/`seasons` tables and `games.sport_id`/`league_id` exist and are unused; every adapter, persistence write, and read path is NFL-hardcoded via named single-edit-point constants; no candidate/recommendation model carries a sport field. Adding a second sport today would require: threading `sport_id` through every adapter/persistence/read function, adding a sport field to `MarketCandidate`/`recommendation_products`/`recommendation_legs`, and building real cross-sport eligibility logic (Stage 3's decision tree) — none of which is started.

## 8. Parlay Architecture Assessment

See Stage 12. MISSING, self-documented as inactive, with real prose in the code itself naming the gap. Requirements before any parlay work begins: sport/league field on candidates and products; an explicit same-game/multi-game/cross-sport decision tree; and — the largest, deliberately unresolved item — real correlation/joint-probability modeling, which this audit does not invent or approximate per HQ's explicit instruction.

## 9. Recommendation Lifecycle Assessment

Real and working for the `ACTIVATED` case; `WITHDRAWN`/`SOFT_DELETED` schema-ready but unexercised; the richer `trigger_type` vocabulary (Milestone 5.6, Volume 3 §5G/Volume 4 §9.7) is confirmed DESIGN LOCKED, NOT YET IMPLEMENTED — matching the Blueprint's own stated status exactly, no drift found here.

## 10. Beta User Journey

See Stage 14 table above.

## 11. Critical Blockers

1. No conversational/question-answering entry point (Stage 1-2) — blocks the entire premise of "ask MANSA a question."
2. Context Intelligence ↔ Probability Modeling wiring blocked by the Context Assembly Proof gate, itself blocked on real per-game player performance data (external provider gates, tracked separately in the Phase 8.4/8.4E/Context-Assembly-Proof work).
3. 11/17 fan-out agents unbuilt (Matchup & Form entirely absent) — no data or provider gate here, purely unbuilt code.
4. Postgame Ingestion Worker unwired — no external gate, purely a missing internal HTTP route + cron target.
5. No sport/league field anywhere in the candidate/recommendation schema — blocks both real multi-sport and any parlay work.

## 12. Recommended Implementation Order (sequencing only — not authorized by this audit)

**Buildable immediately, no live-game data needed:**
- Wire Player Props Worker's, Pregame Worker's, and Postgame Ingestion Worker's internal HTTP endpoints + cron targets (code already exists and is tested; this is pure wiring).
- Wire `news_article_history`/`venues` table reads into the real fan-out committee (a News agent, a Venue agent) — the data is already real and flowing; only the consumer is missing.
- Add a FACT/INFERENCE/MODEL OUTPUT/INSUFFICIENT EVIDENCE explanation taxonomy alongside (not replacing) the existing `EvidenceClassification` scheme.
- Design (not build) the sport/league field addition to `MarketCandidate`/`recommendation_products`/`recommendation_legs` — a schema decision for a future authorized pass.
- Design (not build) a minimal, rule-based intent taxonomy for api-gateway that maps a handful of question shapes onto existing pre-computed data (e.g. "safest bet" → order by `final_aggregate_confidence` desc) — none of this needs new evidence, only new query logic over what's already computed.

**Blocked on real data (tracked separately under Phase 8's Context Assembly Proof / Gate A / Gate B):**
- Wiring Context Intelligence's `player_performance`/`injuries`/`roster_role`/`team_performance`/`depth_lineup`/`game_state_pbp` dimensions into anything.
- Building the 11 missing Matchup & Form agents (they'd have nothing real to reason over today — `team_stats`/`player_stats` are fixture-only, and real per-game data is exactly what Gate A/Gate B are waiting on).
- Empirically validating Adaptive Weighting (needs real graded recommendations at volume, which needs real games to have been played and real recommendations to have been generated against them).
- Any real, on-demand recommendation computation for a live user question (needs the intent-resolution and evidence-completeness work above first, not a data gate, but a real build item beyond this audit's scope).

---

## Consolidated Stage Table

| Stage | Status | Real Code/Service | Real Data | Missing Piece | Dependency |
|---|---|---|---|---|---|
| 1. User Request | IMPLEMENTED AND WORKING (read-only feed) / DOCUMENTED ONLY (question-answering) | `apps/api-gateway/app/recommendations.py`, `auth.py` | `recommendation_products`/`legs` (real, pre-computed) | Any endpoint accepting a question, sport, or scope | api-gateway route + schema |
| 2. Intent Resolution | MISSING | — | — | Intent taxonomy/classifier entirely | Stage 1 entry point |
| 3. Sport/Scope Resolution | IMPLEMENTED BUT NOT CONNECTED | `sports`/`leagues`/`seasons` migrations | Schema real, 0 real rows queried | Application code reading `sport_id`/`league_id` anywhere | New adapter/persistence work |
| 4. Opportunity Discovery | PARTIALLY IMPLEMENTED | `apps/sports-intel-layer/app/workers/*`, `apps/workers/app/cron_dispatch.py` | `odds_snapshots`, `weather_snapshots`, `news_article_history` real; `injury_reports`/`player_stats`/`team_stats` fixture-only | Internal HTTP endpoints for Player Props/Pregame/Postgame Ingestion Workers | `sports-intel-layer/app/main.py` route registration |
| 5. Candidate Generation | IMPLEMENTED AND WORKING | `apps/ai-orchestrator/app/features/candidate.py`, `candidate_generation.py` | `odds_snapshots` (real) | Sport/league field on `MarketCandidate` | Stage 3 |
| 6. Evidence Assembly | PARTIALLY IMPLEMENTED | `apps/ai-orchestrator/app/agents/context.py` (Path A, wired); `app/context_intelligence/*` (Path B, unwired) | Odds/weather real+used; news/venues real+unused; player/roster/stats/PBP missing/fixture | Wiring news/venues into fan-out; real player-level substrate | Phase 8 Context Assembly Proof (player data) |
| 7. Context Intelligence | IMPLEMENTED BUT NOT CONNECTED | `apps/ai-orchestrator/app/context_intelligence/engine.py` | weather/market/news/venue real; 6 dims honest stubs | One-line wiring into Probability Modeling | Context Assembly Proof + Phase 8.1 Gate (locked, 2026-09-08) |
| 8. Probability Modeling | IMPLEMENTED AND WORKING (narrower scope than Blueprint) | `apps/ai-orchestrator/app/agents/probability_modeling.py` | Fan-out committee outputs only | Context Intelligence input; deterministic prior | Stage 7 |
| 9. AI Committee | PARTIALLY IMPLEMENTED (12/22 agents) | `apps/ai-orchestrator/app/agents/*`, `features/consensus.py` | Real for the 6 built fan-out agents | 11 fan-out agents (all Matchup & Form) | Real team/player stats substrate |
| 10. Final Recommendation | IMPLEMENTED AND WORKING | `apps/ai-orchestrator/app/persistence/recommendation_products.py` | Real, persisted | Sport/league field on product/leg | Stage 3 |
| 11. User Explanation | PARTIALLY IMPLEMENTED | `apps/ai-orchestrator/app/features/explainability.py` | Real, different taxonomy | FACT/INFERENCE/MODEL OUTPUT/INSUFFICIENT EVIDENCE enum | New taxonomy design |
| 12. Parlay Architecture | MISSING (self-documented) | — | — | Sport field, decision tree, correlation modeling | Stages 3, 5, 10 + new math |
| 13. Outcome/Learning Loop | PARTIALLY IMPLEMENTED | `apps/ai-orchestrator/app/features/grading.py`, `adaptive_weighting.py` | Grading real; Adaptive Weighting propose-only, unvalidated | Calibration, user feedback columns; real graded volume | Real games played + graded at scale |
| 14. Beta User Journey | PLANNED (proposed only) | — | — | Everything upstream of it that's PLANNED above | All of the above |

## Most Important Question

**"If a real beta user opened MANSA today and asked 'What is the best NFL pick this weekend?' what would actually happen, step by step?"** — answered strictly from real code, not the Blueprint:

1. There is no way to ask that question. No endpoint accepts free text, a sport name, or a request shape.
2. The user would instead open the dashboard and call `GET /v1/recommendations/today`, which returns whatever `recommendation_products` rows already exist for today's slate — computed automatically by the Recommendation Worker's cron cycle, entirely independent of and prior to the user's visit.
3. Since MANSA is single-sport today, "NFL pick" is redundant — every row returned is already NFL; there is no way to further filter, rank by "best," or request an alternative shape (safest, highest-value, three picks, a parlay). The user sees exactly what the backend already decided to show, or a "No Bet Today"/bankroll-preservation card if nothing qualified.
4. Whatever recommendation is shown was built from: Master Refresh's captured schedule/odds/weather/news, largely fixture-quality injury/roster/stats data (the real adapters for these are either entitlement-blocked or wiring-blocked), through 6 of 17 possible Context & Data agents, into a single LLM-driven Probability Modeling call (no deterministic prior, no Context Intelligence signal), through deterministic Consensus/EV/Risk/Strategy qualification, to a persisted, explained recommendation.

**What must be completed before that question can produce a trustworthy MANSA answer**: a real question-answering entry point and intent resolution layer (currently nonexistent); the remaining 11 fan-out agents, or an honest, disclosed acknowledgment that the committee evaluates on partial evidence; Context Intelligence wired into Probability Modeling, itself gated on the Context Assembly Proof clearing (which needs real per-game player data this project doesn't have yet); and a sport/league-aware schema if "NFL pick" is ever meant to be a meaningful filter rather than a tautology.

---

## What was and wasn't done this pass

Pure read-only audit across `apps/api-gateway`, `apps/sports-intel-layer`, `apps/ai-orchestrator`, `apps/workers`, and `docs/blueprint/`, performed via four parallel research passes, each citing real file:line locations, cross-checked against this session's own live Supabase evidence from the Phase 8.4E/Context Assembly Proof work. **Zero provider calls, zero purchases, zero schema/migrations, zero ingestion implementation, zero contextual scoring changes, zero Phase 4 changes, zero Milestone 5.6 changes, zero staging/production changes.** Phase 7 observation and active worker schedules were not touched or disturbed. The only artifact produced is this document.
