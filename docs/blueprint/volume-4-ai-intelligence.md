# The Playbook — Volume 4
## AI Intelligence Architecture: Agents, Orchestration, Consensus, Explainability, Learning

**Version:** v2.0
**Last updated:** 2026-08-05
**Depends on:** Volume 2 (v2.0 — Orchestrator deployment shape, async fan-out pattern, scoped event system) and Volume 3 (v2.0 — `agents`, `agent_performance_scores`, `recommendation_agent_outputs`, `consensus_snapshots`, `model_routing_rules`, `prompt_registry`, `model_registry` tables)
**Resolves open items from:** Volume 2 §7 (confidence variance threshold), Volume 3 §13 (agent weighting algorithm, conversation schema)
**v2.0 note:** Amended per external architecture review — committee is now 22 agents (Meta Agent added as a post-consensus reviewer, not a fan-out participant); shared agent output contract (§2.1) extended with `evidence_classification` for hallucination/assumption discounting. See `v2.0-amendments-architecture-review.md` §1.9–1.10 for full detail.
**Read next:** Volume 5 (Frontend & UX Architecture) — every output defined here needs a home on a screen

---

## 1. How This Volume Fits

Volume 2 defined *how the Orchestrator is deployed* (stateless, async, horizontally scalable). Volume 3 defined *where its outputs are stored* (snapshot tables, append-only history). This volume defines *what it actually thinks* — the 21-agent committee, how their outputs get reconciled into one recommendation, how confidence is calibrated, and how the system gets smarter over thousands of recommendations without overfitting to noise.

This is the largest and most important volume in the blueprint. It's also the one place where a bad decision is hardest to detect early — a flawed pricing tier is obvious in week one; a flawed weighting algorithm can look fine for months and then quietly erode the whole product's credibility. Every section below is written with that risk in mind.

---

## 2. The Agent Committee

Twenty-one independent agents, organized into four functional groups. Every agent receives the same base game snapshot (from the Sports Intelligence Layer, Volume 2 §8) and independently returns a structured output — never prose alone.

### 2.1 Shared Agent Output Contract

Every agent, regardless of category, returns the same base shape, stored in `recommendation_agent_outputs.raw_output` (Volume 3 §5):

```json
{
  "agent_name": "injury_intelligence_agent",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}
```

**Why every agent must include `would_change_mind_if`:** this single field is what makes the Explainability Engine's "what would invalidate this recommendation?" question (Section 8) answerable without inventing an explanation after the fact. It's collected at the moment of analysis, not reconstructed later — which matters for reproducibility (Volume 3's Time Machine principle applies to *reasoning*, not just data).

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

---

## 3. Orchestration Logic

### 3.1 Execution Flow

```
1. Sports Intelligence Layer produces a game snapshot (Volume 2 §8)
2. Orchestrator reads model_routing_rules (Volume 3 §8) for each agent's task_type
3. Context & Data Agents + Matchup & Form Agents + Market Agents execute
   in parallel (async fan-out, Volume 2 §7) — 17 agents, one wave
4. Probability Modeling Agent executes, consuming all 17 outputs
5. Expected Value Agent executes, consuming Probability Modeling output + current odds
6. Risk Manager + Bankroll Coach execute in parallel, consuming EV output + user profile
7. Consensus Engine resolves the full set into one recommendation package
8. Explainability Engine formats the package into the question-answer structure (Section 8)
9. Recommendation Strategy Engine decides final output shape (Section 9)
10. Package + full snapshot written to recommendation_snapshots (Volume 3 §5)
```

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

### 4.2 "No Bet Today" Threshold

Recommend a hard floor: **aggregate_confidence < 0.55 → automatic "No Bet Today,"** regardless of EV. This number should not be treated as sacred on day one — it needs backtesting against historical data before launch and should be one of the first things the Continuous Learning Engine (Section 10) is allowed to adjust, but only via the same sustained-evidence process as agent weights, never on a single bad week.

### 4.3 Elite-Tier Second-Pass Reconciliation

**This resolves the open item flagged in Volume 2 §7.** Recommend: if `agreement_variance > 0.25` (meaning agents meaningfully disagree, not just noisy confidence scores) **and** the user's tier is Elite, trigger a second reasoning pass using the strongest routed model, explicitly given all 21 raw outputs and asked to reconcile the disagreement rather than just re-run the math. Free/Pro tier requests accept the first-pass consensus even under high variance, which is the concrete difference Volume 1's "priority agent compute" pricing language needs. Log `second_pass_triggered = true` (Volume 3 §5) every time this fires — this becomes a measurable feature-usage metric, not just a marketing claim.

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
1. If `aggregate_confidence < 0.55` → `no_bet` (Section 4.2), regardless of anything else.
2. If exactly one game/market clears the confidence floor with strong EV → `single`.
3. If multiple *independent* high-confidence legs exist within the user's `max_parlay_legs` (Volume 3 §3) → `same_game_parlay` or `multi_game_parlay`, but only if the Risk Manager confirms the combined variance is appropriate for the user's stated risk tolerance — never assembled purely because multiple legs are available.
4. If several unrelated high-confidence single bets exist but combining them would only add variance without EV benefit → `multiple_singles`, explicitly presented as separate bets rather than bundled.
5. If market conditions are broadly unfavorable across the board (not just one game) → `bankroll_preservation`, a distinct status from a per-game `no_bet`, meant to message "sit out today entirely" at the portfolio level.

**Never force a shape onto the data.** This is the master spec's most repeated instruction across the whole document, and it's worth stating plainly here as an actual rule the engine enforces: the default output, absent a clear signal, is always the more conservative option in this ordering — no_bet over single, single over parlay.

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

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 4 added.
