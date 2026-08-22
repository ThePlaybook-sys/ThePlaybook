# The Playbook — Volume 4
## AI Intelligence Architecture: Agents, Orchestration, Consensus, Explainability, Learning

**Version:** v5.1
**Last updated:** 2026-08-22
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
9. Explainability Engine formats the package into the question-answer structure (Section 8)
10. Recommendation Strategy Engine decides final output shape (Section 9)
11. Package + full snapshot written to recommendation_snapshots (Volume 3 §5)
```

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

**A real, freshly-discovered mathematical tension in this section's own numbers, flagged rather than silently resolved:** `agreement_variance` (no formula given anywhere in this volume or Volume 3) is implemented as the population variance of the `directional_agreement[i]` values among voting agents. With only two possible values (`1.0`, `0.3`), the maximum possible variance of any real distribution is `p(1-p)(1.0-0.3)^2`, maximized at a 50/50 split: `0.25 × 0.49 = 0.1225` — meaning §4.3's own `agreement_variance > 0.25` Elite second-pass trigger can never fire from any real computed input, under this section's own specified `0.3` fractional penalty, independent of the candidate-anchoring change above (the original game-level majority-vote formula has the identical two-value ceiling). This is an open question for a future decision — whether the fractional penalty, the 0.25 threshold, or the variance formula itself should change — not resolved in this pass. See `CHANGELOG.md` v4.15/v5.1 entries and `PROGRESS.md`'s Milestone 4.7 entry for the full reasoning and options.

**v2.0 addition — evidence-classification discount:** before the formula above runs, any agent whose `evidence_classification` (§2.1) is `assumption` contributes at 0.5× its normal `current_weight[i]` for that specific calculation only — this is a per-recommendation discount, not a permanent change to the agent's stored weight. A single assumption-heavy finding shouldn't carry the same force as a data-backed one, but shouldn't be discarded either, since informed inference is often legitimately useful.

**v2.0 addition — Meta Agent adjustment:** after `aggregate_confidence` is computed, the Meta Agent (§2.6) runs and produces `final_aggregate_confidence = aggregate_confidence + confidence_adjustment`, where `confidence_adjustment` is always ≤ 0. This final, possibly-lowered number is what feeds §4.2's threshold check, never the pre-adjustment value.

### 4.2 "No Bet Today" Threshold

Recommend a hard floor: **final_aggregate_confidence < 0.55 → automatic "No Bet Today,"** regardless of EV. This number should not be treated as sacred on day one — it needs backtesting against historical data before launch and should be one of the first things the Continuous Learning Engine (Section 10) is allowed to adjust, but only via the same sustained-evidence process as agent weights, never on a single bad week.

**Phase 4/5 boundary (Milestone 4.7):** this threshold's result is computed and persisted as an internal analytical fact (`consensus_snapshots.below_confidence_floor`) — this is NOT the same action as producing a user-facing "No Bet Today" recommendation object. Section 9's Recommendation Strategy Engine (Phase 5) alone decides `recommendations.recommendation_type`; Phase 4 never sets it, never sets `status = active`, and never assembles a `recommendation_snapshots` row.

### 4.3 Elite-Tier Second-Pass Reconciliation

**This resolves the open item flagged in Volume 2 §7.** Recommend: if `agreement_variance > 0.25` (meaning agents meaningfully disagree, not just noisy confidence scores) **and** the user's tier is Elite, trigger a second reasoning pass using the strongest routed model, explicitly given all 21 fan-out agents' raw outputs plus the Meta Agent's `reasoning` field, and asked to reconcile the disagreement rather than just re-run the math. Free/Pro tier requests accept the first-pass consensus even under high variance, which is the concrete difference Volume 1's "priority agent compute" pricing language needs. Log `second_pass_triggered = true` (Volume 3 §5) every time this fires — this becomes a measurable feature-usage metric, not just a marketing claim.

**v5.1 — dedicated reconciliation contract (Milestone 4.7):** the second pass's output is a small, dedicated contract (candidate identity, reconciliation reasoning, `confidence_adjustment`, supporting evidence, `would_change_mind_if`) — deliberately NOT the Meta Agent's own `MetaAgentOutput` (§2.6). The two review a candidate's consensus for different reasons and stay semantically separate. Same hard rule as the Meta Agent's: `confidence_adjustment` can only ever be zero or negative, enforced at construction time. **See §4.1's v5.1 note for the real mathematical ceiling that makes this section's own `> 0.25` threshold currently unreachable from any real computed `agreement_variance`** — the trigger logic itself is implemented and tested correctly in isolation; the threshold's practical reachability is an open question, not resolved here.

---

## 5. Confidence Calibration

Confidence scores are only useful if a 0.7 actually means "right about 70% of the time" — otherwise they're just decoration. Calibration is measured, not assumed:

- Bucket historical recommendations by confidence score (e.g., 0.55–0.60, 0.60–0.65, etc.)
- For each bucket, compute actual win rate against that bucket
- A well-calibrated system shows actual win rate tracking the bucket's confidence range; systematic drift (e.g., 0.70-confidence bets winning 55% of the time) means the Probability Modeling Agent is overconfident and needs recalibration

This calculation is exactly what `agent_performance_scores.confidence_calibration_score` (Volume 3 §5) stores per agent, and the same calculation applies at the system level against `ai_performance` (Volume 3 §6). Recommend running this as a scheduled worker job (Volume 2 §4.4) on a rolling basis, not just pre-launch.

---

## 6. Adaptive Agent Weighting

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

## 9. Recommendation Strategy Engine

Decides the *shape* of the final output (single, prop, SGP, multi-game parlay, multiple singles, bankroll preservation, or no-bet) — this sits after Consensus and before Explainability in the flow (Section 3.1, step 9).

**Decision logic, in priority order:**
1. If `final_aggregate_confidence < 0.55` → `no_bet` (Section 4.2), regardless of anything else.
2. If exactly one game/market clears the confidence floor with strong EV → `single`.
3. If multiple *independent* high-confidence legs exist within the user's `max_parlay_legs` (Volume 3 §3) → `same_game_parlay` or `multi_game_parlay`, but only if the Risk Manager confirms the combined variance is appropriate for the user's stated risk tolerance — never assembled purely because multiple legs are available.
4. If several unrelated high-confidence single bets exist but combining them would only add variance without EV benefit → `multiple_singles`, explicitly presented as separate bets rather than bundled.
5. If market conditions are broadly unfavorable across the board (not just one game) → `bankroll_preservation`, a distinct status from a per-game `no_bet`, meant to message "sit out today entirely" at the portfolio level.

**Never force a shape onto the data.** This is the master spec's most repeated instruction across the whole document, and it's worth stating plainly here as an actual rule the engine enforces: the default output, absent a clear signal, is always the more conservative option in this ordering — no_bet over single, single over parlay.

**Parlays freely mix market types (v3.0, explicit confirmation of previously-implicit behavior).** When a parlay shape (rule 3 above) is selected, individual legs are never restricted to one market type. A single parlay can combine moneyline, spread, totals, and player props (passing yards, anytime TD, strikeouts, points, assists, etc.) in whatever combination the Consensus Engine's highest-confidence findings support — this was already implied by the Player Prop Agent existing as a full committee member (§2.3), but is now an explicit rule: mixing markets whenever it improves expected value is default behavior, not a special case requiring separate logic.

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
