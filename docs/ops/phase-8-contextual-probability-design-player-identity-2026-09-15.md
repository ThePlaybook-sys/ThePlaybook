# Phase 8 Contextual Probability Design + Player Identity (2026-09-15)

MANSA HQ directive: "PHASE 8 CONTEXTUAL PROBABILITY DESIGN + PLAYER
IDENTITY." Two objectives: (A) close the player-identity gap for real
player candidates, if an authoritative source exists upstream; (B)
define HOW admitted context is allowed to influence modeled probability.
**Zero code changes this pass** -- Part A concludes with a confirmed,
specific blocker rather than inventing scope; Part B-E are design/audit
work, and the directive's own instruction ("do not implement numeric
probability adjustments in this pass unless the method already exists...
and requires no invented calibration") applies with no exception found.

---

## Part A -- Structured Player Identity

### 1. Player-identity gap result: **BLOCKED, confirmed, not a schema
problem -- the upstream capability does not exist at all yet.**

Audited the entire real `MarketCandidate` construction path, not
assumed:

- **The one and only real production construction site**
  (`grep -rn "MarketCandidate(" app/` across all of `apps/ai-orchestrator`,
  excluding tests) is `app/features/candidate_generation.py`'s
  `generate_candidates_for_game`.
- **That module's own docstring states, as an already-recorded,
  deliberate architectural decision, not something this pass
  discovers**: `_V1_MARKET_TYPES = ("moneyline", "spread", "total")` --
  "Player props are explicitly DEFERRED from this module -- not an
  oversight: the Player Prop Agent is not built, prop candidate
  consensus semantics remain intentionally unresolved... supporting
  historical/usage data for props is still incomplete."
- **Live-confirmed, not assumed**: `SELECT DISTINCT market_type FROM
  odds_snapshots` on real DEV data returns exactly `{"total", "spread",
  "moneyline"}` -- **zero player-prop odds rows exist anywhere in the
  persisted table.** The gap isn't merely "candidate generation ignores
  props that exist" -- no player-prop market data has ever been
  ingested at all.
- **Confirmed at the consensus layer too**: `app.features.consensus.
  resolve_candidate_direction` already returns `None` for `market_type
  == "prop"` by design ("Player Prop Agent and player-prop directional
  semantics are not yet built" -- the module's own docstring, Decision I).
- **`player_prop_agent`** is listed in `CONFIGURED_AGENTS`
  (`committee_context.py`) but **not** in `BUILT_AGENTS` -- it doesn't
  exist as real code.

**Conclusion**: there is no authoritative canonical player identity to
propagate, because there is no live player-prop candidate for one to be
attached to, anywhere in this codebase, today. This is not a schema
redesign problem and not a missing join -- it is three already-deferred,
already-documented milestones (player-prop odds ingestion, player-prop
candidate generation, the Player Prop Agent) that simply haven't been
built yet, each a deliberate prior decision, not an oversight this pass
uncovered. Building any of them would be exactly "turning this into
another infrastructure program," which the directive explicitly
forbids.

### 2. Player_id propagation implemented: **none -- correctly, none
needed.**

No code was changed for Part A. The one relevant hook already
exists from the prior pass (`app/orchestration/cycle.py`'s
`run_candidate_evaluation(..., player_id: str | None = None)`,
Live Context Package Orchestration, 2026-09-15) and remains the correct
integration point for whenever a real player-prop pipeline is built --
that future pipeline would simply pass a real `player_id` through
already-existing, already-tested plumbing. Nothing further was required
or attempted this pass, per the directive's own "do not let that
blocker prevent completion of Part B" instruction.

**Every requirement this section would otherwise have needed to satisfy
is moot, not violated**: deterministic identity only (nothing to
resolve), no fuzzy matching (none attempted), no hardcoded players
(none added), no provider calls (none made), no guessing from display
text (explicitly declined -- see below), `player_id` optional for
non-player markets (already true, unchanged), existing non-player
candidates unchanged (confirmed -- zero files touched).

**One tempting shortcut explicitly rejected**: `MarketCandidate.selection`
does carry free text that, for a hypothetical future prop candidate,
would include a player's display name (e.g. `"Jaxon Smith-Njigba Over
65.5"` -- the exact shape used in this session's own prior test
fixtures). Parsing that text against `players.name` to recover a
`player_id` was considered and explicitly declined: it is precisely the
fuzzy-matching-as-authoritative-identity-resolution this whole Context
Intelligence effort has deliberately avoided everywhere else (opponent
resolution, Engine Integration pass, 2026-09-15) and the directive's own
"no name fuzzy matching as authority" rule forbids it directly. It is
also moot today regardless, since no real prop candidate with such text
exists to parse.

---

## Part B -- Contextual Probability Modeling Design

### 3. Current probability architecture relevant to context

`ProbabilityModelingAgent.build_evidence` (Milestone 4.6, Decision B,
extended by this session's own two prior passes) is the **first and
only** step of the sequential Decision & Advisory chain that touches
probability. Audited directly:

- **There is no deterministic probability-computation code anywhere in
  this codebase.** `modeled_probability`/`confidence_in_probability` are
  produced by exactly one LLM call reasoning over the JSON dict
  `build_evidence()` returns (`sequential_base.build_messages`:
  `json.dumps(evidence, default=str)` becomes the user message). This is
  architecturally different from Expected Value/Risk/Kelly, which
  `app/orchestration/sequential.py`'s own docstring states explicitly are
  "computed here, in application code, between agent calls -- never
  inside an agent's own `build_evidence`."
- **`contextual_evidence` (when a `ContextPackage` is attached) already
  reaches this LLM call today**, automatically, with **zero code-level
  guardrail on how the model may use it** -- it can already, today,
  silently move `modeled_probability` on the basis of context, in any
  direction, by any amount, with no bound, no required citation, and no
  verification. This is the single most important architectural fact
  this audit surfaces: **Option 1 ("existing model/prompt evidence
  interpretation") is not a choice to make -- it is already, silently,
  the status quo**, and the directive's own "no unrestricted LLM
  discretion to invent numeric adjustments" rule is already being
  violated in principle the moment a real candidate carries contextual
  evidence (whether or not the recommendation worker is currently live
  in production is an operational, Phase-6 question this pass does not
  resolve -- the code path exists and would activate the moment it runs).
- No dimension-specific statistical model (Option 3) exists anywhere,
  and building one now would require real calibration data this project
  does not have (Section 5).

### 4. Double-counting findings (Part C)

Audited every admitted dimension against the full `build_evidence()`
payload (`candidate`, `upstream_findings`, `contextual_evidence`) and the
real fan-out committee agents that already run today (`BUILT_AGENTS`):

| Signal | Existing channel(s), confirmed by direct code read | New Context Intelligence channel | Overlap |
|---|---|---|---|
| **Odds/market** | (1) `candidate.american_odds`/`candidate.point` -- this exact wager's own priced line, always present. (2) `VegasLineAgent`/`ClosingLineMovementAgent` (both `BUILT_AGENTS`, already real, already in `upstream_findings`) -- both read `context.odds_history`/`context.line_movement`, built by the SAME `app.features.market.compute_line_movement` function `contextual_evidence.market.facts` itself reuses internally (confirmed: `market.py`'s own docstring: "reuses Milestone 4.5/7.1's existing pure computation, never duplicates it"). | `contextual_evidence.market`: target-game `facts.movement_groups` (**literally redundant** with (2) -- same underlying function, same game) + a genuinely NEW cross-game comparable-pool `similarity_score`/`sample_size`/`confidence` (how atypical this game's movement is vs. real comparable games). | **HIGH -- triple exposure** for the target game's own line facts (candidate + 2 agents + contextual_evidence all carry it); only the comparable-pool signal is non-duplicate. |
| **Weather** | `WeatherAgent` (`BUILT_AGENTS`, already real) reads `daily_game_intelligence.weather`/`.stadium` -- **current-only**, overwritten every refresh. | `contextual_evidence.weather`: a real, historical, point-in-time-capable target-game reading (temperature/wind/precipitation/conditions) plus a same-dome-bucket comparable pool. | **MEDIUM -- double exposure** on the same fact categories (temperature/wind/precip/conditions), sourced differently (current-state committee agent vs. real historical Context Intelligence), but conceptually the same information for a live call where "now" and "target" are close together. |
| **Venue** | No dedicated venue agent exists in `CONFIGURED_AGENTS`/`BUILT_AGENTS` at all. `WeatherAgent`'s own evidence includes `"stadium"` (name only, mild overlap). `TravelFatigueAgent` (`BUILT_AGENTS`) is venue-*adjacent* (distance/timezone) but computes a genuinely different fact. | `contextual_evidence.venue`: full identity, coordinates, roof type, same-venue comparable pool. | **LOW -- new signal**, only trivial (stadium name) overlap with `WeatherAgent`. |
| **Player performance** | `player_prop_agent` is `CONFIGURED` but **not `BUILT`** -- no real channel exists at all (matches Part A's own finding). | `contextual_evidence.player_performance`: real per-game observation(s). | **NONE -- entirely new signal**, no existing channel to duplicate. |

**The new design must, and does (Section 6), treat `market` and
`weather`'s target-game-own facts as already-represented** -- V1's
eligibility rules exclude re-weighting what the fan-out committee
already supplies, and scope each dimension's genuinely NEW contribution
narrowly (Section 6).

### 5. Chosen Contextual Probability V1 methodology

**Option 2 -- a deterministic post-model layer, mirroring EV/Risk/Kelly's
own established pattern (computed in application code, never inside an
agent's `build_evidence`) -- is the architecturally correct destination.**
Option 1 (LLM prompt interpretation) is already, unavoidably, how context
reaches the model today and cannot be un-built without removing
`contextual_evidence` entirely (not proposed); left alone and
unconstrained, it violates the directive's own rules. Option 3
(dimension-specific statistical adjustments) requires real calibration
data (Section 8) that does not exist -- attempting it now would mean
inventing exactly the arbitrary weights the directive forbids.

**V1, this pass, is therefore a design-only hybrid**: it does not build
Option 2's mechanism (no invented calibration exists to power it -- see
the directive's own "do not implement... unless the method already
exists... and requires no invented calibration," which does not apply
here), but it **specifies the exact contract Option 2 must satisfy**
(Section 6), and it names the one concrete, zero-calibration mechanism
that would let Option 2 exist safely without inventing a single
per-dimension weight: a **bounded, symmetric, dimension-agnostic safety
cap on total context-driven probability movement**, established by
comparing a real "with-context" model run against a real "without-context"
baseline run of the exact same candidate (Section 9) -- a cap is a
guardrail on the aggregate, never a calibrated per-dimension effect size,
so it does not fall under the "no arbitrary weights" prohibition the
same way a stated "weather = 10%" figure would.

---

## 6. Rules for each admitted dimension (the V1 contract)

For every dimension: **eligibility conditions**, **eligible signal**,
**direction**, **maximum permitted influence**, **provenance**,
**explanation requirement**, and **partial/unavailable handling**.

### player_performance

- **Eligible when**: `completeness == "joined"` for the specific
  player/game AND the candidate is genuinely player-scoped (moot today,
  Part A).
- **Eligible signal**: the real, per-observation `role_usage_signals`
  (targets/receptions/yards/TDs, etc.) -- never `snapCounts` or any
  field the source itself flags unreliable (`_unreliable_fields`,
  already excluded upstream).
- **Direction**: context-dependent on the specific candidate's own
  selection (e.g. a real, strong receiving performance is directionally
  relevant to an "Over receiving yards" candidate) -- never a fixed
  sign; this pass does not compute one.
- **Maximum permitted influence**: authority scales with `sample_size`,
  never fixed -- `sample_size == 1` (today's only real state, for every
  real player) means **one real game is evidence, not a trend**: it must
  carry materially LESS weight than a future `sample_size >= 2` result
  would. No numeric ratio is specified here (that would be inventing
  calibration); only the DIRECTION of the rule (monotonically
  non-decreasing authority with more real games) is fixed. **No fake
  trend/consistency score is ever computed** -- `confidence`/
  `similarity_score` stay `None` from this dimension exactly as already
  built; a future multi-game sample naturally strengthens evidence only
  because `sample_size`/`insufficient_evidence` (already real, already
  gated by `INSUFFICIENT_SAMPLE_FLOOR`) change, never because a new
  score is invented.
- **Provenance**: `duplicate_raw_row_count`/`canonical_row_id`/
  `ProvenanceRef` already travel verbatim into `contextual_evidence`
  (Context Integration pass) -- any future numeric layer must cite them
  in its own explanation, never discard them.
- **Explanation**: must name the specific observation(s) used (game,
  opponent when resolved, real stat values) -- never a vague "player
  performance was considered."
- **Partial/unavailable**: `player_performance` never resolves
  `"partial"` by its own design (Context Foundation pass); `unavailable`
  means **zero eligibility, zero influence, not a neutral/zero-valued
  input** -- already guaranteed structurally (absent from
  `contextual_evidence` entirely).

### market

- **Eligible when**: `completeness == "joined"` (today's real state for
  SEA@NE: comparable pool of 5 other real games, well above the floor).
- **Eligible signal**: **only** the cross-game comparable-pool
  `similarity_score`/`sample_size`/`confidence` (how atypical this
  game's own movement is relative to real comparable games) -- **never**
  the target game's own `facts.movement_groups` (opening/latest/
  movement/direction), which is already fully represented via
  `candidate.american_odds`/`.point` and `VegasLineAgent`/
  `ClosingLineMovementAgent` (Section 4). Re-weighting the same facts a
  third time is the literal double-counting this design must prevent.
- **Direction**: neutral by default -- an atypical movement is a flag
  for the model to REASON about (why did this move unusually?), never an
  automatic directional signal on its own.
- **Maximum permitted influence**: must never let the model **merely
  copy the sportsbook's own implied probability** and present it as
  MANSA's independent estimate (the directive's own explicit rule) --
  V1's explanation requirement (below) exists specifically to make this
  auditable: if `reasoning` ever reduces to "the market says X, so
  modeled_probability = X," that is a contract violation, not a valid
  use of this dimension, regardless of what any future numeric layer
  computes.
- **Provenance**: the dimension's own `ProvenanceRef` (row counts,
  window) travels forward already.
- **Explanation**: must distinguish "the market's own view" (already
  covered by the fan-out committee) from "how unusual is this specific
  movement" (the one thing this dimension actually, uniquely
  contributes).
- **Partial/unavailable**: `PARTIAL` (comparable pool below the floor)
  admits target facts but the comparable-pool signal itself must not be
  used at all (already `None` in the underlying result); `unavailable`
  -- zero eligibility, same as every other dimension.

### weather

- **Eligible when**: `completeness` is `"joined"` or `"partial"` **AND**
  the candidate's own `market_type`/`selection` is plausibly weather-
  sensitive (e.g. `total`, or a real future passing/kicking prop) --
  **never** eligible merely because real weather data exists for the
  game (the directive's own explicit rule: "no effect merely because
  weather data exists"). A moneyline or spread candidate for a dome game
  is the clearest case where weather must contribute nothing, not
  because the data is missing but because it is not market-relevant.
  This pass does not build the market-type gate; it specifies that any
  future implementation must include one.
- **Eligible signal**: the target game's own real reading (temperature/
  wind/precipitation/is_dome) -- **not** re-derived from
  `daily_game_intelligence.weather` (already covered by the existing,
  current-only `WeatherAgent`, Section 4) -- Context Intelligence's
  contribution is specifically the REAL, point-in-time-capable version
  of the same fact category, which only matters distinctly for a
  genuinely historical reconstruction, not for a live call where the two
  sources are likely near-identical. For V1's live-only scope, this
  dimension's marginal value over the existing `WeatherAgent` is
  honestly small -- named directly, not glossed over.
- **Direction**: never fixed; must remain within whatever a future,
  real, disclosed relationship between a specific weather condition and
  a specific market type would justify -- none exists yet, so V1
  computes no direction.
- **Maximum permitted influence**: `PARTIAL` evidence (today's real
  state for every real weather-covered game -- comparable pool always
  below the floor so far) **must carry strictly less permitted influence
  than a hypothetical future `JOINED` result** -- directionally required,
  not numerically specified (no `JOINED` weather case has ever been
  observed yet to calibrate against).
- **Provenance**: real `ProvenanceRef`, `weatherapi`-source-only
  (fixture exclusion already enforced).
- **Explanation**: must name the specific real reading used and its
  market-type relevance, never a generic "weather was a factor."
- **Partial/unavailable**: `unavailable` (12 of 16 real games today) --
  zero eligibility, never a placeholder "average" condition assumed.

### venue

- **Eligible when**: `completeness` is `"joined"` or `"partial"` **AND**
  a SPECIFIC, pre-identified venue effect exists to cite -- **static
  venue facts alone (an identity, a set of coordinates, a roof-type
  flag) must never by themselves create probability movement** (the
  directive's own explicit rule). Today, no such specific effect is
  computed anywhere in this codebase (Context Intelligence's venue
  dimension produces identity + a same-venue comparable `similarity_score`
  of `1.0` when any comparable exists, never an effect size) -- so
  **venue's honest, current eligibility for probability influence is
  effectively zero**, even though its `completeness` is frequently
  `"joined"`/`"partial"` for real games. Its real, legitimate current use
  is qualitative/explanatory color (e.g. "this game is at Lumen Field,
  outdoors"), not a probability driver.
- **Eligible signal**: none defined for numeric use in V1; identity
  facts only, for explanation/context.
- **Direction / maximum permitted influence**: **zero**, until a
  specific, real, disclosed venue effect (e.g. a documented altitude or
  surface effect with real supporting data) is separately designed --
  not invented here.
- **Provenance**: real `ProvenanceRef` (venues + games-sharing-venue).
- **Explanation**: identity facts may be cited narratively; never
  presented as having moved a probability.
- **Partial/unavailable**: `unavailable` -- zero eligibility, same rule.

### General rules (apply across all four)

- **Missing evidence = no adjustment, never a zero-valued negative
  signal.** Already structurally guaranteed: `unavailable` dimensions
  are absent from `contextual_evidence` entirely (Context Integration
  pass); nothing in this design proposes changing that.
- **`completeness != confidence`.** Restated, not re-derived --
  unchanged from every prior pass's own discipline.
- **No context-derived confidence** -- `confidence_in_probability`
  remains whatever `ProbabilityModelOutput` already computes (today,
  entirely LLM-judgment); this design does not touch it.
- **No unrestricted LLM discretion to invent numeric adjustments** --
  the one rule this pass's own audit (Section 3) found is currently
  being violated in principle, and the one gap the next implementation
  pass (Section 9) must close first, ahead of any dimension-specific
  numeric work.
- **Every probability change must be explainable from evidence +
  rule/method.** Today, `reasoning`/`supporting_evidence` exist but
  nothing enforces they cite `contextual_evidence` specifically when
  context was attached and influential -- a real gap, named for the next
  pass.
- **Hard bounds/guardrails against extreme context-driven movement.**
  None exist today. Section 9 names the concrete mechanism (context-on
  vs. context-off comparison + a disclosed-conservative cap) as the
  next pass's central deliverable.

---

## 7. Numeric-adjustment policy / guardrails

**No numeric adjustment is implemented by this pass.** The policy this
design establishes for any FUTURE numeric work:

1. Any numeric context-driven adjustment must be computed in
   application code (mirroring EV/Kelly/Risk), never left to
   unconstrained LLM discretion inside `build_evidence()`/the model
   call.
2. No per-dimension weight (e.g. "weather = 10%") may ever be invented
   without real, disclosed calibration data backing it -- none exists
   today (Section 8).
3. The one number this design DOES recommend defining -- a
   dimension-agnostic maximum total context-driven movement (a
   disclosed-conservative safety cap, matching this codebase's own
   established convention for undecided constants, e.g. `scoring.py`'s
   own `INSUFFICIENT_SAMPLE_FLOOR`/`MIN_SAMPLE_FOR_FULL_CONFIDENCE`,
   both explicitly "not empirically derived") -- is a GUARDRAIL on the
   aggregate, never a per-dimension effect size, and is therefore not
   the kind of "arbitrary weight" the directive prohibits. Its exact
   value is not set by this pass (that would itself be an invented
   number without the comparison mechanism in Section 9 built first to
   justify it).
4. Any dimension resolving `unavailable` contributes literally nothing
   (not zero-as-a-value -- absent) to any future numeric layer, exactly
   as it already contributes nothing to `contextual_evidence` today.
5. `PARTIAL` evidence may only ever REDUCE, never increase, a
   dimension's eligibility/influence relative to an equivalent `JOINED`
   result.

---

## 8. Validation methodology

**Immediately buildable, zero new implementation required**: a
**context-on vs. context-off comparison harness** -- run the exact same
real candidate through `ProbabilityModelingAgent.build_evidence()` twice
(once with `context.context_package` attached, once with it stripped via
`dataclasses.replace(context, context_package=None)`), diff the two
evidence payloads and, once a real LLM call is made for both, the two
`modeled_probability`/`reasoning` outputs. This requires no new code
today -- both code paths already exist and are already tested
independently (this session's own prior passes).

**Metrics for when a real, graded outcome history exists** (does not
exist yet -- `cycle.py`'s own docstring: "consensus_snapshots is
explicitly out of scope... consensus math belongs to the not-yet-built
Consensus Engine milestone," and no probability-grading/outcome pipeline
was found anywhere in this codebase during this pass's audit):

- **Calibration** (reliability: do candidates modeled at 60% actually
  win ~60% of the time, bucketed).
- **Brier score** / **log loss** (proper scoring rules for probabilistic
  forecasts).
- **Directional accuracy** (did the modeled favorite actually win, a
  coarser but real signal available sooner than full calibration).
- **Context-on vs. context-off comparison, at scale**: once enough real
  graded candidates exist, compare the SAME metrics computed with vs.
  without `contextual_evidence` attached, to determine whether context
  measurably improves calibration/Brier/log loss -- not merely whether
  it changes the number.

**Explicit non-claim, restated as a standing rule for this and every
future pass**: **no predictive-improvement claim will be made from one
week of real data.** The current real substrate (16 real games, one NFL
week, confirmed repeatedly across this session's own prior passes) is
sufficient to prove the MECHANISM works correctly (this pass's own real
JSN/SEA@NE proofs, and every prior pass's), never sufficient to prove
context IMPROVES predictions. Deterministic test fixtures (this
session's own established convention) remain the correct tool for
proving architecture; only real, graded, accumulated history can ever
validate predictive value.

---

## 9. Exactly what the next implementation pass would change

Two independent, small, clearly-scoped candidates -- neither executed by
this pass:

1. **Close the "unrestricted LLM discretion" gap (highest priority,
   per this pass's own audit finding, Section 3).** The smallest safe
   fix does not require the full numeric-adjustment layer: update the
   Probability Modeling agent's own prompt instructions (a
   `prompt_registry` change, not application code) to explicitly state
   the rules Section 6 already defines -- cite `contextual_evidence`
   only when present and eligible per its own `completeness`/
   `sample_size`, never treat `unavailable` as zero, never restate the
   market's own implied probability as an independent finding, and name
   which specific evidence drove any claimed context-based reasoning in
   `supporting_evidence`. This closes real risk with zero new code and
   zero invented calibration.
2. **Build the context-on vs. context-off comparison harness (Section
   8)** -- a real, deterministic test/validation tool (not production
   code) that runs the same real candidate both ways and reports the
   delta, the first real step toward eventually justifying a disclosed
   safety cap (Section 7, item 3) with real evidence rather than an
   invented number.

Not authorized or attempted by either candidate: any per-dimension
statistical weight, any new fan-out agent, any schema change, any
player-prop pipeline work (still blocked per Part A), any change to
EV/Risk/Kelly, any provider call.

---

## Out of scope, exactly as instructed

No provider calls. No recommendation-ranking changes. No unrelated
context gaps addressed. No news bug fix. No injury/PBP work. No
arbitrary weights invented anywhere in this document. Zero files in
`apps/ai-orchestrator/app/` were modified by this pass -- confirmed via
`git status`.
