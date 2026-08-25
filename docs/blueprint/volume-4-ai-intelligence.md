# The Playbook — Volume 4
## AI Intelligence Architecture: Agents, Orchestration, Consensus, Explainability, Learning

**Version:** v5.5
**Last updated:** 2026-08-25

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

Volume 2 defined *how the Orchestrator is deployed* (stateless, async, horizontally scalable). Volume 3 defined *where its outputs are stored* (snapshot tables, append-only history). This volume defines *what it actually thinks* — the 22-agent committee (21 fan-out agents plus the Meta Agent reviewer, v2.0), how their outputs get reconciled into one recommendation, how confidence is calibrated, and how the system gets smarter over thousands of recommendations without overfitting to noise.

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
11. Package + full snapshot written to recommendation_snapshots (Volume 3 §5)
```

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

Resist the urge to remove a chronically low-weighted agent entirely. A near-zero weight already neutralizes its influence on the consensus; removing it destroys the historical record needed for `postgame_reviews.underperforming_agents` (Volume 3 §7) and any future re-evaluation if conditions change (e.g., a Referee Tendencies Agent that's been unreliable for years could become relevant again after a rule change). Weight toward zero, don't delete.

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

---

## 8.5 Market Integrity & Anomaly Intelligence (v5.5, FUTURE CAPABILITY — APPROVED / DOCUMENTED, NOT YET IMPLEMENTED, 2026-08-25)

**Status: architecture reservation only.** Nothing described in this section exists in code today. It is documented here, ahead of implementation, specifically so that Milestone 5.1's frozen Strategy Engine and Milestone 5.2's Explainability Engine are not designed in a way that would make adding this capability later structurally awkward or impossible.

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

- **`market_monitoring_events` (Volume 3 §7)** already exists as live schema and is the natural future data sink for this capability — its `event_type` vocabulary (`line_movement`, `injury_update`, `weather_change`, `lineup_change`, `breaking_news`) and `action_taken` vocabulary (`none`, `updated`, `withdrawn`) already anticipate exactly the "detect a change, decide whether it affects an existing recommendation" shape this capability needs. **Confirmed by direct inspection: this table has zero rows and zero code anywhere references it** — it is unbuilt Phase-1 schema, not a working capability today.
- **`worker-market-monitor` (Volume 2 §4/§5)** is a provisioned Railway service with **no application code at all** — confirmed by a direct repository search (no file anywhere implements it, unlike `worker-scheduled`, which Milestone 4.9 built out for the Recommendation Worker). It is the intended future home for this capability's live monitoring loop.
- **Closing Line Movement Agent** (§2.4, built in Milestone 4.4) already computes how a line has moved since open from `odds_snapshots` history — this is a real, existing signal this future capability would consume as one input, not duplicate. It answers "how has the line moved," not "is this movement explained" — the anomaly layer's job is the second question.
- **`odds_snapshots`** (Volume 3 §4) already holds the full historical price series needed to detect movement; no new raw-data table is anticipated.
- **Recommendation withdrawal** (`recommendations.status='withdrawn'`/`withdrawn_at`/`withdrawal_reason`, Volume 3 §5; mirrored in `recommendation_products` per Volume 3 §5A) already has the schema-level mechanism a SEVERE integrity finding would use to suppress a recommendation — no new withdrawal mechanism is anticipated, only a new trigger for using the existing one.
- **Strategy Engine / Explainability / Time Machine** — see the two subsections above and below; no duplication of responsibility identified, only new upstream input and new downstream disclosure obligations once built.

**No genuine architecture conflict was found** — this capability composes with existing, mostly-unbuilt scaffolding (`market_monitoring_events`, `worker-market-monitor`) rather than requiring any of it to be redesigned.

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

## 10. Continuous Learning Engine (Closes the Loop)

```
games.status → 'final'
      │
      ▼
worker-scheduled generates postgame_reviews (Volume 3 §7)
      │
      ▼
correct_agents / underperforming_agents identified per recommendation
      │
      ▼
aggregated into agent_performance_scores over the evaluation window
      │
      ▼
adaptive weighting algorithm (Section 6) updates agents.current_weight,
  subject to sample-size and max-change guardrails
      │
      ▼
next recommendation cycle uses updated weights
```

This is intentionally a slow, guarded loop — the master spec's "evaluate agents over thousands of recommendations... prevent overfitting" instruction is why every step above has a minimum-evidence gate before it's allowed to change live behavior. Speed is not the goal here; a system that reacts too quickly to short-term results is exactly the failure mode this section exists to prevent.

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
