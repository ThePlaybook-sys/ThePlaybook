# The Playbook — Volume 4
## AI Intelligence Architecture: Agents, Orchestration, Consensus, Explainability, Learning

**Version:** v5.14
**Last updated:** 2026-09-04

**v5.14 note (MINOR, HQ authorization, real code):** §8.5's detection half is now built — Milestone 7.1 (Deterministic Unexplained-Movement Detection Engine), authorized and completed the same day. Full detail in §8.5's own updated status line and the Engineering Roadmap's Milestone 7.1 entry. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v5.13 note (MINOR, HQ Decision Lock, planning only):** §9.7's proposed design is now LOCKED by HQ, all seven items approved in one pass the same day — see the section's own restated seven-item recap and Volume 3 §5G's matching "HQ Decision Lock" subsection for the full text. Highlights: grading's status-blind policy is now mandatory, ratified policy (not a proposal); `market_monitoring_events` explicitly confirmed untouched, Phase 7's alone; Milestone 5.6 approved as a mandatory pre-Beta milestone with a phased authorization — basic mechanics may build ahead of Phase 7/8, but closure requires real Phase 7/8 signals; the dashboard "never silently disappear or overwrite" principle locked, exact visual treatment left open. Zero code/migration/UI/Telegram/grading/worker change from this entry — approving a design is not authorizing its build. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v5.12 note (MINOR, HQ directive, planning only):** New §9.7, Recommendation Lifecycle & Change Communication — architecture reservation only, nothing built. HQ directed formally defining what happens when MANSA changes its view after a recommendation has already been activated, so a real recommendation change between morning analysis and kickoff is never silently lost (`docs/ops/recommendation-lifecycle-spec-2026-09-04.md`). Proposes extending `recommendation_product_lifecycle_events` (Volume 3 §5G, new) with `STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED` event types and a `trigger_type` reusing `market_monitoring_events.event_type` almost verbatim plus two new categories (`contextual_intelligence_change`/`model_refresh`); confirms Volume 5's existing Time Machine `whatChanged`/temporal-integrity design already implements the right "preserve original, surface change separately" shape and needs only a vocabulary extension; flags the live dashboard and any future Telegram alert surface as genuine, undesigned gaps; and makes explicit, as a proposed ratified policy grounded in this pass's own direct code inspection (no status filter exists anywhere in the grading pipeline today), that grading must remain status-blind — an activated recommendation stays gradeable even if later withdrawn, closing the specific loophole that would otherwise let withdrawal improve MANSA's own Track Record. Flagged as a mandatory Phase 12 (Beta) prerequisite per HQ's own explicit instruction. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v5.11 note (MINOR, HQ decision):** New §8.6, Contextual Performance Intelligence — architecture reservation only, same treatment as §8.5 (Market Integrity & Anomaly Intelligence), documenting the future capability the new Engineering Roadmap Phase 8 will eventually build against. Establishes the evidence-quality requirements (comparable sample size, similarity, baseline, recency, confidence, confounders), the "insufficient comparable evidence is a valid result" principle, and an audited list of which context factors already have real, usable history (injuries, weather pregame, depth charts, roster) versus which have none today (in-game condition changes, play-by-play/game state, News history, playing surface) — the latter feeding the separate, time-sensitive 2026 Data Preservation Requirement (`docs/ops/2026-data-preservation-requirement.md`). No numeric threshold invented. See `CHANGELOG.md`'s 2026-09-04 entry for full reasoning.
**v5.10 note (PATCH):** §1's "22-agent committee" description gains a pointer to §8's v5.6 note and Volume 1's v3.1 pricing-copy correction — only 12 agents are implemented as of the Phase 5 close, found relevant again during Phase 6 Product/UX planning (HQ Final Decision 4) since Phase 6 UI must not imply a 22-agent roster. §1's original text is left intact (it accurately describes the original design target); only the pointer is new. See `CHANGELOG.md` v5.10 entry for full reasoning.
**v5.9 note (MINOR):** §6.2/§10 document Milestone 5.5's Adaptive Agent Weighting V1 as a PROPOSE-ONLY implementation, built entirely against deterministic fixtures (`app.features.adaptive_weighting`/`app.orchestration.adaptive_weighting`, ai-orchestrator), persisted append-only to Volume 3 §5E's two new tables. "200 recommendations" is reinterpreted as 200 classifiable graded-leg observations per agent (only the 9 game-level voting agents can ever produce one); `learning_rate` is fixed at `0.25` as an approved initial product-policy default (`ADAPTIVE_WEIGHT_LEARNING_RATE`), not an empirically-optimized value; the ±10% single-adjustment guardrail is enforced independently of it; `agents.current_weight` is never automatically mutated — a future, separately-authorized promotion step is required to close the loop. The 2026-08-07 `agent_performance_scores` rows predate this architecture and carry no valid provenance; they are disregarded, not deleted. This is IMPLEMENTATION VALIDATION only — no real graded recommendation history exists yet, so EMPIRICAL VALIDATION (does the weighting actually improve committee performance) remains pending. See `CHANGELOG.md` v5.9 entry for full reasoning.
**v5.7 note (MINOR):** §9/§8 each gain an explicit logic-version identifier (Phase 5 Milestone 5.3, Time Machine): `app.features.strategy.STRATEGY_VERSION`/`app.features.explainability.EXPLAINABILITY_VERSION`, both `"v1"`, frozen respectively onto Volume 3 §5C's `recommendation_activation_snapshots.strategy_version` and §5B's `recommendation_product_explanations`/`recommendation_leg_explanations.explainability_version` — a sixth and seventh independent kind of version (alongside `prompt_version`/`agent_version`/`weight_applied`/model identity), since Strategy's qualification/ranking rules and Explainability's template logic can each change on their own schedule, independent of the AI committee's own versioning. Neither is a global "AI version" — Volume 3 §5's own five-separate-columns principle, applied twice more. See `CHANGELOG.md` v5.7 entry for full reasoning.
**v5.6 note (MINOR):** §8 gains a note documenting Milestone 5.2's actual Deterministic V1 implementation against the original question table below — built in `app.features.explainability`/`app.orchestration.explainability` (ai-orchestrator), persisted to Volume 3 §5B's two new tables. No LLM narrative layer, no live model calls (`narrative_summary` reserved, unpopulated). One real correction to this section's original sourcing is disclosed inline: "why not another bet" is answered from the Strategy Engine's own deterministic rejection trace (§9, `RejectedCandidate`/`RejectionReason`), not a Public Betting Agent — no such agent exists in the implemented 12-agent committee. See `CHANGELOG.md` v5.6 entry for full reasoning.
**v5.3 note (MINOR):** §3.1/§4.3 document the shared-vs-personalized execution split built for the proactive Recommendation Worker (Milestone 4.9): Probability Modeling → EV → Risk Manager, consensus computation, and Meta Agent review each run exactly once per `(recommendation_id, candidate)` pair, shared across every user; Bankroll Coach runs separately, once per user who needs a stake number, reusing the shared chain's already-computed probability/EV; Elite second-pass reconciliation is computed at most once per candidate per cycle and reused across every Elite-tier subscriber, with entitlement/tier controlling only whether it triggers, never how many times the underlying evidence gets re-analyzed. Candidate generation (V1: home/away moneyline, home/away spread, over/under total, no player props, one reference sportsbook per game) is also documented here for the first time. See `CHANGELOG.md` v5.3 (Volume 4) entry for full reasoning.
**v5.2 note (MINOR):** §4.3's Elite second-pass threshold corrected from the structurally-unreachable `agreement_variance > 0.25` to `> 0.10` (Milestone 4.8, Decision L) — the `1.0`/`0.3` directional-agreement factors, `aggregate_confidence`'s semantics, and the variance formula itself are all unchanged, per Mac's explicit instruction. §6 (Adaptive Agent Weighting) is confirmed Phase 5 scope, not Phase 4 — Phase 4's own obligation (consuming `current_weight` correctly via `weight_applied`) was already satisfied in Milestone 4.7; the write/learning loop described in §6.1 has not been built and its guardrail numbers remain provisional launch defaults pending real settlement/outcome data. See `CHANGELOG.md` v5.2 entry for full reasoning.
**v5.1 note (MINOR):** §4.1 documents candidate-anchored consensus as an intentional Blueprint evolution (Phase 4 Milestone 4.7) — `directional_agreement` now compares each fan-out agent against a specific `MarketCandidate`'s own resolved direction, not a self-referential committee majority, since Milestone 4.6 introduced a candidate concept this section's original wording never anticipated. Also documents a real, freshly-discovered mathematical ceiling on `agreement_variance` (implemented as population variance of `directional_agreement` values) that makes §4.3's `> 0.25` Elite second-pass threshold unreachable under this section's own specified `0.3` fractional penalty — flagged as an open question, not resolved. See `CHANGELOG.md` v5.1 entry for full reasoning.
**Depends on:** Volume 2 (v5.0 — Orchestrator deployment shape, async fan-out pattern, scoped event system, Redis, Recommendation Worker, multi-source/deterministic-derived-intelligence vendor strategy) and Volume 3 (v4.0 — `agents`, `agent_performance_scores`, `recommendation_agent_outputs`, `consensus_snapshots`, `model_routing_rules`, `prompt_registry`, `model_registry`, `daily_game_intelligence`, normalized multi-sport core)
**Resolves open items from:** Volume 2 §7 (confidence variance threshold), Volume 3 §13 (agent weighting algorithm, conversation schema)
**v5.0 note (MAJOR):** §1.1 (new) establishes the RAW FACT → DETERMINISTIC FEATURE → AI REASONING → CONSENSUS → RECOMMENDATION STRATEGY pipeline as an explicit, volume-wide principle — triggered by declining SportsDataIO's ~$10-15K/season quote and adopting a multi-source + internally-derived-intelligence strategy instead (Volume 2 §8's own updated note). Generalizes the deterministic-math discipline already locked into Phase 4's real implementation (Milestone 4.2's agent output contract) to every feature category, not only EV/Kelly: an LLM never fabricates a missing metric, never performs arithmetic or recalls a fact application code can compute reproducibly. Derived-score-table/`daily_game_intelligence`-field ownership stays explicitly undecided, deferred to the pre-Milestone-4.4/4.5 data-contract inspection Mac has directed. See `CHANGELOG.md` v5.0 entry for full reasoning.
**v4.0 note:** §3.1 now documents two entry points into the same pipeline — the proactive Recommendation Worker (Volume 2 §4.4) and on-demand NL Engine requests — converging on identical steps, not separate fast/slow paths. See `CHANGELOG.md` v4.0 entry for full reasoning.
**Read next:** Volume 5 (Frontend & UX Architecture) — every output defined here needs a home on a screen

---

## 1. How This Volume Fits

Volume 2 defined *how the Orchestrator is deployed* (stateless, async, horizontally scalable). Volume 3 defined *where its outputs are stored* (snapshot tables, append-only history). This volume defines *what it actually thinks* — the 22-agent committee (21 fan-out agents plus the Meta Agent reviewer, v2.0) as originally specified [only 12 are implemented as of the Phase 5 close — see the v5.6 note (§8) and Volume 1 v3.1 for the current, correct count; any UI referencing agent count must derive it from live system data, never assume 22], how their outputs get reconciled into one recommendation, how confidence is calibrated, and how the system gets smarter over thousands of recommendations without overfitting to noise.

This is the largest and most important volume in the blueprint. It's also the one place where a bad decision is hardest to detect early — a flawed pricing tier is obvious in week one; a flawed weighting algorithm can look fine for months and then quietly erode the whole product's credibility. Every section below is written with that risk in mind.

### 1.1 Data Sourcing, Derived Intelligence & the Deterministic Calculation Boundary (v5.0)

Added mid-build (2026-08-20), triggered by a real commercial finding rather than planning-stage foresight: SportsDataIO quoted approximately $10,000-$15,000 per NFL season for the collection of feeds this volume's agents were originally assumed to consume directly. Mac's decision — **not proceeding with that purchase at this stage** — is documented fully in Volume 2 §8's own updated vendor-strategy note; this subsection documents the architectural consequence for how every agent in §2 must be designed as a result, since the consequence is squarely this volume's concern, not Volume 2's.

**The governing pipeline, now explicit rather than implicit:**

```
RAW FACT
   ↓
DETERMINISTIC FEATURE / CALCULATION
   ↓
AI REASONING
   ↓
CONSENSUS
   ↓
RECOMMENDATION STRATEGY
```

**Three rules follow directly, and apply to every agent in §2, not only the Decision & Advisory group's EV/Kelly math this volume already singled out (§2.5, §9):**

1. **Buy or ingest raw facts where necessary.** A provider (purchased or free/open) supplies facts the product cannot derive itself — market odds, official injury designations, weather observations, play-by-play events. This layer stays exactly as the adapter-pattern architecture already requires (Volume 2 §8) — swappable, never hardcoded to one vendor.
2. **Calculate what can be calculated deterministically, in application code, not inside a model prompt.** Anywhere a real formula, a real distance calculation, or a real historical aggregation exists, that calculation is plain, reproducible, testable code — never delegated to an LLM to compute or recall. This generalizes the discipline Phase 4's implementation already locked in for EV/Kelly (Milestone 4.2's contract work, `app/agents/contract.py`) to every other feature category a fan-out agent might otherwise be tempted to have the model estimate: travel distance from venue coordinates, line-movement direction/magnitude/velocity from `odds_snapshots`' append-only history, usage shares from `player_stats`, situational tendencies from play-by-play, and any other objectively computable metric.
3. **AI is for reasoning and interpretation over already-computed facts and features, never for fabricating a missing one.** An agent whose deterministic feature is unavailable (no source exists yet, or the calculation hasn't been built yet) must say so — via `evidence_classification: "assumption"`, a lower `confidence`, and a `finding`/`would_change_mind_if` that names the specific gap (§2.1) — never invent a plausible-sounding number to fill the space. This is the same null-not-neutral principle Volume 3 §4.1 already establishes for `daily_game_intelligence` (a `null` category is "unavailable," never silently coerced to a default), carried forward to what an agent is allowed to output: a missing input must never become a confident-looking, fabricated output.

**Where a deterministic feature actually lives — `daily_game_intelligence`, a supporting table, a derived-score table, or computed on demand — is deliberately NOT decided by this note.** That ownership question (including the long-open one for the 13 derived score tables and `daily_game_intelligence`'s `ai_scores`/`momentum`/`matchup_ratings`/`ev_calculations`/`confidence_scores`/`recommendation_candidates` fields, Volume 3 §4.1/§4.2) is Mac's explicit instruction to resolve via a dedicated data-contract impact inspection immediately before Milestones 4.4/4.5 build the affected agent groups — assigning ownership now, merely because a table already exists, is exactly the premature decision that inspection exists to prevent. See `PROGRESS.md`'s Milestone 4.2 entry (2026-08-20) for the full inspection scope and the affected-agent list it will classify (AVAILABLE RAW / DERIVABLE / EXTERNAL SOURCE REQUIRED / DEGRADED BUT USABLE / BLOCKED).

**`public_betting`/`sharp_money` — reaffirmed, not loosened.** Volume 3 §4.1 already established these stay `null` until a legitimate vendor is selected. This note adds one explicit prohibition that volume didn't need to state until agents actually existed to violate it: **line movement is evidence an agent may reason over, but line movement alone is never treated as proof of, or a substitute for, actual sharp-money/public-betting-percentage data.** The Sharp Money Agent and Public Betting Agent must degrade (lower confidence, `evidence_classification` reflecting the gap) rather than reinterpret `null` as "no signal" or infer a percentage from odds movement that was never actually measured.

See `CHANGELOG.md` v5.0 entry for the full Reason/Decision/Alternatives/Impact record, and Volume 2 §8's own updated note for the vendor-candidate detail (nflverse, The Odds API vs. SportsGameOdds, OpenWeather, injuries/news still open) this subsection deliberately does not duplicate.

---

## 2. The Agent Committee

**Twenty-two agents total** (v2.0 — expanded from 21): twenty-one independent agents organized into four functional groups, all participating in the parallel fan-out, plus a 22nd — the Meta Agent (§2.6) — which runs after the other 21 and reviews the committee's output rather than the game itself. Every fan-out agent receives the same base game snapshot (from the Sports Intelligence Layer, Volume 2 §8) and independently returns a structured output — never prose alone.

### 2.1 Shared Agent Output Contract

Every fan-out agent, regardless of category, returns the same base shape, stored in `recommendation_agent_outputs.raw_output` (Volume 3 §5):

```json
{
  "agent_name": "injury_intelligence_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}
```

**Why every agent must include `would_change_mind_if`:** this single field is what makes the Explainability Engine's "what would invalidate this recommendation?" question (Section 8) answerable without inventing an explanation after the fact. It's collected at the moment of analysis, not reconstructed later — which matters for reproducibility (Volume 3's Time Machine principle applies to *reasoning*, not just data).

**Why `evidence_classification` was added (v2.0):** an agent's finding can be strongly worded and still be resting on an assumption rather than hard data. Requiring every agent to self-classify its own finding — rather than having a separate process guess at it after the fact — means the Consensus Engine (§4.1) can discount assumption-heavy findings at the moment consensus is calculated, not as an afterthought.

### 2.2 Context & Data Agents
Establish the factual ground truth other agents reason on top of.

| Agent | Core Question | Primary Inputs |
|---|---|---|
| Injury Intelligence Agent | Who's out, questionable, or playing through something, and how much does it matter? | `injury_reports` snapshots, depth chart |
| Weather Agent | Does weather meaningfully affect this game's total or style of play? | `weather_snapshots`, stadium (indoor/outdoor) |
| Travel & Fatigue Agent | Does travel distance/time zone shift create a measurable disadvantage? | Schedule history, game location |
| Rest Days Agent | Does a rest-days differential between teams matter here? | Schedule history |
| Referee Tendencies Agent | Does the assigned crew's historical tendency (pace, penalty rate) affect the total or style? | Referee assignment, historical ref data |

### 2.3 Matchup & Form Agents
Reason about team-vs-team quality and trajectory.

| Agent | Core Question | Primary Inputs |
|---|---|---|
| Offensive Matchup Agent | How does this offense perform against this specific defensive profile? | Team/player stats, matchup history |
| Defensive Matchup Agent | How does this defense perform against this specific offensive profile? | Team/player stats, matchup history |
| Historical Trends Agent | What do these two teams' (or this situation's) historical patterns suggest? | Historical game data |
| Team Form Agent | Is either team trending up or down recently, independent of season-long averages? | Recent game results, advanced metrics |
| Coaching Tendencies Agent | Does either coaching staff have a tendency (aggressiveness, situational calling) relevant here? | Historical play-calling data |
| Motivation Agent | Does either team have a non-obvious motivational factor (revenge game, milestone, lookahead spot)? | Schedule context, narrative data |
| Playoff Importance Agent | How much does this game actually matter to each team's season, and does that change effort/strategy? | Standings, playoff scenarios |
| Player Prop Agent | For prop markets specifically, how should an individual player's likely usage/performance be assessed? | Player stats, usage trends, matchup |

### 2.4 Market Agents
Reason about the betting market itself, not the underlying sport.

| Agent | Core Question | Primary Inputs |
|---|---|---|
| Vegas Line Agent | What is the current line actually implying, and is that implication sound? | `odds_snapshots` |
| Closing Line Movement Agent | How has the line moved since open, and what does that movement suggest? | `odds_snapshots` history |
| Sharp Money Agent | Is there evidence of sharp (professional) money on one side, distinct from ticket volume? | Line movement vs. bet split data, where available |
| Public Betting Agent | What is public sentiment doing, and should it be faded or respected here? | Bet split data, where available |

### 2.5 Decision & Advisory Agents
Convert everything above into a probability, a value judgment, and a risk-aware recommendation.

| Agent | Core Question | Primary Inputs |
|---|---|---|
| Probability Modeling Agent | Given all upstream findings, what's a calibrated win/cover/over probability? | All upstream agent outputs |
| Expected Value Agent | Given that probability and the current price, is there positive EV here? | Probability Modeling Agent output, current odds |
| Risk Manager | Independent of whether EV is positive, how much variance/risk does this specific bet carry? | Bet type, odds, historical variance by bet type |
| Bankroll Coach | Given the user's profile (unit size, risk tolerance, bankroll), how should this translate to a suggested stake? | `user_profiles`, `betting_dna`, EV/Risk Manager output |

**Why Risk Manager and Bankroll Coach are separate from Expected Value:** a bet can have strong positive EV and still be inappropriate for a specific user's bankroll or risk tolerance (e.g., a +EV parlay with high variance is a bad fit for a conservative $20/unit casual bettor, per Volume 1's Persona B). Collapsing these into one agent would force a single number to represent two different questions — "is this a good bet in the abstract" vs. "is this a good bet for this person" — and Volume 1's personalization promise depends on keeping that distinction explicit and auditable.

**Bankroll Coach's stake formula (v3.0):** fractional Kelly Criterion, not an unspecified translation. Quarter-Kelly is the default multiplier — full Kelly is too aggressive for a product whose core positioning is disciplined risk management, not maximum growth. Computed as `stake = bankroll × (kelly_fraction × edge / odds) × risk_tolerance_multiplier`, where `edge` and the base Kelly fraction come from the Probability Modeling Agent's calibrated probability against the current odds, and `risk_tolerance_multiplier` (derived from `user_profiles.risk_tolerance`) scales the quarter-Kelly base up or down per user rather than applying one fixed fraction to everyone.

### 2.6 Meta Agent (v2.0 — Committee Reviewer, Not a Fan-Out Participant)

The 22nd agent. Unlike the other 21, it doesn't analyze the game — it analyzes the committee's output after the Consensus Engine has run (Section 4). Think of it as AI quality assurance sitting one layer above everything else in this section.

```json
{
  "agent_name": "meta_agent",
  "polarization_score": 0.0,
  "uncertainty_flag": false,
  "confidence_adjustment": 0.0,
  "reasoning": "plain-language summary of committee health for this recommendation"
}
```

- `polarization_score` — how split the 21 fan-out agents were, independent of `agreement_variance` (§4.1), which measures disagreement mathematically; this field captures whether the disagreement clusters meaningfully (e.g., all Market agents vs. all Matchup agents) or is just noise.
- `uncertainty_flag` — true when variance is unusually high across categories, not just within one.
- `confidence_adjustment` — **can only ever be zero or negative.** This is a hard rule, not a convention: letting the Meta Agent boost confidence would create a backdoor around the anti-overfitting guardrails already built into the adaptive weighting system (Section 6). Its entire purpose is catching reasons to be *more* cautious.

Applied in §4.1 as the last step before the 0.55 "No Bet Today" check (§4.2): `final_aggregate_confidence = aggregate_confidence + confidence_adjustment` (where `confidence_adjustment ≤ 0`).

---

## 3. Orchestration Logic

### 3.1 Execution Flow

**Two entry points trigger this flow (v4.0)**, both converging on the same steps below: (1) the **Recommendation Worker** (Volume 2 §4.4), running proactively shortly after each Master Refresh, generating recommendations before any user has asked; (2) the **NL Engine** (§7), triggered on-demand by a specific user request the proactive path wouldn't have anticipated ("build me something around Mahomes"). Both produce a `recommendations` row through the identical pipeline — there is no separate "fast path" or "slow path" logic, only a different trigger.

```
1. Sports Intelligence Layer produces a game snapshot (Volume 2 §8) — as of v3.0, this means agents query `daily_game_intelligence` (Volume 3 §4.1) first, falling back to the individual supporting tables only for anything not yet reflected in that day's pre-assembled record
2. Orchestrator reads model_routing_rules (Volume 3 §8) for each agent's task_type
3. Context & Data Agents + Matchup & Form Agents + Market Agents execute
   in parallel (async fan-out, Volume 2 §7) — 17 agents, one wave
4. Probability Modeling Agent executes, consuming all 17 outputs
5. Expected Value Agent executes, consuming Probability Modeling output + current odds
6. Risk Manager + Bankroll Coach execute in parallel, consuming EV output + user profile
7. Consensus Engine resolves the full set into one recommendation package (§4.1)
8. Meta Agent (§2.6) reviews the consensus output and applies its confidence_adjustment, if any
9. Recommendation Strategy Engine decides final output shape (Section 9)
10. Explainability Engine formats the package into the question-answer structure (Section 8)
11. Package + full snapshot composed into the Time Machine activation-snapshot manifest (Volume 3 §5C, Milestone 5.3) — NOT the legacy `recommendation_snapshots` (Volume 3 §5), which is confirmed unfit for the Phase 5 product layer and remains untouched
```

**Step 11 corrected (v5.9, Pre-Phase-6 Operational Readiness Gate, 2026-08-27) — this numbered list predates Milestone 5.3 and still named the legacy table `recommendation_snapshots` as the pipeline's final write target.** The authoritative mechanism, in production since Milestone 5.3, is the additive activation-snapshot manifest (`recommendation_activation_snapshots` + its two join tables, composing already-frozen Milestone 5.1/5.2 rows by FK) plus the internal-only `app.orchestration.reconstruction.reconstruct_recommendation_product` read path — see §5C's own correction note and Volume 3 §5C for the full reasoning already on record. This edit updates the numbered list itself to match; it does not introduce a new decision.

**Steps 9/10 reordered (v5.0, Phase 5 Milestone 5.1, Decision R, 2026-08-25) — a genuine self-contradiction in this document's earlier text, not a new decision being introduced here.** The list above originally read Explainability (step 9) then Strategy (step 10), while Section 9's own text already said Strategy "sits after Consensus and before Explainability" — the two couldn't both be true. Strategy also structurally has to run first: Explainability's question list (Section 8) includes "why this bet type" and "why not alternatives," neither of which is answerable before Strategy has actually decided a shape. Corrected here to match Section 9's own text and the underlying dependency, not the other way around.

**Why proactive generation doesn't complicate personalization (step 6):** the Recommendation Worker's proactive run uses each active user's `user_profiles`/`betting_dna` at the time it runs, same as an on-demand request would — it's not a single generic recommendation broadcast to everyone. In practice this means the worker iterates active users (or user-persona clusters, as an optimization once volume justifies it) rather than producing one universal recommendation per game.

Steps 4–6 are necessarily sequential (each depends on the prior step's output), while steps 1–17 in step 3 run concurrently — this hybrid pattern is why the deployment needs to support both fan-out and short sequential chains within a single request, a nuance worth flagging back to Volume 2's stateless-service assumption: the Orchestrator's internal execution graph has structure, even though the service itself is stateless between requests.

### 3.2 Model Routing Decision

Each `task_type` in `model_routing_rules` maps to a primary/fallback model. Recommended default routing:

- **Context/Data/Matchup/Market agents (17 agents):** faster, cheaper model tier by default — these are structured extraction-and-reasoning tasks over well-defined data, not open-ended judgment calls, so they don't need the most expensive model.
- **Probability Modeling, Expected Value:** stronger reasoning model — these synthesize 17 upstream signals into one calibrated judgment, which is exactly the kind of task where a weaker model's errors compound.
- **Consensus reconciliation (Elite second-pass only, Section 4.3):** strongest available model, used sparingly and only when triggered.

This routing table is data (Volume 3 §8), so this default can be tuned per-agent as real performance data accumulates in `agent_performance_scores` — an agent whose confidence calibration is poor on the cheaper model is a concrete, measurable signal to route it to a stronger model, rather than a guess.

---

## 4. Consensus Engine

### 4.1 Aggregate Confidence Calculation

```
aggregate_confidence = Σ (agent_confidence[i] × current_weight[i] × directional_agreement[i])
                        ─────────────────────────────────────────────────────────────────
                                            Σ current_weight[i]
```

Where `directional_agreement[i]` is 1.0 if the agent's `directional_lean` matches the majority lean, and a fractional penalty (recommend 0.3, tunable) if it disagrees — this way a confident but lone dissenting agent pulls aggregate confidence down rather than being silently outvoted, since disagreement itself is information (this is also what feeds `agreement_variance` in `consensus_snapshots`, Volume 3 §5).

**v5.1 — candidate-anchored consensus, an intentional Blueprint evolution (Phase 4 Milestone 4.7, 2026-08-22).** This section was written before any specific-wager concept existed in the architecture. Phase 4 Milestone 4.6 introduced `MarketCandidate`-scoped evaluation (Probability Modeling, Expected Value, Risk Manager, Bankroll Coach all reason about one specific priced wager, e.g. "KC moneyline -125," not "the game" abstractly) — a concept this section's original "majority lean" wording never anticipated, and which a literal implementation would evaluate incoherently (e.g. letting totals-relevant agents outvote moneyline-relevant ones for a spread candidate). **Consensus is now explicitly candidate-anchored, not computed as a self-referential committee majority:** `directional_agreement[i]` compares each agent's `directional_lean` against the SPECIFIC CANDIDATE's own resolved direction (home/away for moneyline/spread, over/under for totals — resolved by exact match against the game's authoritative `home_team`/`away_team`, never inferred from array position or text ordering), answering "how strongly does the available committee support THIS candidate?" rather than "what does the committee agree on generally?" No separate game-level majority score is maintained alongside it. One `consensus_snapshots` row exists per `(recommendation_id, candidate_key)` pair, never one per game collapsing multiple evaluated candidates together.

**The exact three-state rule, since the original two-state (matches/disagrees) formula has no accommodation for "no opinion":** an agent's lean exactly matching the candidate's direction contributes `1.0`; the exact opposite value on the same axis contributes `0.3`; `directional_lean = "none"`, OR a lean on a different axis than the candidate's own (e.g. a home/away lean against a totals candidate), contributes no directional vote at all — such an agent is excluded from both the numerator and denominator of this formula (never coerced into support or opposition), while remaining fully visible in the run's own participation record. Player-prop candidates have no defined directional mapping yet (Player Prop Agent itself remains unbuilt) and are excluded from this calculation entirely — `aggregate_confidence` is `None` (undefined, not a fabricated number) for a prop candidate today.

**A real mathematical tension in this section's own numbers, found in Milestone 4.7 and resolved in Milestone 4.8 (Decision L):** `agreement_variance` (no formula given anywhere in this volume or Volume 3) is implemented as the population variance of the `directional_agreement[i]` values among voting agents. With only two possible values (`1.0`, `0.3`), the maximum possible variance of any real distribution is `p(1-p)(1.0-0.3)^2`, maximized at a 50/50 split: `0.25 × 0.49 = 0.1225` — meaning the original `agreement_variance > 0.25` Elite second-pass trigger (§4.3) could never fire from any real computed input, under this section's own specified `0.3` fractional penalty, independent of the candidate-anchoring change above (the original game-level majority-vote formula has the identical two-value ceiling). **Resolved (v5.2): the threshold alone was corrected to `> 0.10`** — reachable at a 70/30 voting split (`agreement_variance ≈ 0.1029`) and every split closer to even, while looser disagreement (75/25 or beyond) stays below it. The `0.3` fractional penalty, `aggregate_confidence`'s semantics, and the variance formula itself were deliberately left unchanged — this was judged the smallest defensible fix, not a reason to redesign the underlying disagreement signal. `agreement_variance` remains, explicitly, an **unweighted** committee-polarization signal: `weight_applied`/the assumption discount affect `aggregate_confidence` but never this statistic, so a small number of heavily-weighted dissenting agents against a larger number of lightly-weighted ones is not distinguished from an equal-headcount split of equally-weighted agents today. Whether `agreement_variance` should eventually become weight-aware is an open, explicitly deferred question — not decided in Milestone 4.8. See `CHANGELOG.md` v4.15/v5.1/v5.2 entries and `PROGRESS.md`'s Milestone 4.7/4.8 entries for the full derivation and options considered.

**v2.0 addition — evidence-classification discount:** before the formula above runs, any agent whose `evidence_classification` (§2.1) is `assumption` contributes at 0.5× its normal `current_weight[i]` for that specific calculation only — this is a per-recommendation discount, not a permanent change to the agent's stored weight. A single assumption-heavy finding shouldn't carry the same force as a data-backed one, but shouldn't be discarded either, since informed inference is often legitimately useful.

**v2.0 addition — Meta Agent adjustment:** after `aggregate_confidence` is computed, the Meta Agent (§2.6) runs and produces `final_aggregate_confidence = aggregate_confidence + confidence_adjustment`, where `confidence_adjustment` is always ≤ 0. This final, possibly-lowered number is what feeds §4.2's threshold check, never the pre-adjustment value.

### 4.2 "No Bet Today" Threshold

Recommend a hard floor: **final_aggregate_confidence < 0.55 → automatic "No Bet Today,"** regardless of EV. This number should not be treated as sacred on day one — it needs backtesting against historical data before launch and should be one of the first things the Continuous Learning Engine (Section 10) is allowed to adjust, but only via the same sustained-evidence process as agent weights, never on a single bad week.

**Phase 4/5 boundary (Milestone 4.7):** this threshold's result is computed and persisted as an internal analytical fact (`consensus_snapshots.below_confidence_floor`) — this is NOT the same action as producing a user-facing "No Bet Today" recommendation object. Section 9's Recommendation Strategy Engine (Phase 5) alone decides `recommendations.recommendation_type`; Phase 4 never sets it, never sets `status = active`, and never assembles a `recommendation_snapshots` row.

### 4.3 Elite-Tier Second-Pass Reconciliation

**This resolves the open item flagged in Volume 2 §7.** Recommend: if `agreement_variance > 0.10` (v5.2, corrected from `0.25` — see §4.1's note; meaning roughly a 70/30-or-more-polarized split among voting agents, not just noisy confidence scores) **and** the user's tier is Elite, trigger a second reasoning pass using the strongest routed model, explicitly given all 21 fan-out agents' raw outputs plus the Meta Agent's `reasoning` field, and asked to reconcile the disagreement rather than just re-run the math. Free/Pro tier requests accept the first-pass consensus even under high variance, which is the concrete difference Volume 1's "priority agent compute" pricing language needs. Log `second_pass_triggered = true` (Volume 3 §5) every time this fires — this becomes a measurable feature-usage metric, not just a marketing claim.

**v5.1 — dedicated reconciliation contract (Milestone 4.7):** the second pass's output is a small, dedicated contract (candidate identity, reconciliation reasoning, `confidence_adjustment`, supporting evidence, `would_change_mind_if`) — deliberately NOT the Meta Agent's own `MetaAgentOutput` (§2.6). The two review a candidate's consensus for different reasons and stay semantically separate. Same hard rule as the Meta Agent's: `confidence_adjustment` can only ever be zero or negative, enforced at construction time. **See §4.1's v5.2 note for the mathematical ceiling that made the original `> 0.25` threshold unreachable and the corrected `> 0.10` value's derivation** — the trigger logic itself was already implemented and tested correctly in isolation before the threshold correction; only the constant changed.

---

## 5. Confidence Calibration

Confidence scores are only useful if a 0.7 actually means "right about 70% of the time" — otherwise they're just decoration. Calibration is measured, not assumed:

- Bucket historical recommendations by confidence score (e.g., 0.55–0.60, 0.60–0.65, etc.)
- For each bucket, compute actual win rate against that bucket
- A well-calibrated system shows actual win rate tracking the bucket's confidence range; systematic drift (e.g., 0.70-confidence bets winning 55% of the time) means the Probability Modeling Agent is overconfident and needs recalibration

This calculation is exactly what `agent_performance_scores.confidence_calibration_score` (Volume 3 §5) stores per agent, and the same calculation applies at the system level against `ai_performance` (Volume 3 §6). Recommend running this as a scheduled worker job (Volume 2 §4.4) on a rolling basis, not just pre-launch.

---

## 6. Adaptive Agent Weighting

**Phase 4/5 boundary, confirmed (v5.2, Milestone 4.8 inspection, 2026-08-24):** this entire section — the write/learning loop that actually adjusts `agents.current_weight` from historical performance — is **Phase 5 scope**, per `engineering-roadmap-build-order.md`'s own explicit "Continuous Learning loop updating agent weights under guardrails" assignment. Phase 4's obligation regarding weighting was only to *consume* `current_weight` correctly, which Milestone 4.7 already satisfies (`weight_applied` frozen at fan-out time, `compute_consensus` reading only the frozen value, never a live re-join). As of this note, **no code writes to `agents.current_weight`, `agent_performance_scores`, or `postgame_reviews` anywhere in the codebase**, and every row in those tables plus `verified_bets`/`bet_slips`/`ai_performance`/`projected_user_performance`/`verified_user_performance` is Phase-1 `seed.sql` fixture data, not real historical performance — confirmed by direct live-database inspection, not assumed. The three guardrails below (§6.1) remain **provisional launch defaults, explicitly not finalized** — validating them requires real early-outcome data that does not exist yet; finalizing them now would itself be inventing parameters to make an unbuilt system look decided. Phase 5's own inspection pass, once real settlement/postgame data exists, is expected to re-derive or confirm these numbers with actual evidence.

### 6.1 The Algorithm

```
new_weight[agent] = current_weight[agent] × (1 + learning_rate × performance_delta[agent])

where performance_delta[agent] = (agent's calibrated ROI over window) - (committee average ROI over same window)
```

Guardrails, all enforced before a weight update is allowed to write to `agents.current_weight`:

1. **Minimum sample size** — recommend no weight change below 200 recommendations in the evaluation window (this is why `agent_performance_scores.sample_size` is a required field, Volume 3 §5, not optional).
2. **Maximum single-update change** — cap any single weight adjustment at ±10%, even if the raw formula suggests more. This directly implements the master spec's "avoid overfitting... require sustained statistical evidence" instruction as a hard limit, not a guideline someone can skip under pressure to "fix" an agent that had one bad week.
3. **Evaluation window** — recommend a rolling 90-day window minimum before any agent's weight changes at all, long enough to span a meaningful slice of a season without being so long that it can't react to something like a genuine, sustained shift in an agent's reliability.

### 6.2 Why Not Just Deactivate Underperforming Agents

Resist the urge to remove a chronically low-weighted agent entirely. A near-zero weight already neutralizes its influence on the consensus; removing it destroys the historical record needed for underperforming-agent evidence and any future re-evaluation if conditions change (e.g., a Referee Tendencies Agent that's been unreliable for years could become relevant again after a rule change). Weight toward zero, don't delete. **Corrected reference (Milestone 5.5, 2026-08-27):** the historical record this section originally cited, `postgame_reviews.underperforming_agents` (Volume 3 §7), is confirmed unbuilt/unfit legacy schema (Milestone 5.4) — the real historical record is `recommendation_product_postgame_reviews.underperforming_agents` (Volume 3 §5D) and, at the per-observation level, `adaptive_weight_proposal_observations.classification = 'underperforming'` (Volume 3 §5E).

**Implementation note (v5.9, Milestone 5.5, Propose-Only V1, 2026-08-27).** Built in `app.features.adaptive_weighting` (pure) / `app.orchestration.adaptive_weighting`, persisted to Volume 3 §5E's `adaptive_weight_proposals`/`adaptive_weight_proposal_observations`. Mapping this section's own text onto what actually ships:

- **"200 recommendations" (§6.1)** means 200 classifiable graded-leg observations PER AGENT — see §5E's full definition. This is a Phase-5-architecture reinterpretation of language written before the product/leg layer existed, not a contradiction of the original intent (sustained, per-agent statistical evidence before any influence changes).
- **`learning_rate` (§6.1's formula) = `0.25`** — an APPROVED V1 PRODUCT-POLICY DEFAULT (`ADAPTIVE_WEIGHT_LEARNING_RATE`), NOT an empirically-derived or optimal value, frozen onto every persisted evaluation so a future change is historically traceable. Subject to future review once real graded evidence exists.
- **Guardrails enforced exactly as specified**, application-enforced (the sample-size count and 90-day window are business-logic conditions no database constraint can express on their own) with a database-level append-only/idempotency backstop identical in design to Milestone 5.4's grading tables.
- **V1 is PROPOSE-ONLY, not autonomous.** `agents.current_weight` is never written by this milestone — every evaluation persists what it WOULD propose (`raw_proposed_weight`, `guardrail_adjusted_proposed_weight`) with `applied_weight` always `NULL`. Applying a proposal is a separate, not-yet-authorized future capability, per explicit instruction not to assume "adaptive" implies "autonomous."
- **Global weights only** — no per-sport or per-market-type segmentation is built, though `market_type` remains reachable from every persisted observation's own foreign-key chain for a future segmented-weighting capability to use without re-deriving lost provenance.
- **CLV plays no role** — it remains unavailable (Milestone 5.4, reaffirmed).
- **No LLM (Large Language Model) participates anywhere in this calculation** — ROI, sample counting, `performance_delta`, guardrail checks, and the proposed-weight formula are all pure arithmetic over already-graded, already-frozen evidence; confirmed by source-inspection regression test, not just by design intent.
- **Confidence calibration (§5)'s single aggregate `confidence_calibration_score`** is deliberately left `NULL` in V1 — the bucket-level calculation itself is well-defined, but no Blueprint-authorized formula exists yet for collapsing per-bucket calibration into the one scalar column requires; inventing one was explicitly out of scope for this milestone.
- **Empirical validation remains pending.** Zero real graded recommendations exist in this system as of this milestone (live-verified) — every proposal this engine can currently produce is proven correct against deterministic fixtures only, never described as statistically proven, optimal, or profit-maximizing.

---

## 7. Natural Language Engine

Resolves the schema gap flagged at the end of Volume 3 (§13, `conversations` / `conversation_messages`).

```sql
create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_preferences jsonb default '{}',   -- v3.0: session-scoped exclusions, see below
  created_at timestamptz default now()
);

create table conversation_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  role text check (role in ('user','assistant')),
  content text not null,
  intent_classification text,       -- e.g. 'request_recommendation','ask_explanation','set_preference'
  linked_recommendation_id uuid references recommendations(id),
  created_at timestamptz default now()
);
```

**Intent classification, not rigid command parsing.** Per Volume 1's onboarding design and the master spec's explicit examples ("I only got $20," "I hate betting the Cowboys"), the NL Engine's job is to classify free-text into an intent + extracted parameters (stake constraint, team exclusion, risk framing), then route to the appropriate engine — it never requires the user to phrase things in a specific way. This same classification step is also the mechanism that refines `persona_classification` in `user_profiles` (Volume 3 §3) over time, alongside the Betting DNA worker.

**Session-scoped preference memory (v3.0).** Distinct from the persistent `betting_dna` table (Volume 3 §3): statements like "I don't like unders," "I only bet player props," or "my bankroll today is $75" apply for the rest of that conversation without needing to be restated, written to `conversations.session_preferences` and checked by the NL Engine on every subsequent recommendation request in that session. These don't persist to `betting_dna` on their own — that graduation to a permanent preference only happens if the pattern repeats across multiple sessions, via the existing Betting DNA background worker. Session memory is cheap and immediate; persistent memory requires actual evidence of a lasting pattern, same anti-overfitting instinct that governs agent weighting (§6).

**Progressive disclosure — four response levels (v3.0).** The default response is concise by design, not a compromise:

| Level | Trigger | Content |
|---|---|---|
| 1 | Default | One card: bet, confidence, EV, 1-2 sentence summary |
| 2 | "Why?" / "Explain" | Bullet summary of the 5-8 strongest contributing factors |
| 3 | "Show me your reasoning" | Full prose rendering of the explainability question set (§8) |
| 4 | "Show me everything" | Complete consensus report — every contributing agent's output |

Nothing new needed to be built to support this: Level 4 *is* the Explainability Panel (Volume 5 §5), Level 3 *is* a prose rendering of `explainability_payloads`, Level 1 *is* the Recommendation Card's existing summary fields. This is a presentation-layer sequencing decision, not a new data requirement.

---

## 8. Explainability Engine

Maps directly onto `explainability_payloads` (Volume 3 §5) and the master spec's explicit question list — this section defines *where each answer comes from*, closing the loop between "the product must explain this" (Volume 1) and "the schema has a field for it" (Volume 3):

| Question | Source |
|---|---|
| Why this recommendation? | Synthesized from Probability Modeling + Expected Value Agent outputs |
| Why this bet type? | Recommendation Strategy Engine's decision path (Section 9) |
| Why now? | Closing Line Movement Agent + timing of market inefficiency |
| Why not another bet / not the public favorite? | Public Betting Agent's lean vs. final recommendation, explicitly contrasted |
| What evidence was strongest? | Highest-weighted agents whose `directional_lean` matched the final call |
| Biggest risks? | Risk Manager output directly |
| What would invalidate this? | Aggregated `would_change_mind_if` fields from top-contributing agents |
| Which agents contributed? | `contributing_agents` — agents whose weighted confidence exceeded a minimum contribution threshold |
| Why does this fit the user? | Bankroll Coach output, referencing `user_profiles` + `betting_dna` |

This table is the concrete implementation spec Volume 5 needs to design the recommendation detail screen around — every row here is a UI element, not just a data field.

**Implementation note (v5.6, Milestone 5.2, Deterministic V1, 2026-08-25):** built in `app.features.explainability`/`app.orchestration.explainability`, persisted to Volume 3 §5B's `recommendation_product_explanations`/`recommendation_leg_explanations`. Every value is read back from an already-frozen Phase 4/Milestone 5.1 row — nothing here is re-derived, re-computed, or (since there is no live model call in this milestone) narrated by an LLM. Mapping the table above onto what actually ships:

| Question | Actual v1 source |
|---|---|
| Why this recommendation? / Why this bet type? | `why_this_shape` — the Strategy Engine's own outcome (`single`/`multiple_singles`/`no_bet`/`bankroll_preservation`) and qualification math (§9) |
| Why now? | Not built in V1 — Closing Line Movement is a game-level committee voter (contributes to `contributing_agents`), not yet a standalone timing statement; see §9.5 (Bet Timing & Execution Intelligence, future) |
| Why not another bet / not the public favorite? | `why_not_other_shapes`/`rejected_alternatives` — **corrected sourcing:** the Strategy Engine's own deterministic rejection trace (`RejectedCandidate`/`RejectionReason`, §9), never a Public Betting Agent lean. No Public Betting Agent exists in the implemented 12-agent committee; this row's original sourcing text was aspirational and is corrected here, not implemented as originally written. |
| What evidence was strongest? | `strongest_evidence`, from `contributing_agents` — game-level committee agents only (Injury Intelligence, Weather, Vegas Line, Closing Line Movement, Travel & Fatigue, Rest Days) whose `directional_lean` matches the leg's resolved direction |
| Biggest risks? | `biggest_risks` — Risk Manager's own already-frozen candidate-level output, read directly |
| What would invalidate this? | `would_change_mind_if` — verbatim quote of the single highest-weighted supporting agent's own field; NULL (never synthesized) when no defensible one exists |
| Which agents contributed? | `contributing_agents` jsonb — a frozen render of the same `recommendation_agent_outputs` rows above, not a separate threshold computation |
| Why does this fit the user? | Not built in V1 — `user_recommendation_selections` (Volume 3 §5A) already carries the per-user Kelly/risk-tolerance personalization; a Bankroll-Coach-sourced explanation sentence is deferred, not fabricated in its place |

Two rows are honestly unbuilt rather than filled with a fabricated stand-in — "why now" and "why does this fit the user" — per the explicit "NULL/absent is preferable to invented intelligence" guardrail (also governing `would_change_mind_if` above). Both are natural extension points for a future milestone, not gaps hidden behind placeholder text.

---

## 8.5 Market Integrity & Anomaly Intelligence (v5.14, Milestone 7.1's detection engine BUILT 2026-09-04; the rest remains FUTURE CAPABILITY, NOT YET IMPLEMENTED)

**Status: the DETECTION half of this section is now real, working code (Milestone 7.1, 2026-09-04) — the STRATEGY/EXPLAINABILITY/UI half described below remains architecture reservation only, nothing built.** `app.features.market_integrity` (`ai-orchestrator`) computes the conceptual severity model below (INSUFFICIENT_HISTORY added as its own honest fourth state, never folded into NORMAL) from `LineMovementFeatures`, checks it against injury/weather/lineup/**news** evidence (`app.persistence.market_integrity`), and persists a qualifying (WATCH/ELEVATED/SEVERE) result to `market_monitoring_events` for the first time (`app.orchestration.market_integrity.assess_game_market_integrity`) — deterministic throughout, no LLM call anywhere in the classification path, matching this section's own Mechanism Decision below exactly. **Not yet built, still exactly as described below:** Strategy Engine interaction (SEVERE suppression via the existing withdrawal mechanism — Milestone 7.2), Explainability disclosure (Milestone 7.3), any UI surface, and any wiring into a live pipeline at all — `assess_game_market_integrity` is reachable today only by direct import (this milestone's own 42 tests), never automatically. Thresholds are disclosed-conservative policy defaults (`THRESHOLD_VERSION="v1-provisional"`), explicitly not empirically derived — DEV's real odds history remains exactly as thin as Milestone 7.0 found it. Full detail: Engineering Roadmap's Milestone 7.1 entry; `CHANGELOG.md`'s 2026-09-04 entry.

The remainder of this section, unchanged since 2026-08-25, still accurately describes the FULL future capability Milestone 7.1 is only the first slice of:

**Purpose.** The Playbook must account for situations where the normal statistical and betting assumptions surrounding a game, market, team, player, or other participant may be less trustworthy than usual. **This is explicitly not a "rigging detector."** The system must never claim a game is fixed, a player intentionally underperformed, a referee manipulated an outcome, a sportsbook controlled an outcome, or that suspicious market behavior alone proves corruption — unless credible, authoritative evidence establishes such an integrity event. Absent that evidence, the system detects and communicates unusual conditions, unexplained market behavior, and statistical anomalies — never a fabricated causal story.

**Three distinct concepts, kept explicitly separate — conflating them is the one mistake this section exists to prevent:**

1. **Statistical anomaly** — an observed performance or condition is unusual relative to expected behavior. Alone, this is not evidence of manipulation.
2. **Market anomaly** — betting-market behavior is unusual or cannot currently be explained by known information (e.g. abnormal line movement, unusual player-prop movement, movement inconsistent with currently-known injury/weather/roster information, abrupt near-kickoff movement). Alone, this is not evidence of manipulation.
3. **Confirmed integrity information** — credible external information exists (an official league investigation, regulator action, suspension, criminal case, a confirmed gambling-policy violation, authoritative reporting of an integrity event). **Only this category may justify explicit integrity-related language**, and its provenance must be preserved alongside the claim.

**Unexplained Market Movement — the key future signal.** When the Playbook's known evidence supports one side and no meaningful injury/weather/roster/matchup information has changed, but the market nevertheless moves materially against that side, the system must never conclude "Vegas knows something." It may instead surface **UNEXPLAINED MARKET MOVEMENT**: "the market changed materially in a way the information currently available to The Playbook does not adequately explain." This increases uncertainty; it never manufactures an explanation to fill the gap.

**Conceptual severity model (labels only — no numeric thresholds are locked in by this entry; a later focused inspection, with real market data available to validate against, must derive any defensible number, exactly matching this project's established practice of never inventing a threshold without evidence — see the Elite second-pass variance threshold history in §4.3 for precedent):**

- **NORMAL** — no meaningful anomaly/integrity concern.
- **WATCH** — something unusual exists but does not currently invalidate the recommendation.
- **ELEVATED** — multiple or meaningful unexplained signals exist; the recommendation deserves additional scrutiny.
- **SEVERE** — credible integrity information, or extreme unexplained conditions, make normal assumptions sufficiently unreliable that recommendation suppression may be appropriate.

**Architectural position.** Conceptually sits between the committee/consensus analysis (§2–§6) and Strategy Engine activation (§9): `Market/Data Refresh → Phase 4 Analysis/Committee → Market Integrity & Anomaly Intelligence → Strategy Engine → Explainability (§8) → Product Recommendation`. It is primarily a **risk/guardrail capability**, not an ordinary voting committee member — it must not be casually implemented as "just another fan-out agent" whose lean gets averaged into consensus. **Whether it is ultimately a deterministic risk engine, one or more specialist agents, a hybrid, or another mechanism is an explicit open implementation question for a future focused architecture inspection — not decided here.**

**Strategy Engine interaction (future).** The Strategy Engine (§9, currently frozen per Milestone 5.1) must eventually be capable of responding to an anomaly/integrity signal with outcomes such as: recommendation remains valid; recommendation receives additional scrutiny; recommendation moves into a WAIT state (§9.5); recommendation is re-evaluated; recommendation is suppressed/PASS; recommendation becomes `no_bet`. The system must always prefer disclosed uncertainty over fabricated certainty.

**Explainability requirement (future).** Explainability (§8) must eventually distinguish FACT, INFERENCE, ANOMALY, UNEXPLAINED CONDITION, and CONFIRMED INTEGRITY INFORMATION as genuinely different categories, never blended into one sentence. Acceptable: "Unusual market movement was detected that is not currently explained by known injury, weather, or roster information." Unacceptable, under any circumstance: "The sportsbook knows the game is fixed." Provenance/evidence must be preserved for every integrity-related claim, exactly like every other explanation statement in §8.

**Relationship to existing architecture — inspected directly, not assumed:**

- **`market_monitoring_events` (Volume 3 §7)** already exists as live schema and, as of Milestone 7.1 (2026-09-04), has its first real writer — `app.orchestration.market_integrity` inserts a row (`event_type='line_movement'`, `action_taken` always `'none'`) for every qualifying (WATCH/ELEVATED/SEVERE) classification. Its `event_type`/`action_taken` vocabulary anticipated exactly this shape, confirmed correct by actually building against it rather than only by inspection.
- **`worker-market-monitor` (Volume 2 §4/§5)** is a provisioned Railway service with **no application code at all** — confirmed by a direct repository search (no file anywhere implements it, unlike `worker-scheduled`, which Milestone 4.9 built out for the Recommendation Worker). It is the intended future home for this capability's live monitoring loop.
- **Closing Line Movement Agent** (§2.4, built in Milestone 4.4) already computes how a line has moved since open from `odds_snapshots` history — this is a real, existing signal this future capability would consume as one input, not duplicate. It answers "how has the line moved," not "is this movement explained" — the anomaly layer's job is the second question.
- **`odds_snapshots`** (Volume 3 §4) already holds the full historical price series needed to detect movement; no new raw-data table is anticipated.
- **Recommendation withdrawal** (`recommendations.status='withdrawn'`/`withdrawn_at`/`withdrawal_reason`, Volume 3 §5; mirrored in `recommendation_products` per Volume 3 §5A) already has the schema-level mechanism a SEVERE integrity finding would use to suppress a recommendation — no new withdrawal mechanism is anticipated, only a new trigger for using the existing one.
- **Strategy Engine / Explainability / Time Machine** — see the two subsections above and below; no duplication of responsibility identified, only new upstream input and new downstream disclosure obligations once built.

**No genuine architecture conflict was found** — this capability composes with existing, mostly-unbuilt scaffolding (`market_monitoring_events`, `worker-market-monitor`) rather than requiring any of it to be redesigned.

---

## 8.6 Contextual Performance Intelligence (v5.11, FUTURE CAPABILITY — APPROVED / DOCUMENTED, NOT YET IMPLEMENTED, 2026-09-04)

**Status: architecture reservation only, same discipline as §8.5.** Nothing described in this section exists in code today. Documented here, ahead of implementation and ahead of its own roadmap phase's actual build authorization (Engineering Roadmap Phase 8), so the committee/consensus/Strategy Engine layers already frozen (Milestones 4.x/5.1) are not designed in a way that makes absorbing this capability later structurally awkward.

**Purpose.** MANSA must learn how comparable historical/current context changes expected player and team performance, and propagate that impact across every market type it evaluates: player props, moneyline, spread, totals, and future intelligent/correlated parlays. Context includes, at minimum: weather (including changing in-game conditions where data permits), injuries/player availability, teammate dependency, QB/receiver combinations, lineup/depth-chart changes, opponent/matchup, venue/surface, home/away, rest/travel, role/usage, and game state/script.

**The one rule this section exists to enforce: do not treat isolated observations as patterns.** A single game where a backup receiver had a big day is an anecdote, not evidence of a repeatable context-driven effect. Every contextual claim this capability produces must be gated by real evidence quality, not narrative plausibility alone.

**Evidence requirements — every contextual-impact claim must consider:**
1. **Comparable sample size** — how many genuinely similar historical situations exist.
2. **Similarity** — how close the comparison situations actually are to the current one, not just superficially labeled the same (e.g. "windy game" covers a wide real range).
3. **Baseline performance** — the impact must be measured against the player/team's own normal baseline, not league average alone.
4. **Recency** — older comparable situations are weaker evidence than recent ones, especially where role/scheme/personnel has since changed.
5. **Uncertainty/confidence** — every output carries an explicit confidence/uncertainty signal, never a bare point estimate presented as fact.
6. **Relevant confounders, where supported** — e.g. a QB's poor performance in cold games might really be explained by which offensive line he had at the time, not the cold itself; this capability must disclose when a plausible confounder exists and can't be ruled out, rather than presenting a cleaner story than the evidence supports.

**"Insufficient comparable evidence" is a valid, expected output — never suppressed or papered over with a lower-confidence guess dressed up as an answer.** This mirrors §8.5's own "disclosed uncertainty over fabricated certainty" principle exactly, applied to performance context instead of market integrity.

**No numeric thresholds (minimum sample size, similarity cutoff, recency decay rate, confidence bands) are locked in by this entry** — per this project's own established practice (the Elite second-pass variance threshold history in §4.3, the Adaptive Weighting learning-rate/guardrail history in §6, and §8.5's own identical deferral immediately above), any such number must be derived once real accumulated comparable-situation data exists to validate it against, not invented ahead of that data. A future focused inspection, authorized separately from this entry, sets those numbers.

**Target flow:**

```
Raw data
  → Contextual Performance Intelligence
  → player/team impact (with sample size, similarity, recency, confidence, disclosed confounders)
  → Probability Modeling (§2.5)
  → market comparison
  → EV / Risk / Consensus (§4)
  → Recommendation (§9)
  → Grading / Continuous Learning (§6, §9.6)
```

**Architectural position — mirrors §8.5's placement reasoning, not a new pipeline shape.** This is explicitly **not a 22nd/23rd fan-out agent** whose narrative lean gets averaged into consensus — the evidence-quality requirements above (sample size, similarity, recency, confidence, confounders) are exactly the kind of reproducible computation Volume 2 §1.1's own principle assigns to deterministic application code, never to an LLM ("never delegate to an LLM what application code can compute"). The existing Context & Data Agents (§2.2: Injury Intelligence, Weather, Travel & Fatigue, Rest Days), Matchup & Form Agents (§2.3: Offensive/Defensive Matchup, Team Form, Player Prop Agent), and Decision & Advisory Agents (§2.5: Probability Modeling) already reason qualitatively over raw context today — **this capability does not replace them or duplicate their role.** It sits upstream, computing the reproducible, evidence-graded quantitative impact score those agents currently have to estimate narratively from raw inputs alone, the same relationship the Closing Line Movement Agent already has with the deterministic `LineMovementFeatures` module (`app/features/market.py`) it interprets rather than computes itself. **Likely home: a new deterministic module in `ai-orchestrator` (e.g. `app/features/contextual_performance.py`), alongside `app/features/market.py`, not a new worker and not a new agent** — consistent with §8.5's own "no new worker" decision for Market Integrity and with this codebase's every other comparable guardrail (Grading, Adaptive Weighting, the 0.55 confidence floor, the EV>0 gate). This placement is a recommendation for the future focused inspection to confirm, not a decision made here.

**Relationship to existing architecture — audited directly against the real, current schema and workers, not assumed (2026-09-04 pass):**

- **Real, usable append-only history exists today for several context factors**, each keyed and timestamped in a way this capability could query directly: `injury_reports` (injuries/availability), `weather_snapshots` (weather — pregame only, see the gap below), `depth_chart_snapshots` (lineup/depth-chart changes, teammate dependency, QB/receiver combinations — team-keyed, not game-keyed, per Volume 3 §4.1's own documented shape), `roster_memberships` (team-membership history), and `games.venue_lat`/`venue_long`/`venue_type` (venue, home/away, part of surface — see gap below). None of this is a new build; Phase 8 would be a genuinely new *consumer* of already-real data, not a new capture pipeline for these categories.
- **A confirmed, material gap: no play-by-play or game-event table exists anywhere in this schema.** `player_stats`/`team_stats` are captured once, from a single post-finalization provider payload (Postgame Ingestion Worker) — there is no quarter-by-quarter, drive-level, or play-level record of *how* a final stat line was produced. **"Game state/script" and any context factor that depends on in-game sequencing (e.g. "this back's usage collapsed once the team was down two scores") cannot be reconstructed at any depth from what this schema captures today**, for any game, past or future, unless that changes before the games are played (see the separate 2026 Data Preservation Requirement, `docs/ops/2026-data-preservation-requirement.md`, for the immediate/time-sensitive version of this same finding).
- **A confirmed, material gap: every context-relevant specialized worker (Odds, Player Props, Injury, Weather) stops polling a game at its own kickoff** (`app.workers.windows`'s `Window.STOPPED`, Volume 2 §8) — "weather, including changing in-game conditions where data permits" is a context factor this section explicitly names, but no in-game weather change, no in-game injury/inactive update, and no in-game odds movement is captured by any currently-running worker. This is the same underlying gap the Data Preservation Requirement documents as immediately time-sensitive.
- **A confirmed gap: playing surface (turf vs. grass) is not captured.** `games.venue_type` only distinguishes `outdoor`/`dome`/`retractable_dome`; no column carries surface type at all.
- **News has no history** (Phase 7 Milestone 7.0's own audit finding, unchanged) — a trade, suspension, or lineup-change news item's precise timestamp/content cannot be reconstructed once `daily_game_intelligence.news` is next overwritten. This directly weakens the "news as a contextual-intelligence input" connection this capability depends on (see below).
- **No "comparable situation" index exists anywhere** — `player_stats`/`team_stats`/`games` hold the raw material this capability needs, but nothing today computes, caches, or reuses a "find similar historical situations" query. This is new computation this capability would have to build, not a missing table alone.
- **Historical backfill depth is currently mixed and provider-dependent**, per the 2026-09-03 NFL provider bake-offs (`docs/ops/nfl-provider-bakeoff-2026-09-03.md`, `docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`): BALLDONTLIE reaches at least one prior season; API-SPORTS is restricted to 2022-2024 on the evaluated plan; MySportsFeeds' prior-season game listings were plan-restricted (403) on the evaluated key. "Comparable sample size" and "recency" both depend on how much real historical depth MANSA can actually backfill, which is not fully resolved by any single current provider.

**Connection to News (per HQ's explicit instruction, 2026-09-04): future architecture must allow material news — an injury, an inactive designation, a suspension, a lineup change, a trade — to update player/team context and ultimately affect applicable moneyline/spread/total/prop probabilities.** Today, News Worker's own output (`daily_game_intelligence.news`) is a current-state jsonb blob with no history and no structured event type — it cannot today feed a deterministic contextual-impact computation the way `injury_reports`/`depth_chart_snapshots` can, since there's no stable record of *when* a given news item first became true. Closing this gap (a structured, timestamped, categorized News event history) is a real prerequisite for the News → context connection this section anticipates, not something this entry builds or schedules — see the separate News cadence audit (`docs/ops/news-cadence-architecture-audit-2026-09-04.md`) for the adjacent News-provider-architecture work this connects to.

**No genuine architecture conflict was found** — this capability composes with real, already-append-only evidence (injuries, weather pregame, depth charts, roster history) for several of its named context factors, and cleanly identifies exactly which factors (in-game conditions, game state/script, news history, playing surface) have no data to compose with at all today, which is precisely what the Data Preservation Requirement below exists to close before it becomes unrecoverable.

---

## 9. Recommendation Strategy Engine

Decides the *shape* of the final output (single, prop, SGP, multi-game parlay, multiple singles, bankroll preservation, or no-bet) — this sits after Consensus/Meta Agent and before Explainability in the flow (Section 3.1, step 9; see that section's own note on the step-order correction). Implemented, deterministically, in `app.features.strategy` (ai-orchestrator) — persisted to the Phase 5 product layer, Volume 3 §5A.

**Finalized decision logic (v5.0, Phase 5 Milestone 5.1, Decisions X/Y/Z/AA/AB/AC/AM/AN, 2026-08-25) — supersedes the priority-order list this section previously carried, which predated Phase 4's candidate-anchored architecture and left several genuine ambiguities (EV vs. confidence dominance, exact tie-break behavior, the exact no_bet/bankroll_preservation boundary) explicitly open. Every ambiguity below was closed by Mac's own explicit ruling, not inferred:**

1. **Qualification — both gates required, neither alone sufficient:** a candidate qualifies only when `final_aggregate_confidence >= 0.55` (Section 4.2's floor) AND `ev_per_dollar > 0`. A high-confidence, zero/negative-EV candidate does not qualify; a positive-EV, below-floor candidate does not either.
2. **Ranking, tie-break, and same-market conflict resolution all use one hierarchy:** `ev_per_dollar` DESC, then `final_aggregate_confidence` DESC, then `candidate_key` ASC (purely for deterministic output, never a betting-quality signal). EV is the sole primary signal; confidence is a secondary tie-break only — there is no blended score.
3. **Same-market exclusivity:** at most one candidate per `(game, market_type)` survives for moneyline/spread/total — the two possible selections are opposing sides of one wager and can never both be selected. DB-enforced (Volume 3 §5A, `idx_recommendation_legs_one_per_market`), not merely a convention.
4. **`no_bet` is strictly per-game:** zero qualifying candidates for that specific game, independent of the rest of the slate.
5. **`bankroll_preservation` is strictly slate-wide:** zero qualifying candidates ANYWHERE in the entire slate that Master Refresh run covers — there is no partial-slate or percentage-threshold version of this outcome.
6. **`single` vs. `multiple_singles` is decided by the total count of selected legs across the whole slate, after same-market conflict resolution — not by game count.** Exactly one selected leg anywhere in the slate → `single`. Two or more → `multiple_singles`. One game may legitimately contribute more than one leg (e.g. a qualifying moneyline and a qualifying total are different markets, not opposing sides).
7. **`same_game_parlay`/`multi_game_parlay` remain schema-supported but INACTIVE** (Decision AD/AN, confirmed by a full-codebase grep: no joint-probability formula, no combined-EV formula, no correlation data, and no sportsbook parlay/SGP pricing exists anywhere in this codebase or any adapter). The Strategy Engine has no parlay branch at all as of Milestone 5.1, not a disabled one — activating parlays later is new work (correlation modeling, combined-variance math, parlay pricing), not a flag flip.

**Never force a shape onto the data** remains true and is now mechanically enforced rather than aspirational: the qualification gate in rule 1 is the actual mechanism that produces `no_bet`/`bankroll_preservation` as the honest default absent a real signal, not a policy statement layered on top.

**The market-mixing rule (v3.0) is preserved as written for the day parlays activate**, but does not apply to anything the Strategy Engine currently produces — `multiple_singles` presents each qualifying leg as its own separate bet by construction, never combined, so there is no "mix" to speak of until same_game_parlay/multi_game_parlay actually activate.

---

## 9.5 Bet Timing & Execution Intelligence (v5.5, FUTURE CAPABILITY — APPROVED / DOCUMENTED, NOT YET IMPLEMENTED, 2026-08-25)

**Status: architecture reservation only.** Nothing described in this section exists in code today.

**Purpose.** The Playbook should not universally recommend placing a bet immediately, nor universally recommend waiting until immediately before game time. Correct timing depends on current price, EV, line movement, unresolved information (injury status, lineup/inactive announcements, weather), market movement, data freshness, integrity/anomaly signals (§8.5), proximity to game start, and the risk that waiting causes the current favorable price to disappear. The Playbook's job therefore eventually extends beyond "what should I bet?" to "*when* should I bet it?"

**The three-question distinction this capability makes explicit, and which the architecture must not collapse into one question:**

- **ANALYSIS** — is this candidate fundamentally attractive? (Phase 4 committee/consensus, §2–§6)
- **STRATEGY** — should The Playbook recommend it at all? (§9, frozen per Milestone 5.1)
- **EXECUTION** — is the *current* price and *current* information state appropriate for acting *now*? (this section, future)

A recommendation may therefore exist while its execution state is WAIT — "good bet" and "good bet at this exact price and exact moment" are treated as genuinely different questions, never conflated into a single verdict.

**Core execution states (conceptual, future):**

- **BET NOW** — the candidate qualifies and the current market price is sufficiently attractive that waiting is not justified by currently unresolved information.
- **WAIT** — the candidate is promising/qualified or close to actionable, but meaningful information remains unresolved, or market conditions warrant additional observation. **WAIT is an active state, not "do nothing"** — the intended future loop is `recommendation identified → WAIT → automatic data/market refresh → re-evaluation → BET NOW / continue WAIT / PASS / LINE LOST`, triggered by (future, unscheduled) events such as a new odds snapshot, meaningful line movement, an injury-status change, an inactive/lineup announcement, a weather change, material news, an anomaly-state change (§8.5), or approaching game start. **The exact scheduling/event architecture for this loop is explicitly not chosen here** — it requires its own later execution-focused inspection, and likely depends on the event infrastructure Volume 2 §3 already lists as deferred post-MLP (`InjuryUpdated`, `WeatherChanged`, and similar consumers).
- **PASS** — the opportunity no longer satisfies The Playbook's requirements.
- **LINE LOST** — The Playbook previously identified an attractive opportunity, but the market moved enough that the original edge no longer exists at the currently available price (e.g. the original candidate was Team A -2.5; the current market is Team A -4.5). **The system must re-evaluate the CURRENT price and must never continue presenting the original recommendation as actionable merely because the earlier price was attractive.**

**Price sensitivity — a foundational principle for this capability, not yet enforced anywhere in the codebase today.** A recommendation is conditional on price: Team A -2.5 and Team A -5 are not necessarily the same opportunity. The Playbook must eventually preserve the activation-time price (already true today — `recommendation_legs.american_odds`/`.point`/`.decimal_odds` freeze this exactly, per Volume 3 §5A) and compare later observed prices against it, re-evaluating EV when the price materially changes. **No universal numeric threshold for what constitutes "LINE LOST" is invented here** — that requires a later, market-specific inspection, exactly the same discipline already applied to the Elite second-pass variance threshold (§4.3) and explicitly required again here.

**Integration with Market Integrity & Anomaly Intelligence (§8.5).** Market Integrity & Anomaly Intelligence feeds this capability, not the reverse. Example: a candidate still qualifies statistically, but `UNEXPLAINED MARKET MOVEMENT = ELEVATED` (§8.5) — Execution Intelligence may then return WAIT rather than BET NOW, without needing to know *why* the movement occurred. **This is a load-bearing architectural principle for both future capabilities: unknown information may change the action without the system inventing the missing explanation.**

**Relationship to existing architecture — inspected directly, not assumed:**

- **Recommendation lifecycle / withdrawal** (Volume 3 §5/§5A) already has the schema-level `status`/`withdrawn_at`/`withdrawal_reason` mechanism a PASS/LINE LOST transition would use — no new withdrawal mechanism is anticipated.
- **Master Refresh / Recommendation Worker** (Volume 2 §4.4, Milestone 4.9) currently run once per slate cycle, not continuously against live price movement — the "automatic re-evaluation" loop above is new scope, not something either currently does or was designed to preclude.
- **`market_monitoring_events`/`worker-market-monitor`** — same unbuilt foundation §8.5 depends on; this capability is a second, later consumer of the same eventual monitoring loop, not a duplicate of it.
- **Explainability (§8)** would need to surface, per historical decision point: what changed, why the state changed, what information remains unresolved, the originally-evaluated price, and the currently-available price — all of which are facts, not narrative, and therefore fit §8's existing deterministic-fact discipline without requiring new LLM capability.
- **Time Machine** (Volume 3 §5A's frozen-leg pattern, Milestone 5.3's snapshot mechanism) must eventually preserve, without overwriting: the original candidate, original price, original EV, original recommendation, original execution state, every subsequent market price observed, every state transition and its reason, and the anomaly/integrity signal state at each decision point. **This is a requirement on Milestone 5.3's design, not something Milestone 5.2/5.3 must build now** — but it must not be designed out. The append-only, frozen-at-write pattern already established for `recommendation_legs`/`user_recommendation_selections` (Milestone 5.1) is the direct precedent this future work would extend, not replace.
- **User experience** (Volume 5, future) would need BET NOW/WAIT/PASS/LINE LOST to read as genuinely different, understandable states — not new to this document's principles, but flagged so Volume 5's eventual design doesn't collapse them into one generic "recommendation" card.

**No genuine architecture conflict was found.** This capability depends on §8.5 (documented above) and on event/monitoring infrastructure that Volume 2 already named and deliberately deferred — it composes with that deferral rather than contradicting it.

---

## 9.6 Postgame Review Grading Engine (v5.8, Phase 5 Milestone 5.4, 2026-08-27)

**Deterministic grading first, always (Decision BI) — the grading engine, never an LLM, decides WIN/LOSS/PUSH/VOID_NO_ACTION/PENDING_MISSING_DATA/NOT_APPLICABLE.** `app.features.grading` (`apps/ai-orchestrator`) is a pure function of two already-frozen/already-authoritative inputs — the leg's own `market_type`/`selection`/`point` (Volume 3 §5A, immutable by construction: no UPDATE path exists anywhere in this codebase for `recommendation_legs`) and the game's authoritative final facts (`games.final_score`, once reconciliation-eligible, below) — never current market information, never an LLM judgment call. `GRADING_VERSION` is frozen onto every grade event (Volume 3 §5D) and stamped independently of `POSTGAME_REVIEW_VERSION` (Decision BN/BO) — the deterministic rules and the narrative-generation logic evolve on separate timelines.

**Supported markets today: moneyline, spread, total — deterministic push/win/loss rules, including the standard industry moneyline-tie-is-push rule.** `player_prop` is deliberately unsupported, not degraded (Decision BJ) — the grading dispatch already has a market-type branch reserved for it; a leg of that type is skipped entirely (no grade event written) rather than fabricating a settlement, exactly the "structurally extensible but inactive" treatment already given to other not-yet-built capabilities in this volume (§8.5, §9.5).

**Reconciliation-eligibility is the actual grading-readiness condition, not `games.status = 'final'` alone (Decision BH).** The Postgame Ingestion Worker's own bounded reconciliation window (Volume 2 §8) can still correct final stats for up to 72 hours after finalization — grading a `final` game waits until that window has elapsed (`games.finalized_at + 72h`, the same final checkpoint the ingestion worker's own schedule already uses) before treating `final_score` as authoritative. `postponed`/`canceled` games grade immediately as `VOID_NO_ACTION` — no reconciliation process exists for them to wait on.

**Per-leg, per-product grading (Decision BK) — `multiple_singles` is never treated as a parlay.** Each leg is graded independently, on its own game's own reconciliation timeline; a product-level rollup is computed only once every one of its legs has a terminal grade, and the rollup preserves every individual leg outcome (`leg_outcome_counts`) rather than collapsing them into a single win/loss. `no_bet` and `bankroll_preservation` are always `NOT_APPLICABLE` (Decisions BL/BM) — no Blueprint-approved rule exists yet for "was passing/abstaining retrospectively correct," so V1 does not invent one; the underlying candidate/game-decision data remains reconstructable for a future, explicitly-designed retrospective capability.

**Append-only correction/regrade (Decision BP), enforced at the database, never solved with application-memory-only bookkeeping (Decision BQ).** A stat correction or grading-rule change never overwrites a historical grade — it inserts a new row referencing the one it supersedes, DB-idempotency-enforced via a partial unique index on `(parent_id, grading_version) WHERE is_correction = false` (Volume 3 §5D).

**Postgame Review narrative (Decision BU) is strictly downstream of an already-persisted grade — the LLM cannot alter it, structurally, not by convention.** Execution order: authoritative reconciled result → deterministic grade → factual evidence/deltas → LLM narrative. The narrative model's own response contract (`PostgameReviewNarrativeOutput`) has exactly three string fields (`outcome_summary`/`why_it_won_or_lost`/`learning_notes`) — no field capable of representing a grade, EV, confidence, or historical Explainability value exists for it to populate. Routed through the same `ModelRouter`/`RetryEngine`/`AdapterRegistry` plumbing every committee agent already uses, gated on a `model_routing_rules` row for `task_type="postgame_review_narrative"` that does not exist yet (flagged as a required pre-live-narrative seed, same class of gap Milestone 4.8-6 closed for the 12 committee agents' own `prompt_registry` rows) — narrative generation is skipped, never defaulted to a guessed model, when that row is absent. `FakeModelAdapter` only through this milestone's own build and test suite; zero live OpenAI/Anthropic calls.

**Causal attribution is explicitly bounded (Decision BS).** The narrative layer may describe factual deltas ("wind increased from the activation snapshot to kickoff," "the quarterback was ruled out") but must never assert unsupported causation ("the wind caused the loss"). `factual_deltas` itself is conservatively `None` in this milestone — no activation-vs-kickoff snapshot-diffing infrastructure was built — an honest absence, never an approximation.

**Agent correctness (Decision BT) reuses this volume's own §4.1 `directional_agreement` three-state comparison verbatim** (`app.features.consensus.lean_factor`), applied against the REALIZED direction (derived from the already-computed grade: a WIN leg's realized direction is its own candidate direction; a LOSS leg's is the opposite) rather than a new/looser standard. An agent is never classified as wrong merely for disagreeing with the majority, having lower confidence, or the product losing overall — only a traceable comparison between that agent's own historical directional call and the realized outcome counts. Where no realized direction exists (push/void/pending), no agent is classified either way.

**Closing Line Value (CLV) remains unavailable (Decision BR).** `agent_performance_scores.clv` exists as a nullable column, but no closing-price-capture mechanism exists in `odds_snapshots` today — this milestone does not approximate a closing line from an arbitrary snapshot; CLV stays `NULL` until a real Market Monitoring/closing-price capability is built.

**Adaptive Agent Weighting boundary, unchanged from §6/§10 below (Decision BW).** This engine PRODUCES trustworthy historical grading evidence — it does not write `agents.current_weight`, does not populate `agent_performance_scores`, and does not activate the 200-sample guardrail. One open interpretation question is explicitly carried forward, not resolved here: what exactly counts as one "recommendation" toward the provisional 200-sample threshold (§6.1) under the modern Phase 5 product/leg architecture — a graded leg, a graded product, or the legacy Phase 4 cycle unit the roadmap's own guardrail text was originally written against.

---

## 9.7 Recommendation Lifecycle & Change Communication (v5.13, DESIGN LOCKED BY HQ 2026-09-04, NOT YET IMPLEMENTED)

**Status: architecture reservation only, design fully locked.** Nothing described in this section exists in code today, but every design decision below is now HQ-approved and binding, not merely proposed — HQ reviewed the original proposal and issued a same-day Decision Lock ratifying all seven items (full text: `docs/ops/recommendation-lifecycle-spec-2026-09-04.md`; schema counterpart, with the full seven-item recap: Volume 3 §5G's "HQ Decision Lock" subsection). **Approving the design is not authorization to build it** — implementation, migrations, UI, Telegram, grading, and worker code all remain untouched by this entry.

**The seven locked decisions, restated at this Volume's own level of detail:**
1. Lifecycle vocabulary (`STRENGTHENED`/`WEAKENED`/`NO_LONGER_QUALIFIES`/`REPLACED`) approved as proposed; `recommendation_products.status` stays binary.
2. `REPLACED` always creates a NEW `recommendation_products` row and a NEW `recommendation_activation_snapshots` row — never a mutation of the original.
3. Grading is now mandatory, ratified policy: an activated recommendation stays independently gradeable on its ORIGINAL frozen terms regardless of later `WEAKENED`/`WITHDRAWN`/`NO_LONGER_QUALIFIES`/`REPLACED` events; a replacement/reversal that itself activates is a SEPARATE, independently gradeable MANSA decision. This is HQ's own named mandatory protection against survivorship bias.
4. `user_recommendation_placements` approved — user-reported placement/exposure only, never sportsbook-verified; changes communication tone only, never grading, and must never imply MANSA can cancel/cash-out/hedge a wager.
5. `market_monitoring_events` is explicitly NOT implemented or extended by this capability now — Phase 7 remains solely responsible for Market Integrity signals; this section's `trigger_type` vocabulary (Volume 3 §5G) borrows the same value-strings without touching that table.
6. Milestone 5.6 (Engineering Roadmap) approved as a mandatory pre-Beta milestone, phased: basic lifecycle mechanics may be built ahead of Phase 7/8, but the milestone cannot be considered complete until real Phase 7/Phase 8 signals can actually feed it.
7. Dashboard behavior locked at the principle level — a materially changed recommendation must never silently disappear or overwrite its previous state, on any surface. Exact visual treatment remains a future implementation/design decision.

**Purpose, and the exact gap this closes.** §9's Strategy Engine decides what to recommend once, at activation. §9.5 (above) asks whether the *current price* is still right to act on. §9.6 asks how a finished game gets graded. **None of the three answers HQ's actual question: when new information arrives between activation and kickoff (an injury, a lineup change, weather, a market move, a News item, a Phase 8 contextual-intelligence signal, or simply a routine model/Strategy recompute surfacing a different result), how does MANSA communicate that its own view changed, without ever rewriting or erasing what it originally said?** HQ's own worked example: 10:00 AM, MANSA recommends Team A -3 at positive EV; 11:30 AM, WR1 is ruled out, the projection changes, the market moves, MANSA no longer recommends Team A. **The 10:00 AM recommendation must remain permanently visible in Time Machine, unedited** — the same non-negotiable already proven for `recommendation_legs`' own 100%-immutable design, extended here to the narrative layer sitting on top of it.

**Core principle.** Once `recommendation_products` is activated, the original activated recommendation and its later change (if any) are both preserved, always — never one overwriting the other. This is not a new invention: it is the same append-only discipline already governing every table in the Phase 5 product/leg/explanation/grading layer, applied for the first time to the *communication* of a change rather than only to the underlying data.

**Proposed lifecycle vocabulary (Volume 3 §5G) — extends, never replaces, the existing three-state event log.** `recommendation_product_lifecycle_events.event_type` already has `ACTIVATED`/`WITHDRAWN`/`SOFT_DELETED` (Milestone 5.3, live). Proposed additions: `STRENGTHENED` (new evidence increased confidence, still active), `WEAKENED` (new evidence reduced confidence, still active — HQ's 11:30 AM moment before a formal withdrawal decision), `NO_LONGER_QUALIFIES` (a re-check against §9's own frozen `>= 0.55` / `> 0` qualification rule failed — the *reason* a `WITHDRAWN` event is about to fire or just fired, not a substitute for it), and `REPLACED` (superseded by a separately-activated new product — a reversal is always a second, independent activation, never a mutation of the first, preserving `recommendation_products`' "one row, one immutable decision" invariant exactly as designed).

**Trigger vocabulary — reused, not invented, per HQ's own explicit instruction.** `market_monitoring_events.event_type` (Volume 3 §7) already has `'line_movement'`, `'injury_update'`, `'weather_change'`, `'lineup_change'`, `'breaking_news'` — this is the correct existing vocabulary for four of HQ's five named trigger categories (injuries/inactives, lineup/depth-chart, weather, market movement/odds deterioration, new news), and Volume 3 §5G proposes reusing it verbatim as a new `trigger_type` column on the lifecycle event log. Two genuinely new categories are added, since HQ's own list names them and no existing vocabulary covers them: **`contextual_intelligence_change`** (Volume 4 §8.6, Phase 8, not yet built) and **`model_refresh`** (a routine Strategy/consensus recompute — e.g. an Elite second-pass reconciliation, §4.3 — surfacing a materially different result against unchanged inputs). **`market_monitoring_events` itself remains zero-rows/zero-code, and HQ's 2026-09-04 Decision Lock explicitly confirms this section does not implement or extend it now** — Phase 7 remains its sole owner. `trigger_type` is a separate CHECK constraint on this section's own event table that borrows the same value-strings for consistency; it creates no dependency on `market_monitoring_events`'s schema and requires no Phase 7 code to exist before this section's own schema can be built. Real signals populating `trigger_type` for `line_movement`/`injury_update`/`weather_change`/`lineup_change`/`breaking_news` do, however, require Phase 7's detection worker to actually exist — this is exactly the Milestone 5.6 completion condition (below): the schema can be built early, but the milestone only CLOSES once Phase 7 (and Phase 8, for `contextual_intelligence_change`) can genuinely feed it.

**No new numeric re-evaluation engine — this is a load-bearing restriction, not an oversight.** A `WEAKENED`/`STRENGTHENED`/`NO_LONGER_QUALIFIES` event may carry a qualitative, factual `trigger_event_data` payload (what changed — a player ruled out, a line move) but must never carry a fabricated new `ev_per_dollar`/`final_aggregate_confidence` number. No automatic re-evaluation loop exists yet — that capability is §9.5's own explicitly future, unscheduled "recommendation → WAIT → automatic refresh → re-evaluation" mechanism, which itself still requires the event infrastructure Volume 2 §4.5 already named and deferred. If and when that engine is eventually built, a genuine re-evaluation produces a NEW activated `recommendation_products` row (an `ACTIVATED` + `REPLACED` pair against the old one), never a retrofitted number on the original — the same principle §9.5 already established for LINE LOST, extended here to non-price triggers.

**User-facing behavior — never silent disappearance.**
- **Time Machine already gets most of this right today, by design, not by accident.** Volume 5 §5's `HistoryJourneyProps.whatChanged` stage already renders `lifecycleEvents: { eventType: 'ACTIVATED' | 'WITHDRAWN' | 'SOFT_DELETED'; timestamp; reason }[]`, defaults to "No material changes recorded" rather than disappearing, and — per Volume 5's own Milestone 4 "temporal integrity" rule — Stage 1 (`whatWeRecommended`) is already structurally forbidden from rendering the product's *current* status/grade; those facts appear only in `whatChanged`/`whatHappened`. **This is the exact "preserve original, surface change separately" principle HQ's directive asks for, already built for Time Machine's historical view.** The only gap is vocabulary: the union type needs the four new values above, and a `trigger`/`relatedRecommendationProductId` field to render `REPLACED`'s forward/backward linkage.
- **Dashboard (live view) principle locked, exact visual treatment still open (HQ Decision Lock, 2026-09-04).** Volume 5 still documents no concrete behavior for a product transitioning `active → withdrawn` (or gaining a `WEAKENED`/`STRENGTHENED` event) while still live on `/today` — that remains a genuine, disclosed implementation-design gap. What is now locked: **a materially changed recommendation must never silently disappear or overwrite its previous state**, on this or any other surface. At minimum, an honest state change (e.g. "Updated 11:30 AM — see what changed") replacing the original card's content, never a card that simply vanishes — the exact visual/interaction design is left to a future Phase 6-adjacent UX pass.
- **Telegram/future alerts carry a Telegram-specific risk this document flags explicitly: a bot CAN edit or delete its own prior message.** Whatever future Telegram Companion is eventually built (still fully unbuilt, per this Volume's §7/Volume 5 §7 confirmation), a lifecycle-change event on a product a user was already alerted about must always be a NEW, threaded follow-up message, never an edit or deletion of the original alert — the chat-surface-specific instance of "never rewrite what MANSA already said."
- **"Placed" status changes the *tone*, never the *facts*, of any of the above.** Volume 3 §5G proposes a new standalone `user_recommendation_placements` table (a user's own self-report; MANSA has no sportsbook integration to infer this). Once a placement row exists for a product, any subsequent lifecycle-change communication on it must shift from actionable framing ("we no longer recommend this") to informational-only framing ("this information is for your awareness — MANSA cannot cancel, hedge, or cash out a sportsbook wager"), per HQ's explicit instruction not to assume any such capability exists. Nothing about grading or Track Record changes based on placement status — placement is a communication-tone signal only.

**Grading / Track Record — the survivorship-bias question HQ asked directly, now a locked, mandatory policy, not a proposal.** Answered here, mechanism in Volume 3 §5G: **yes, an activated recommendation remains gradeable even if later withdrawn** — confirmed by direct inspection of `apps/ai-orchestrator/app/{persistence,orchestration}/postgame_grading.py` during the original pass: no read function or grading path filters by `recommendation_products.status`, so a withdrawn product's legs are already graded exactly like an active one's, on their frozen activation-time terms. **HQ's 2026-09-04 Decision Lock ratifies this as mandatory policy (grading is status-blind by design)**, not left as an accidental property of the read layer — closing the exact loophole that would otherwise let withdrawing a recommendation improve MANSA's own record. Grading always reads the ORIGINAL frozen `recommendation_legs` row — never a later `WEAKENED`/`STRENGTHENED` observation, which per the restriction above never carries a number to grade against anyway. A `REPLACED` reversal counts as two independent graded observations in Track Record, never collapsed into one — HQ's own words: "a replacement/reversal that is activated is a separate independently gradeable MANSA decision." **The existing 72-hour finality gate (§9.6, `RECONCILIATION_WINDOW_HOURS = 72`) is unchanged and fully orthogonal** — lifecycle events never affect grading-eligibility timing.

**Relationship to §9.5 (Bet Timing & Execution Intelligence) — two axes, deliberately not merged.** §9.5 asks "is the current price right to act on now" (EXECUTION); this section asks "has MANSA's own analytical view of the underlying call changed" (ANALYTICAL VALIDITY / COMMUNICATION) — a market move can trigger either or both (a `LINE LOST` execution transition and a `WEAKENED` lifecycle event can both be true of the same product at the same moment, for different reasons), but neither this section nor §9.5 is a special case of the other, and no code path is proposed that would need to resolve one into the other. §9.5's own prior note — "Recommendation lifecycle / withdrawal already has the schema-level mechanism a PASS/LINE LOST transition would use — no new withdrawal mechanism is anticipated" — remains accurate: this section's new event types sit alongside `WITHDRAWN`, they do not replace it, and a future §9.5 implementation would still fire the same `WITHDRAWN` event it already anticipated, optionally now also tagged `trigger_type='line_movement'`.

**Beta dependency (HQ's own explicit framing, 2026-09-04, now locked as Milestone 5.6, phased): this behavior must be settled before Phase 12 (Beta)** — real recommendations will change between morning analysis and kickoff during any live beta cohort, and an unhandled silent-disappearance case would directly damage the Time Machine reproducibility claim Beta's own acceptance criteria already depend on (Phase 12, Volume 1 Journey 3). **Phasing, per the Decision Lock:** basic lifecycle mechanics (the schema above, the vocabulary, `user_recommendation_placements`) may be implemented ahead of Phase 7/Phase 8 — none of it structurally requires either to exist. Milestone 5.6 cannot be considered CLOSED, however, until real Phase 7 (`market_monitoring_events`-sourced) and Phase 8 (contextual-intelligence) signals can actually feed `trigger_type` — a lifecycle-communication capability that can only ever produce `model_refresh`-triggered events, with no real market/injury/weather/lineup/news signal behind any of the others, would not satisfy HQ's own stated purpose for this milestone. See the Engineering Roadmap's own updated Phase 5/Phase 12 entries, same date.

**No genuine architecture conflict was found.** This capability composes with §9.5's own future automatic re-evaluation loop and the same Volume 2 §4.5 event infrastructure it already depends on, reuses Volume 3 §7's `market_monitoring_events` vocabulary rather than duplicating it, and extends Volume 5's already-correct Time Machine temporal-integrity design rather than contradicting it.

---

## 10. Continuous Learning Engine (Closes the Loop)

```
games.status → 'final'
      │
      ▼
is_reconciliation_complete? (Postgame Ingestion Worker, Volume 2 §8) --
  the actual grading-readiness gate, not the raw status transition alone (§9.6)
      │
      ▼
Postgame Review Grading Engine (§9.6) writes deterministic per-leg/per-product
  grades (Volume 3 §5D) -- NOT the legacy postgame_reviews (Volume 3 §7, unbuilt)
      │
      ▼
correct_agents / underperforming_agents identified per graded product (§9.6)
      │
      ▼
per-agent classifiable observations aggregated into a PROPOSED weight
  evaluation (Section 6, Volume 3 §5E's adaptive_weight_proposals) --
  sample-size and 90-day-window guardrails enforced, NOT agent_performance_scores
  (that table's only 2 rows predate this architecture and are disregarded)
      │
      ▼
proposal persisted append-only; agents.current_weight is NEVER
  automatically written (PROPOSE-ONLY V1, Milestone 5.5) -- promotion into
  agents.current_weight is a separate, NOT YET AUTHORIZED future capability
      │
      ▼
next recommendation cycle continues using whatever weight is
  CURRENTLY in agents.current_weight, unaffected by any proposal
```

**Status as of Milestone 5.5: every step through "proposal persisted append-only" is built and fixture-proven; the loop still does not close.** Milestone 5.4 produces the graded evidence; Milestone 5.5 produces a fully-computed, guardrail-checked, historically-traceable PROPOSAL of what each agent's weight would become — but `agents.current_weight` itself is never touched by any code in either milestone. Promoting a proposal into a real weight change is a separate, not-yet-authorized future capability (propose-then-promote, per explicit instruction not to assume autonomous mutation is desirable merely because the feature is named "Adaptive"). This is intentionally a slow, guarded loop — the master spec's "evaluate agents over thousands of recommendations... prevent overfitting" instruction is why every step above has a minimum-evidence gate before it's allowed to change live behavior, and why even a fully-computed proposal still requires a further, deliberate step before it can. Speed is not the goal here; a system that reacts too quickly to short-term results — or that automatically acts on its own conclusions before they've been reviewed — is exactly the failure mode this section exists to prevent.

---

## 11. Evaluation Methodology (Pre-Launch)

Before any of this goes live with real users, recommend backtesting the full agent committee and consensus logic against at least one full prior NFL season of historical data, specifically checking:
- Does the confidence calibration hold up out-of-sample (Section 5)?
- What's the actual historical frequency of "No Bet Today" days at the 0.55 threshold — too rare (system never holds back) or too frequent (system is uselessly conservative) both indicate the threshold needs tuning before it's ever tuned live on real users?
- Does the adaptive weighting algorithm converge sensibly when run against a full season of postgame data, or does it oscillate?

This backtesting phase is a concrete, sizable engineering task in its own right and should be scoped as its own milestone before public launch, not treated as a footnote to Volume 4.

---

## 12. Open Decisions Carried to Later Volumes

- **Recommendation detail screen** must surface every row in Section 8's explainability table — Volume 5 owns the layout.
- **Chat interface** (Volume 5) needs to render `conversation_messages` naturally, including showing which recommendation a message is linked to.
- **No Bet Today / Bankroll Preservation UI states** are two distinct states per Section 9, not one generic empty state — this was flagged generally in Volume 1 and is now a specific, named requirement for Volume 5.
- **0.55 confidence threshold and ±10% max weight change** are launch defaults, not final — flag for a MINOR version bump once backtesting (Section 11) produces real numbers.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 4 added. Updated to v2.0, 2026-08-05, per external architecture review — Meta Agent (§2.6) and `evidence_classification` (§2.1, §4.1) integrated into the committee and consensus logic described above, not just noted in the version header. Updated to v3.0, 2026-08-05 — Kelly Criterion (§2.5), session memory and progressive disclosure (§7), and explicit parlay market-mixing (§9) integrated directly. Updated to v4.0, 2026-08-06 — dual entry points (proactive Recommendation Worker + on-demand NL Engine) integrated into §3.1, per the internal markdown-consistency review.
