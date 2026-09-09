# Phase 8.5 — Request-to-Answer Architecture Audit and Beta Interaction Contract (2026-09-09)

**Status: read-only architectural audit and planning pass. No code, schema, migration, worker activation, cron change, credential change, or provider call was made.** Builds directly on the accepted 2026-09-08 end-to-end audit and the 2026-09-09 user-question-to-recommendation audit — this pass does not re-discover News, Venue, Weather, Odds/Market, Player Identity, Roster/Depth, or Player Season Stats as unknowns; each is treated as already-vetted project knowledge per HQ's explicit instruction, cited rather than re-derived.

---

## 1. Executive Verdict

MANSA's real pipeline (Master Refresh → Recommendation Worker → 6-of-17 fan-out agents → single-LLM Probability Modeling → deterministic Consensus/EV/Risk/Strategy → Explainability → persisted `recommendation_products`) is genuinely built and wired end-to-end for its current scope. The gap this pass exists to close is real and singular: **there is no canonical path for a user's request — natural-language or structured — to enter that pipeline at all.** The user-facing surface only ever reads what the backend already decided to compute.

**The most important architectural discovery of this pass, refining (and in one place correcting) the 2026-09-09 report's own recommendation**: the existing schema already contains the foreign keys needed to solve sport/league identity propagation — `games.sport_id`/`league_id`/`season_id` (nullable FKs to the real `sports`/`leagues`/`seasons` tables) exist today and are simply never populated. Because every candidate, agent output, leg, and even every slate-scoped product (via its legs, which always carry `game_id`) is reachable from a `game_id`, **populating `games.sport_id`/`league_id` at write time — an application-code change, not a migration — is sufficient to make sport identity recoverable at every stage of the pipeline, with zero new columns anywhere else.** This is a smaller, more precise finding than "add sport/league fields to the candidate/recommendation schema," and it directly satisfies HQ's instruction not to propose a migration until existing foreign keys are proven insufficient.

**A second correction to the prior pass**: this pass's own devil's-advocate review (Part 17) found that the 2026-09-09 report's recommendation to build two new fan-out LLM agents for News and Venue would likely **duplicate reasoning the already-real, already-deterministic Context Intelligence engine performs**, and would put an LLM in a loop where deterministic evidence-quality scoring already exists and works. The revised recommendation (§9-§10 below) is to wire Context Intelligence's existing news/venue dimensions directly into Probability Modeling — exactly the one-line integration point the engine's own docstring already names — rather than building new agents.

---

## 2. Actual Current Architecture (source-grounded)

Per-stage map, each row: file/module, real responsibility, inputs, outputs, invoked?, deterministic or AI, known limitation. Facts here are carried forward from the 2026-09-08/09 audits (re-verified against current source where this pass touched the same files) — not re-derived from scratch.

| Stage | File/Module | Responsibility | Inputs | Outputs | Invoked? | Det./AI | Limitation |
|---|---|---|---|---|---|---|---|
| API Gateway | `apps/api-gateway/app/recommendations.py` | Read-only serving of already-persisted rows | `since`/`until`/`limit`, `display_id` | Serialized cards | Yes (real user traffic) | Deterministic | No question/sport/team/player/market param anywhere |
| Auth | `apps/api-gateway/app/auth.py` | Verify Supabase JWT, confirm `user_profiles` exists | Bearer token | `CurrentUser(id,email)` | Yes | Deterministic | Never forwarded past api-gateway |
| Master Refresh | `apps/sports-intel-layer/app/master_refresh/run.py` | Schedule/roster fetch, DGI assembly | Provider schedule | `games`, `daily_game_intelligence` | Yes (cron) | Deterministic | Doesn't populate `games.sport_id`/`league_id` |
| Recommendation Worker (slate) | `apps/workers/app/recommendation_worker.py` | Find eligible games, invoke per-game cycle | `master_refresh_runs`, `games` | Per-game AI cycle calls | Yes (cron) | Deterministic | NFL-only by construction |
| `run_game_recommendation` | `apps/ai-orchestrator/app/orchestration/recommendation_worker.py` | Fan-out → candidates → per-candidate eval | `game_id` | Persisted legs/products | Yes | Mixed | No user in this loop at all |
| Fan-out agents (6/17) | `apps/ai-orchestrator/app/agents/{injury_intelligence,weather,travel_fatigue,rest_days,vegas_line,closing_line_movement}.py` | Qualitative reasoning over one evidence source each | `AgentContext` | `AgentOutput` (no `game_id` field — see §5) | Yes | AI (LLM) | 11 fan-out agents (all Matchup & Form) unbuilt |
| Probability Modeling | `apps/ai-orchestrator/app/agents/probability_modeling.py` | Model win probability from committee outputs | `candidate`, `upstream_findings` | `ProbabilityModelOutput` | Yes | AI (LLM) | No deterministic prior; no Context Intelligence input |
| Consensus | `apps/ai-orchestrator/app/features/consensus.py` | Weighted aggregation, Elite second-pass trigger | Fan-out outputs | Aggregate confidence | Yes | Deterministic | — |
| EV | `apps/ai-orchestrator/app/features/expected_value.py` | EV from modeled probability + odds | `p_model`, odds | `EVResult` (no `game_id` field) | Yes | Deterministic | — |
| Risk | `apps/ai-orchestrator/app/features/risk.py` | Outcome variance | `p_model` | `RiskAssessment` (`historical_bet_type_variance` permanently `None`) | Yes | Deterministic | Degraded by design, no real data yet |
| Strategy | `apps/ai-orchestrator/app/features/strategy.py` | Qualify/rank/resolve conflicts | `EvaluatedCandidate`s | Strategy decision | Yes | Deterministic | — |
| Explainability | `apps/ai-orchestrator/app/features/explainability.py` | Build why/risks/limitations | Consensus + agent outputs | Explanation rows | Yes | Deterministic | Different taxonomy than FACT/INFERENCE/MODEL-OUTPUT (§9) |
| Persistence | `apps/ai-orchestrator/app/persistence/recommendation_products.py` | Write products/legs | Strategy output | `recommendation_products`/`legs` | Yes | Deterministic | No sport/league column (recoverable via `game_id`, §5) |
| User retrieval | `apps/api-gateway/app/recommendations.py` | Serve to user | `display_id` or date window | Cards | Yes | Deterministic | Read-only, no computation trigger |

**MISSING INTERACTION PATH**: there is no stage between "API Gateway" and "Master Refresh" that a user request could enter through. The pipeline begins at Master Refresh's own cron trigger, not at any user action. A canonical request would need to enter at API Gateway, but today API Gateway has nothing to do with a request except serve already-computed rows.

---

## 3. Current Breakpoints

1. **No question-intake endpoint** (confirmed, both audits) — the single hard breakpoint.
2. **Context Intelligence is real and unwired** — a second, independent evidence-assembly path (`apps/ai-orchestrator/app/context_intelligence/engine.py`) computes real, deterministic, evidence-graded scores for weather/market/news/venue but is never called from the real recommendation cycle. Its own docstring names the exact wiring point; nothing has made that change.
3. **Sport/league identity is structurally solvable but currently unpopulated** — see §1's central finding and §5's matrix.
4. **11 of 17 fan-out agents don't exist** — the committee evaluates every candidate on roughly a third of its documented designed width.
5. **Player Props/Pregame/Postgame Ingestion Workers have real code and zero invocation wiring** — pure in-repo debt, no external blocker.

---

## 4. Existing Reusable Infrastructure

Explicitly not rediscovered as unknowns, per HQ's instruction — cited as available building blocks:

- **News**: real provider, real ingestion, real `news_article_history`, controlled recurring cadence, growing. Context Intelligence's `news.py` already queries it and computes a real, deterministic, timing-correlated evidence-quality score. **Reusable as-is** for wiring (§9).
- **Venues**: real canonical `venues` table, real stadium/coordinate/type identity, real weather-compatibility linkage (already flows into `TravelFatigueAgent` via `games.venue_lat/long`). Context Intelligence's `venue.py` already queries the dedicated table for cross-game comparability. **Reusable as-is** (§10).
- **Weather**: real WeatherAPI integration, real persisted rows, real recurring worker, correct dome handling. Not reopened.
- **Odds/Market**: real `odds_snapshots`, real `MarketCandidate`, real `game_id`/`market_type`/`final_aggregate_confidence`/`ev_per_dollar`. This is the substrate the minimum vertical slice (§14) is built entirely from.
- **Player identity**: real canonical identity, MySportsFeeds compatibility proven, real provider-ID mapping (Phase 8.2). Reusable the moment per-game data exists.
- **Roster/depth**: real partial data, append-only snapshots, incomplete coverage — a real but partial substrate, not a green light for full lineup-aware requests yet.
- **Player season stats**: real season-level stats retrieved and persisted-capable (Phase 8.3C/D); `gamesStarted` confirmed unreliable, disclosed, never trusted as participation evidence.
- **Gamelogs**: `_gamelogs` family CLOSED (Phase 8.4D, 4/4 real requests failed `400`). **Not reopened by this pass, and not referenced again below except as a closed fact.**
- **Per-game player data**: still blocked. Gate A (BALLDONTLIE billing) and Gate B (MySportsFeeds `game_boxscore` post-game validation) remain the tracked future gates (Volume 4 §8.6 v5.15, Phase 8.4E). Not touched by this pass.

---

## 5. Sport/League Propagation Matrix

Traced against real source, confirmed this pass (not carried forward unverified):

```
SPORT → LEAGUE → SEASON → GAME → MARKET → CANDIDATE → EVIDENCE → AGENT OUTPUT → MODEL → RECOMMENDATION LEG → RECOMMENDATION PRODUCT → USER RESPONSE
```

| Transition | Status | Exact reason |
|---|---|---|
| SPORT → LEAGUE → SEASON (schema) | **GREEN, at the schema level** | `sports`/`leagues`/`seasons` are real, correctly normalized, FK'd tables (`supabase/migrations/20260807211306_sports_data_tables.sql:20-56`) |
| SEASON → GAME | **RED, in application code, despite a GREEN schema path existing** | `games.sport_id`/`league_id`/`season_id` are real, nullable FK columns (same migration, lines 63-65) but confirmed **never written** by `apps/sports-intel-layer/app/persistence/schedule.py` or `master_refresh/*.py` (zero hits, this pass's own grep). `games.sport` is a hardcoded literal `'nfl'` (`schedule.py:111`). A real, working season-string *resolver* exists (`app/persistence/seasons.py`) but it computes a provider-request string scoped to a league the caller already knows — it does not populate `games.sport_id`/`league_id` as a side effect. |
| GAME → MARKET (candidate generation) | **YELLOW** | `MarketCandidate.game_id` is real and carried (`app/features/candidate.py:21-33`) — sport is recoverable by joining `game_id → games.sport_id`, but only once `games.sport_id` is populated (currently RED, see above); `MarketCandidate` itself has no sport field |
| MARKET/CANDIDATE → EVIDENCE (fan-out) | **YELLOW** | `AgentContext` is built per-game (`build_agent_context`) so evidence is implicitly game-scoped, but nothing in the evidence dict itself carries sport/league explicitly |
| EVIDENCE → AGENT OUTPUT | **YELLOW** | `AgentOutput` (`app/agents/contract.py:102-117`) has **no `game_id` field at all** — confirmed this pass by direct inspection. Identity is held only by the orchestration call stack (the fan-out cycle is invoked once per game), never carried on the object itself. Recoverable only by staying inside the same in-memory cycle, not by inspecting a persisted or passed-around `AgentOutput` alone. |
| AGENT OUTPUT → MODEL (Probability Modeling) | **YELLOW** | `ProbabilityModelOutput` carries `candidate_key` (derived from the candidate, which does carry `game_id`) but not `game_id` itself, and no sport field |
| MODEL → EV/RISK | **YELLOW** | `EVResult`/`RiskAssessment` (confirmed this pass, `app/features/expected_value.py:22-27`, `app/features/risk.py:25-28`) carry **no candidate/game identity fields at all** — purely numeric, associated only by the orchestration function's own local scope (`_evaluate_one_candidate`) |
| MODEL → RECOMMENDATION LEG | **GREEN** | `recommendation_legs.game_id uuid not null references games(id)` (`supabase/migrations/20260825120000_recommendation_products_schema.sql:131`) — **always present, even for slate-scoped products** — this is the load-bearing fact for the whole matrix: every leg, regardless of its parent product's scope, is joinable to `games.sport_id` once that column is populated |
| LEG → RECOMMENDATION PRODUCT | **YELLOW (game-scope) / RED-but-recoverable (slate-scope)** | Game-scoped products carry `game_id` directly (`recommendation_products.game_id`, same migration line 49) — YELLOW, recoverable via join. Slate-scoped products (`multiple_singles`/`bankroll_preservation`/`multi_game_parlay`) have **no `game_id` at all by design** (line 49's own comment) — but every one of their constituent legs still carries `game_id`, so sport eligibility is still recoverable, just one join further out (product → legs → games), never truly lost |
| PRODUCT → USER RESPONSE | **RED, at the presentation layer** | `apps/api-gateway/app/recommendations.py` never joins through to `games.sport_id`/`league_id` today (confirmed — its own `_read_game`/`_read_games_by_ids` select only `home_team,away_team,scheduled_start,status`) — even if `games.sport_id` were populated, the API layer would still need a small, additive change to actually surface it |

**Verdict, directly answering HQ's framing**: **no schema migration is required anywhere in this chain.** The existing `games.sport_id`/`league_id` FKs, combined with the fact that `recommendation_legs.game_id` is unconditionally present even for slate-scoped products, are structurally sufficient to guarantee every recommendation can be unambiguously scoped to a sport — once (a) `games.sport_id`/`league_id` are populated at Master Refresh write time (application code, not a migration), and (b) the API-gateway read path adds one additional join (application code, not a migration). This is a smaller footprint than the 2026-09-09 report's "add a sport/league field to `MarketCandidate`/`recommendation_products`/`recommendation_legs`" recommendation, which is **superseded by this finding** — those new columns are not needed.

---

## 6. Canonical Request Contract

**One canonical internal representation, three distinct stages, deliberately not collapsed:**

```
RAW USER INPUT           — exactly what arrived: a string, or a structured UI payload
      ↓ (normalization — different per input type, same output shape)
NORMALIZED REQUEST        — CanonicalMansaRequest, defined below
      ↓ (intent resolution — deterministic, §7)
RESOLVED INTENT           — the StructuredIntent object from the 2026-09-09 report, unchanged
      ↓ (scope + capability check, §10)
EXECUTION PLAN            — "retrieve this already-computed data" vs. "insufficient evidence" vs. "unsupported" — never a bare query string
```

**Why these stay separate, not collapsed**: `RAW USER INPUT` must be preserved verbatim (for audit/telemetry and because normalization is lossy); `NORMALIZED REQUEST` is the one shape both NL and structured-UI inputs converge to, but it doesn't yet know what the user *means* (a normalized request can still be ambiguous); `RESOLVED INTENT` is a specific, actionable classification, but knowing what someone wants isn't the same as knowing whether MANSA can honestly answer it — that's `EXECUTION PLAN`'s job, and it's where the Capability Check (§10) and insufficient-evidence disclosure live. Collapsing any two of these would either lose the audit trail, force premature commitment to an interpretation, or let an unsupported request silently produce a misleading answer — three real, distinct failure modes this separation exists to prevent.

**Proposed `CanonicalMansaRequest` fields:**

| Field | Belongs? | Exists elsewhere? | Required/optional | User input or system-resolved? | Multi-sport ready? |
|---|---|---|---|---|---|
| `requestType` | Yes — every downstream stage needs it | No (new) | Required (resolved, may be `unresolved`) | System-resolved (§7) | Yes — sport-agnostic vocabulary |
| `rawText` | Yes — audit/reconstruction | No (new) | Required | User input | N/A |
| `sport` | Yes — §5's entire finding depends on this being real | Schema exists (`sports`), unpopulated downstream | Optional (explicit only, never guessed) | User input (explicit) or system-default (today: trivially NFL) | Yes, by design |
| `league` | Yes, structurally, but **not yet meaningfully distinct from sport with only NFL live** | Schema exists (`leagues`) | Optional | User input | Reserved for future (e.g. NCAA vs NFL under American football) |
| `season` | **Not needed for the beta contract** | Real, used internally (`seasons.py`) for provider requests | N/A for user-facing beta | — | Defer — today's slate is always "current season," no user-facing need yet |
| `date` | Yes — already a real, working filter (`since`/`until`) | Yes, exists | Optional, defaults to today | User input | Sport-agnostic |
| `gameId` | Yes — real, already the primary join key everywhere | Yes, exists | Optional | User input (via team/game name) or system-resolved | Sport-agnostic |
| `teamName` | Yes, for `team_specific` requests | Partially (string match only, §5's YELLOW case) | Optional | User input | Needs disambiguation once two sports share a city name |
| `playerName` | **Reserved, not usable yet** | No real substrate to match against (Phase 8 gate) | Optional, always resolves to `insufficient_evidence` until Phase 8 data exists | User input | Yes, once real |
| `marketType` | Yes — real, direct column | Yes, exists | Optional | User input | Sport-agnostic |
| `recommendationStyle` | Yes — this is `requestType`'s scope companion (safest/highest_value/etc.) | No (new) | Optional, defaults to `best_overall`'s eventual definition | User input | Sport-agnostic |
| `n` (count) | Yes, for "top 3" style requests | No (new) | Optional, default 1 | User input | Sport-agnostic |
| `crossSportPreference` | Yes — needed the moment a second sport exists | No (new) | Optional, `null` until multi-sport is real | User input (explicit) or system default | Exists specifically for multi-sport |
| `explanationDepth` | **Not needed for the beta contract** | No | Defer — every response already gets the full existing explanation payload; no product reason yet to offer a "shorter" version | — | Defer |

**Do not automatically add every field** — `season` and `explanationDepth` are explicitly deferred above, not because they're wrong ideas, but because nothing in the current product needs them yet and adding unused fields to a contract this early risks exactly the "add sport everywhere" over-design HQ's own framing warns against.

**How NL and structured UI converge**: both produce the same `CanonicalMansaRequest`. Structured UI input skips normalization almost entirely (a dropdown selection for `sport`/`recommendationStyle` maps directly to the field); NL input goes through the deterministic normalization + intent-resolution layer (§7) to arrive at the identical shape. **Neither path is privileged** — the contract, not the input method, is canonical.

---

## 7. Intent-Resolution Design

**A deterministic rule-based layer is sufficient for the first beta**, matching the project's own "never delegate to an LLM what deterministic code can reliably do" principle (already applied identically to `app.features.market`/`grading`/`consensus`).

**Requests deterministic rules can resolve safely** (keyword/pattern match against a small, known vocabulary): safest, highest value, today's picks, best NFL pick (sport keyword + generic "best"), three picks (numeral/word-to-`n` extraction), game-specific (a recognized team name pair present in today's real slate), team-specific (a single recognized team name present). All of these map directly to an already-real column ordering (§2/§5 of the 2026-09-09 report) — the resolver's job is purely pattern recognition, not judgment.

**Requests requiring clarification**: "best pick" alone (ambiguous — confidence? EV? a blended score not yet defined, per the 2026-09-09 report's own finding), "conservative"/"aggressive" (no defined band exists yet — this is a product decision, not a resolvable pattern until one is made), a team name that matches no team in today's real slate (bye week, or a misheard/mistyped name).

**Requests that should be rejected as unsupported**, honestly, not silently degraded: player-specific requests (no real per-game substrate, §4), any parlay-probability request beyond "show me independent legs" (§8/§12), cross-sport requests today (there is no second sport to be cross with — this should say so plainly, not silently narrow to NFL as if that were the answer to a genuinely cross-sport question).

**Future requests that might require an LLM**: anything genuinely open-ended or requiring synthesis across multiple qualitative factors the deterministic vocabulary can't enumerate in advance (e.g., "why do you like this pick more than that one" as a live, adaptive follow-up conversation) — explicitly **not** needed for the beta vertical slice, and not designed further here.

**How ambiguity should be handled**: the resolver returns `requestType: "unresolved"` with a populated `unresolvedReason`, and the API layer returns that reason honestly to the user rather than guessing — this is the same "insufficient evidence, never a lower-confidence guess dressed up as an answer" principle already locked elsewhere in this codebase (Context Intelligence's `unsupported.py`), applied here to intent itself rather than evidence.

**Explicit answer to HQ's warning**: an LLM is **not** the default router simply because input is natural language — the resolver above handles the full beta vocabulary deterministically; an LLM is not proposed anywhere in this pass's design.

---

## 8. Multi-Sport Request Behavior

Per HQ's explicit rules, restated and mapped onto `CanonicalMansaRequest.sport`/`crossSportPreference`:

- **Explicit single sport** ("best NFL pick today") → `sport="nfl"` set directly, `crossSportPreference=null` — no follow-up question, ever, for this case.
- **Explicit cross-sport** ("best picks across sports") → `sport=null`, `crossSportPreference="explicit"` — the system must not narrow to one sport once real multi-sport data exists.
- **Ambiguous** ("what's the best pick today?") — **recommended beta policy: (D) return the strongest eligible result while clearly identifying scope**, not (C) ask for clarification. Reasoning: today this is moot (trivially NFL, nothing to ask about); once a second sport exists, defaulting to "search all eligible sports, but label every result's sport explicitly" (option A, combined with D's labeling discipline) preserves the honest-disclosure principle this whole pass is built around, without forcing a clarifying round-trip for what is, in the common case, still probably a single-sport-dominant product. **This is a real product decision for HQ to confirm, not unilaterally finalized here** — recorded explicitly in §20.
- **Scaling**: because `sport`/`crossSportPreference` are already first-class fields in the contract (§6), and because §5 proved the existing schema/FK structure is sufficient once populated, **adding NBA later requires no redesign of the request system itself** — only (a) a second provider-adapter instance (already the established one-constant-per-file pattern), (b) populating `games.sport_id` for NBA games the same way NFL games would need it populated, and (c) the ambiguous-case policy decision above actually mattering for the first time.

---

## 9. News Intelligence Placement

Evaluated against the four options, per HQ's explicit criteria:

| Option | Architectural fit | Committee independence | Duplicate-reasoning risk | LLM cost | Latency | Provenance | Freshness | Multi-sport | Phase 4 |
|---|---|---|---|---|---|---|---|---|---|
| A. Dedicated News Agent (new LLM fan-out agent) | Matches the existing 1-source-per-agent pattern structurally | Yes, independent | **High** — would re-derive what Context Intelligence's `news.py` already computes deterministically (timing correlation with real market movement) | New, recurring LLM cost per game per cycle | New | New provenance path to maintain | Already real (4h cadence) | Needs its own sport-scoping | New file, additive, but functionally redundant |
| B. Existing agent directly consumes News evidence | Cheap to wire | No — blurs an existing agent's single-source scope | Moderate — an existing agent (e.g. Injury Intelligence) would now reason over two unrelated evidence types in one LLM call, muddying its own `EvidenceClassification` output | No new agent, but heavier existing calls | Slightly higher per existing call | Provenance harder to attribute to the right source once merged | Same | Same blurring problem compounds across sports | Touches an existing, working agent |
| **C. Context Intelligence produces structured News context upstream (already built)** | **Best fit — this is precisely what already exists** | N/A — not a committee member, a pre-computed deterministic signal, same relationship `app/features/market.py` already has to `ClosingLineMovementAgent` | **None** — this IS the deterministic computation; building A/B on top of it would be the duplication | **Zero new LLM cost** — `news.py`'s scoring is fully deterministic | Zero new latency (already computed, just unread) | Real, already-typed (`ProvenanceRef`) | Already real | Already sport-agnostic (queries by team, not by hardcoded sport) | **The one-line change the engine's own docstring already names** — additive to `ProbabilityModelingAgent.build_evidence`, touches no other Phase 4 file |
| D. Deterministic retrieval attached directly at recommendation assembly (citation only, no reasoning) | Cheapest, but discards the evidence-quality scoring Context Intelligence already computes | N/A | None | None | None | Simple | Real | Sport-agnostic | None — but throws away real, working computation for no reason |

**Recommendation: Option C.** Context Intelligence already **is** the correct architectural home for News — it was built for exactly this purpose, and its own docstring already specifies the wiring point. Building a new dedicated LLM agent (A) would genuinely duplicate reasoning Context Intelligence already performs deterministically, and would introduce an LLM call where one isn't needed — directly the failure mode HQ's devil's-advocate framing (Part 17 item 9) warns against. **This corrects the 2026-09-09 report's own recommendation to build a new `news_agent.py`** — that recommendation is withdrawn in favor of wiring the existing engine.

**FACT vs. INFERENCE, defined for News specifically**: FACT = what the article's own text states directly and verifiably ("Player X was officially listed as questionable" — a status change `news_article_history` genuinely captures). INFERENCE = a conclusion drawn from that fact ("Player X's availability may reduce offensive production" — this is never something the article itself asserts, and must never be presented as though it were). **Context Intelligence's `news.py` already respects this boundary structurally** — it never interprets article content, only correlates real article timing against real market-movement timing, and reports a similarity/confidence score with `insufficient_evidence` when the correlation is too weak to support a claim. It does not, and per this option should not, generate the INFERENCE step itself — that remains Probability Modeling's (or a future dedicated reasoning layer's) job, fed by Context Intelligence's FACT-adjacent timing signal, not conflated with it.

---

## 10. Venue Intelligence Placement

Same four-option evaluation, condensed since the finding is simpler:

**Static facts** (stadium identity, coordinates, venue type) are **already correctly retrieved as plain context**, not reasoned over — this is exactly right and needs no agent of any kind (Option D, for this narrow layer). **Deterministic context** (dome status affecting weather relevance) is **already wired** — `TravelFatigueAgent` already consumes `games.venue_lat/long` for travel/timezone computation, and `WeatherAgent`'s own dome-handling logic (confirmed real, not reopened per HQ's instruction) already uses venue type correctly. **Analytical inference** (whether environmental conditions at this venue historically affect a specific market) is exactly Context Intelligence's `venue.py` dimension — a real, deterministic, evidence-graded similarity score (binary same-venue match today, explicitly not a fabricated distance metric per its own code).

**Does Venue need a dedicated intelligence agent at all? No.** Unlike News (which involves genuinely discrete, non-deterministic real-world events), Venue's own "intelligence" ceiling is a similarity/comparability score over structured, already-fully-known facts — there is no unstructured content to interpret the way a news article has. **Recommendation: Option C for the comparability dimension (wire `venue.py`'s existing output the same way as News, §9), Option D (plain retrieval, already working) for everything else.** No new agent, dedicated or otherwise, is justified for Venue.

---

## 11. Weather / Venue / News Interaction Model

**Recommended architecture: one combined contextual evidence package, computed once, upstream of both the existing fan-out committee and Probability Modeling — exactly what `ContextualIntelligenceResult` already is** (`apps/ai-orchestrator/app/context_intelligence/models.py`, real, already covers all four supported dimensions plus six honest stubs in one object per game). This avoids double-counting by construction: Venue tells the system whether weather is relevant (already true — dome/outdoor classification feeds both `WeatherAgent`'s dome-handling and Context Intelligence's own weather bucketing, from the same source field, `games.venue_type`); Weather provides the observed/forecast condition itself (already flowing to `WeatherAgent` via DGI, and separately to Context Intelligence's `weather.py`); News provides external developments (§9). **The existing fan-out agents and Context Intelligence already avoid re-deriving each other's facts** — they read from the same underlying tables (`weather_snapshots`, `games`) via different code paths for different purposes (qualitative "what does this mean" vs. quantitative "how much evidence supports comparing this to history"). The one real risk (not yet materialized, but worth naming): if a future News/Venue *agent* (Option A/B, §9/§10) were built anyway, it would need to explicitly NOT re-score what Context Intelligence already scores — this is exactly why this pass recommends Option C over A/B, removing the risk at its source rather than managing it after the fact.

---

## 12. Explanation and Provenance Architecture

**Current infrastructure, confirmed (carried forward, not re-derived)**: `EvidenceClassification` (`data_backed|inference|assumption`, agent-output layer, real, drives Consensus's own weight-halving for `assumption`-classified outputs) and Context Intelligence's `insufficient_evidence` (real, per-dimension, never fabricates a confidence number).

**MODEL OUTPUT — do these categories overlap, and should this be a real, distinct category?** Yes, distinct, and it does not cleanly overlap with the other three: a `modeled_probability` from Probability Modeling is neither a FACT (it wasn't observed), an INFERENCE in the "we derived this from disclosed evidence" sense the existing taxonomy means (it's an LLM judgment, not a traced logical derivation a reader could independently verify step by step), nor an ASSUMPTION (it's not something the system is presupposing for lack of better information — it's the system's own computed output). **Recommendation: yes, add MODEL OUTPUT as a real, fourth category, not merely because the name sounds right, but because none of the existing three can honestly describe what a modeled probability is.**

**Can one statement depend on multiple categories?** Yes, necessarily — a single recommendation's explanation legitimately contains a FACT ("the spread moved 1.5 points"), an INFERENCE drawn from it and other evidence ("this suggests sharp money on the away team"), a MODEL OUTPUT ("MANSA's model estimates a 58% win probability"), and possibly an INSUFFICIENT EVIDENCE disclosure in the same breath ("historical comparable-weather performance data doesn't exist for this player yet"). **The architecture must support per-statement tagging within one explanation, not one tag per whole recommendation** — a single coarse label would either force everything down to the least-certain category (useless) or let a MODEL OUTPUT hide inside a block labeled FACT (exactly the failure mode HQ is guarding against).

**Where should provenance live? The recommendation-explanation layer — `recommendation_product_explanations`/`recommendation_leg_explanations` — is the correct owner**, per the same reasoning the 2026-09-09 report already reached: this is already where `why_selected`/`strongest_evidence`/`biggest_risks`/`data_limitations` live, already persisted, already reconstructable via Time Machine. Extending it with per-statement or per-field category tags is a natural continuation of an existing table's existing purpose, not a new architectural layer.

**How this prevents a model prediction from being presented as a fact**: by construction, once MODEL OUTPUT exists as its own category and the explanation layer enforces per-statement tagging, `modeled_probability` can never be rendered without its own label — the same discipline `EvidenceClassification`'s `assumption` tag and Context Intelligence's `insufficient_evidence` flag already enforce for their own categories today, just extended to a category that currently has no home.

**Multi-sport compatibility**: none of this taxonomy is sport-specific — it classifies the *epistemic status* of a statement, not its subject matter, so it needs no changes for a second sport.

---

## 13. Capability-Check Architecture

**Design (not built)**: a small, deterministic function, `check_capability(intent: StructuredIntent) -> CapabilityResult`, evaluated **after scope resolution, before retrieval** — checking capability against an unscoped intent would produce false negatives (e.g. rejecting "safest pick" before knowing which sport/date narrows it to zero eligible candidates vs. many).

```
CapabilityResult = SUPPORTED | PARTIALLY_SUPPORTED | INSUFFICIENT_EVIDENCE | UNSUPPORTED
```

- **SUPPORTED**: "highest-confidence NFL recommendation today" — maps directly to a real column, real data exists for today's real slate.
- **PARTIALLY_SUPPORTED**: "How has Hunter Henry performed recently?" — real season-level stats exist (Phase 8.3C), so a partial, explicitly-scoped answer ("season totals only, not per-game") is honest and possible.
- **INSUFFICIENT_EVIDENCE**: "How does Hunter Henry perform against this opponent in bad weather?" — real per-game historical substrate doesn't exist (the exact gap the Context Assembly Proof, Volume 4 §8.6 v5.15, already names and gates), so this must resolve here, not attempt a degraded answer.
- **UNSUPPORTED**: a request type the resolver can't classify at all, or one explicitly out of scope by product decision (e.g. joint parlay probability, §8/§14).

**Interaction with the existing insufficient-evidence system**: this layer **reuses**, not replaces, Context Intelligence's own `insufficient_evidence`/`ContextualDimensionResult` mechanism and the Context Assembly Proof's own JOINED/PARTIAL/UNAVAILABLE vocabulary — a capability check for anything context-dependent should literally call into that existing machinery rather than inventing a parallel one.

**Should capability checks be deterministic? Yes, always** — the entire point of this layer is to prevent MANSA from manufacturing completeness; an LLM-based capability check would reintroduce exactly the risk (a plausible-sounding but ungrounded "yes, I can answer that") this layer exists to prevent.

---

## 14. Minimum Honest Beta Vertical Slice

Critically evaluated, not blindly approved, per HQ's instruction:

1. **What "safest" means in Beta**: the single active `recommendation_leg` with the highest `final_aggregate_confidence` among today's qualified products. **This must be named precisely, not left ambiguous.**
2. **Which column(s) support it**: `recommendation_legs.final_aggregate_confidence` — real, already computed, already the exact ordering `recommendations.py` documents as its own governing principle (no fabricated "primary"/"best" field exists — confirmed, `recommendations.py:34-41`).
3. **Evidence limitations that remain**: the underlying confidence comes from a committee running at 6/17 fan-out width, with News/Venue unwired (§9/§10) and Context Intelligence entirely unconsulted (§4) — "safest" is MANSA's own honest confidence given its current, narrower evidence base, not a claim about objective betting risk.
4. **What must be disclosed**: exactly the limitation in #3, in plain language, every time — not a one-time disclaimer buried in a help page.
5. **Can it be produced without triggering new intelligence computation? Yes** — this is purely a retrieval-and-ordering operation over already-persisted rows, zero new LLM calls, zero new provider calls, zero new computation.
6. **Should it retrieve a precomputed recommendation product? Yes, exactly that** — no on-demand computation is proposed or needed for this slice.
7. **Behavior when nothing qualifies**: return the existing, already-real "No Bet Today"/bankroll-preservation signal honestly — this already exists as a first-class product type and needs no new design.

**The critical terminology distinction, addressed directly**: **"Highest available MANSA aggregate confidence" is not the same claim as "objectively safest betting outcome," and the product must never conflate the two.** Recommended internal terminology: `SAFEST_BY_MANSA_CONFIDENCE` (or equivalent internal constant name) — never a bare `SAFEST`. Recommended user-facing terminology: something like *"MANSA's highest-confidence pick today"* rather than *"the safest bet"* — the former is a true, verifiable claim about MANSA's own output; the latter implies an objective property of the wager itself that MANSA cannot honestly claim given the evidence limitations in #3. **This is the single most important terminology decision in this entire report** — getting it wrong would mean the very first thing a beta user sees misrepresents what MANSA actually knows.

**Verdict**: this vertical slice, with the terminology correction above and the disclosure in #4, is honest, deterministic, built entirely on real existing data, low-risk, fully reversible (a read-only endpoint), and useful. **Approved as designed, with the terminology correction as a hard requirement, not a suggestion.**

---

## 15. Request-Type Progression (grounded in the real codebase, not an idealized level scheme)

| Level | Request shape | Status |
|---|---|---|
| 1 | Precomputed retrieval by date (existing `/today` behavior) | **READY NOW** |
| 2 | Filtered retrieval: safest, highest-value, market-specific, top-N | **NEEDS IMPLEMENTATION** (§14 — new endpoint + intent resolver only, no schema/data change) |
| 3 | Game/team-scoped retrieval | **NEEDS IMPLEMENTATION** (string-match team resolution, §5/§7 — works today for NFL, improves once `games.sport_id`/canonical team-ID join lands) |
| 4 | Sport/league-explicit and cross-sport-aware retrieval | **NEEDS IMPLEMENTATION**, gated on populating `games.sport_id`/`league_id` (§5) — no migration, but real application code |
| 5 | Evidence-aware contextual answers (News/Venue/Weather-informed) | **NEEDS IMPLEMENTATION**, gated on Context Intelligence wiring (§9/§10/§11) — code exists, wiring doesn't |
| 6 | Player-specific requests | **BLOCKED ON PHASE 8 DATA** — no real per-game player substrate exists (Context Assembly Proof's own Readiness Matrix) |
| 7 | Parlay with real joint/correlated probability | **BLOCKED ON PHASE 8 DATA** (needs real per-game correlation evidence) **and its own distinct future capability**, not merely blocked-then-ready |
| 8 | Genuinely on-demand intelligence computation (new candidate evaluation triggered live by a user request, not pre-computed) | **BLOCKED ON PHASE 4 AUTHORIZATION** — this would mean invoking the committee/Probability Modeling outside the existing cron cycle, a real architectural change to when/how those systems run, requiring its own explicit authorization regardless of data readiness |
| 9 | Second-sport (NBA) requests | **BLOCKED ON HUMAN/PROVIDER ACTION** — new adapter credentials/entitlement, a business decision outside this audit's scope |

---

## 16. Ingestion Worker Reassessment

Per-worker, going beyond "is it wired" (already established, §3) into "would activation actually help":

**Player Props Ingestion Worker**: inputs = odds-provider prop feeds (same provider infrastructure as Odds Worker, already proven live); provider dependency = same credential already in use for Odds Worker, no new one; persistence = writes `odds_snapshots` with `market_type='prop'`, real and tested; idempotency = inherits the same append-only pattern as Odds Worker; tests = exist (confirmed real cadence-mirroring logic in the prior audit). **Would activation create meaningful new substrate?** Yes, directly — but request-level demand for prop-based requests doesn't exist yet in the beta contract (§6 defers `playerName`), so activating it now would create real data with no current consumer. **Belongs after the beta vertical slice**, once player-specific requests (Level 6, §15) are closer to unblocked.

**Pregame Ingestion Worker**: inputs = coordinates Odds/Player Props/Injury/Weather at T-minus-5; no new provider dependency; persistence = triggers the existing `daily_game_intelligence` refresh path, already real and tested elsewhere. **Would activation help the vertical slice?** Marginally — DGI is already refreshed by Master Refresh; Pregame Worker's value is a tighter, closer-to-kickoff refresh, a freshness improvement, not a new capability. **Belongs after the beta vertical slice**, as a quality improvement, not a blocker for it.

**Postgame Ingestion Worker**: inputs = provider post-game payload (SportsDataIO, already-authorized/reserved credential per this project's own established discipline); persistence = writes `team_stats`/`player_stats`, currently fixture-only precisely because this worker never runs; idempotency = confirmed insert-if-changed, not append-only (a known, disclosed, pre-existing gap, unrelated to activation itself). **Would activation create meaningful new substrate? Yes, significantly** — this is the one worker whose activation would directly start closing the real per-game player/team data gap the Context Assembly Proof is waiting on (though it alone isn't sufficient — Gate A/Gate B's own external provider questions remain separate). **Cost/quota**: uses the already-reserved, already-authorized SportsDataIO allowance per prior sessions' own tracked discipline — this pass does not re-authorize spending it, only notes that this worker is the one most directly relevant to unblocking Phase 8 data once separately authorized. **Sequencing**: this worker's activation is closer to the Phase 8 data-gate track than to the beta-interaction-loop track this pass is scoped to — **flagged as a high-value future activation, not sequenced into this pass's own implementation order** (§17), since HQ's guardrails here explicitly prohibit worker activation regardless.

---

## 17. Final Canonical Request-to-Answer Architecture Map

```
USER
 ↓
INPUT NORMALIZATION                    — NEEDS NEW CODE (small; NL keyword pass + structured-UI passthrough, §6/§7)
 ↓
CANONICAL REQUEST                      — NEEDS NEW CODE (the CanonicalMansaRequest shape itself, §6)
 ↓
INTENT RESOLUTION                      — NEEDS NEW CODE (deterministic resolver, §7 — no LLM)
 ↓
SCOPE RESOLUTION                       — NEEDS NEW CODE (small; resolves sport/game/team against today's real slate)
 ↓
CAPABILITY CHECK                       — NEEDS NEW CODE (§13; reuses EXISTING Context Intelligence insufficient_evidence machinery)
 ↓
RETRIEVAL / COMPUTATION DECISION       — NEEDS NEW CODE (small; for beta, always resolves to "retrieval," never "computation" — Level 8 in §15 is BLOCKED)
 ↓
EXISTING DATA / RECOMMENDATION RETRIEVAL — EXISTS NOW (recommendations.py's own read/join/serialize logic, §2)
 ↓
INTELLIGENCE PROCESSING WHEN ACTUALLY REQUIRED — EXISTS NOW but NEEDS WIRING (Context Intelligence engine is real; the "when actually required" branch for the beta slice never triggers it — §9/§10 wiring is a distinct, separate future pass from the beta loop itself)
 ↓
ANSWER ASSEMBLY                        — EXISTS NOW (existing card serialization, reused verbatim)
 ↓
EXPLANATION / PROVENANCE               — EXISTS NOW, NEEDS NEW CODE for MODEL OUTPUT category (§12; the table and 3 of 4 categories are real, the 4th is a real gap)
 ↓
USER RESPONSE
```

**Not idealized** — every "EXISTS NOW" above cites a real file already confirmed in this or the prior two audits; every "NEEDS NEW CODE" is scoped to what §6-§13 actually designed, not a wishlist.

---

## 18. Implementation Sequence

Each pass: purpose, existing code reused, new code required, schema impact, phase dependencies, provider impact, reversibility, test strategy, acceptance criteria.

### Pass 1 — Question-Intake + Deterministic "Safest" Slice
- **Purpose**: close the single hard breakpoint (§3.1) with the minimum honest slice (§14).
- **Reuses**: `get_current_user`, existing card-serialization logic, existing `final_aggregate_confidence` ordering.
- **New code**: `POST /v1/recommendations/ask` route; `CanonicalMansaRequest` model; a minimal intent resolver handling only `safest`/`unresolved`.
- **Schema impact**: none.
- **Phase dependencies**: none — entirely within api-gateway + existing recommendation reads.
- **Provider impact**: none — zero new calls of any kind.
- **Reversibility**: fully — a new, additive read-only route.
- **Test strategy**: unit tests on the resolver's pattern matching; integration test confirming the endpoint returns the same row `/today`'s own ordering-by-confidence would produce.
- **Acceptance criteria**: a real request for "what's the safest NFL pick today" returns MANSA's real highest-confidence active leg for today, correctly labeled per §14's terminology requirement, or an honest "nothing qualified today" response.

### Pass 2 — Extend Intent Vocabulary (highest-value, market-specific, top-N, game/team-specific)
- **Reuses**: Pass 1's endpoint/resolver skeleton.
- **New code**: additional deterministic pattern branches (§7); team-name matching against today's real slate.
- **Schema impact**: none.
- **Phase dependencies**: none.
- **Provider impact**: none.
- **Reversibility**: fully.
- **Test strategy**: one test per new request type, each asserting the correct existing column/ordering is used.
- **Acceptance criteria**: all Level-2/3 request types from §15 resolve correctly against real today-data.

### Pass 3 — Populate `games.sport_id`/`league_id` + Surface Sport in Responses
- **Reuses**: existing `sports`/`leagues` tables, existing `seasons.py` resolver pattern as a model.
- **New code**: a small addition to Master Refresh's schedule-persistence path to resolve and write `sport_id`/`league_id` (currently hardcoded `'nfl'` literal becomes a real lookup); a join in `recommendations.py`'s read path to surface it.
- **Schema impact**: **none** — §5's own central finding; the columns already exist.
- **Phase dependencies**: none (Phase 3-adjacent code, not Phase 4/5).
- **Provider impact**: none.
- **Reversibility**: fully — populating a previously-null column is additive and non-destructive.
- **Test strategy**: confirm every newly-persisted game carries the correct `sport_id`/`league_id`; confirm the API response surfaces it.
- **Acceptance criteria**: a real `recommendation_products` row, retrieved via the API, unambiguously identifies its sport — the structural precondition for Level 4 (§15).

### Pass 4 — Wire Context Intelligence into Probability Modeling (News/Venue/Weather/Market dimensions)
- **Reuses**: the entire existing, real `context_intelligence` engine — zero new evidence-computation code.
- **New code**: the one-line addition the engine's own docstring already names, inside `ProbabilityModelingAgent.build_evidence`.
- **Schema impact**: none.
- **Phase dependencies**: **touches Phase 4** (`app/agents/probability_modeling.py`) — requires its own explicit authorization per HQ's standing guardrails, separate from this pass's own "zero Phase 4 changes" scope. **Not sequenced to begin without that separate authorization.**
- **Provider impact**: none — the data is already real and already flowing.
- **Reversibility**: additive to the evidence dict; fully reversible by removing the one field.
- **Test strategy**: confirm `ProbabilityModelingAgent`'s prompt/evidence now includes the contextual signal; confirm behavior when Context Intelligence itself returns `insufficient_evidence` for a dimension (must degrade honestly, never fabricate).
- **Acceptance criteria**: a real recommendation's explanation can trace a News/Venue/Weather/Market-derived signal back to Context Intelligence's own real computation.

### Pass 5 — MODEL OUTPUT Explanation Category
- **Reuses**: existing `recommendation_product_explanations`/`recommendation_leg_explanations` table and write path.
- **New code**: a new field/tagging mechanism on that table (§12).
- **Schema impact**: additive column(s) on an existing table — a real, small migration.
- **Phase dependencies**: touches Explainability (Phase 5-adjacent), not Phase 4 itself.
- **Provider impact**: none.
- **Reversibility**: additive column, fully reversible.
- **Test strategy**: confirm a `modeled_probability`-derived statement is tagged MODEL OUTPUT and never FACT.
- **Acceptance criteria**: every existing explanation field can be traced to exactly one of FACT/INFERENCE/ASSUMPTION/MODEL OUTPUT/INSUFFICIENT EVIDENCE.

**Explicit note on sequencing discipline**: Pass 4 and Pass 5 are named and scoped here, per HQ's request for the full sequence, but **neither is authorized to begin by this pass** — both cross into Phase 4/Explainability territory this pass's own guardrails (and HQ's standing Phase 4/Milestone 5.6 protections) reserve for separate, explicit authorization. Passes 1-3 are the actually-sequenced, immediately-actionable beta-interaction-loop work.

---

## 19. Devil's-Advocate Findings

1. **Are we building a natural-language interface when structured UI would solve the beta problem more simply?** Partially valid — the deterministic resolver (§7) is small enough that a structured-UI-only beta (dropdowns for sport/style/date) would indeed be simpler to ship first and would exercise the identical `CanonicalMansaRequest`/retrieval path. **Recommendation: the canonical contract and Pass 1-2 backend work should ship first, UI-agnostic; whether the first beta UI is NL, structured, or both is a separate, cheaper decision that doesn't change any backend work above.**
2. **Are we creating new agents where deterministic retrieval is better?** Yes, this was the 2026-09-09 report's own mistake for News/Venue, corrected in §9/§10 above.
3. **Are News and Venue agents truly independent intelligence or merely duplicate context?** Answered directly by #2's correction — they would have been duplicates; the corrected recommendation avoids building them.
4. **Are we prematurely changing schema fields that existing foreign keys already solve?** This was actively checked (§5) and the answer is **yes, the prior report's proposed new columns are unnecessary** — corrected in §1/§5/§18 Pass 3.
5. **Are we calling something "safe" that is merely "high confidence"?** Directly addressed in §14 — yes, this was a real risk, and the terminology correction there is the fix.
6. **Are we allowing model outputs to masquerade as facts?** Not currently prevented — this is precisely why §12 recommends adding MODEL OUTPUT as its own category rather than leaving it unnamed.
7. **Are we creating a multi-sport architecture before a second sport exists, or preserving identity boundaries for future scaling?** The latter — §6/§8's design adds fields the contract needs regardless of when NBA arrives (sport/crossSportPreference), but Pass 3 (§18) only populates what NFL already needs; no NBA-specific code is proposed anywhere in this pass.
8. **Are we accidentally crossing into Phase 4?** Passes 1-3 do not. Pass 4 explicitly does, and is explicitly flagged as needing separate authorization rather than silently bundled into "the sequence."
9. **Are we duplicating Context Intelligence functionality?** This was the central catch of this review (§9/§10) — the original News/Venue-agent idea would have; the corrected recommendation eliminates the duplication at its source.
10. **What is the smallest possible implementation that creates a real user → MANSA → answer loop?** Pass 1 alone (§18) — a single new endpoint, a single-request-type resolver, zero schema change, zero Phase 4 touch, built entirely on data and computation that already exists.

**This recommendation survives its own scrutiny because every design decision above changed in response to one of these ten questions, not despite them** — the sport/league schema recommendation shrank, the News/Venue agent recommendation was reversed, and the implementation sequence was explicitly split at the Phase 4 boundary rather than presented as one undifferentiated list.

---

## 20. Explicit Decisions Required from Mac/HQ

1. **Ambiguous cross-sport request policy** (§8): confirm "return the strongest eligible result, clearly labeled" as the beta default, vs. asking a clarifying question — not finalized here, a real product call.
2. **"Best overall"/"conservative"/"aggressive" definitions** (§7, carried from the 2026-09-09 report, still open): what confidence/EV band each maps to — needed before Level 2 (§15) can fully cover the original 12 example questions, though the "safest"/"highest value" subset (Pass 1-2) doesn't need this decision first.
3. **User-facing terminology for "safest"** (§14): explicit sign-off on *"MANSA's highest-confidence pick"* (or equivalent) over *"the safest bet"* — flagged as the single most important wording decision in this report.
4. **Pass 4 authorization** (§18): wiring Context Intelligence into Probability Modeling touches Phase 4 and needs its own explicit go-ahead, separate from and after this pass.
5. **Pass 5 authorization** (§18): the MODEL OUTPUT explanation-schema addition is a real (small) migration and needs its own authorization.
6. **Postgame Ingestion Worker activation timing** (§16): flagged as high-value for closing the Phase 8 data gap, but explicitly not sequenced or authorized by this pass — HQ to decide when to fold it into the Phase 8 data-gate track.
7. **Whether the first beta UI is NL, structured, or both** (§19 item 1) — a UI-layer decision independent of the backend sequence above.

---

## What was and wasn't done this pass

Pure read-only audit and architecture design, grounded in direct source citation (this pass's own fresh verification of `games`/`recommendation_products`/`recommendation_legs`/`AgentOutput`/`EVResult`/`RiskAssessment` schema, plus the two prior accepted audits for everything not re-verified). **Zero provider calls, zero purchases, zero credential changes, zero worker activation, zero cron changes, zero schema changes, zero migrations, zero ingestion implementation, zero contextual scoring changes, zero recommendation-logic changes, zero Phase 4 changes, zero Milestone 5.6 changes, zero Phase 7 observation changes, zero Phase 8 implementation changes, zero staging/production changes.** No roadmap contradiction was discovered — the roadmap's own Phase 8 Context Assembly Proof gate (Volume 4 §8.6 v5.15) remains fully consistent with every finding in this report; the roadmap was not touched.
