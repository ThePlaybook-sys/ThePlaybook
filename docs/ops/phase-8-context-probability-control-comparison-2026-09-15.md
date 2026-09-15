# Phase 8 — Context Probability Control + Comparison

**Date:** 2026-09-15
**Directive:** MANSA HQ — "PHASE 8 CONTEXT PROBABILITY CONTROL + COMPARISON"
**Type:** Implementation (Part A: prompt guardrail) + new harness (Part B: comparison mechanism)
**Authorized scope:** exactly the two next steps the prior pass ("Contextual Probability Design + Player Identity") recommended and nothing else.

---

## 1. Why this pass exists

The prior pass found that `contextual_evidence` already reaches the Probability Modeling
Agent's one LLM call today (whenever `context_package` is attached — real production
candidates get one via `cycle.py`'s `_attach_context_package`) with **zero code-level
guardrail** on how the model is allowed to use it. That pass also found there is no
deterministic probability-computation code anywhere in this codebase — `modeled_probability`
is entirely one LLM call's own judgment over the `build_evidence()` JSON blob. This pass closes
the first gap (a guardrail) and builds the second thing the design pass recommended (a
deterministic comparison harness) — nothing more.

---

## 2. Part A — LLM Probability Guardrail (implemented, live)

### 2.1 Where the live prompt actually lives (investigated first)

`app.agents.sequential_base._LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS`/`_LEGACY_SEQUENTIAL_
SYSTEM_PROMPT_TEMPLATE` are **source wording only** — Milestone 4.8's `resolve_active_prompt`
resolves the actual live prompt from the `prompt_registry` table at the orchestration boundary
(`app.orchestration.sequential.run_sequential_agent`), never from this Python file at runtime.
`scripts/generate_prompt_registry_seed.py` is the one mechanism that turns the `_LEGACY_*`
constants into the literal `prompt_text` a `prompt_registry` row carries — confirmed by reading
it in full. `idx_prompt_registry_one_active_per_name` (2026-08-24) enforces exactly one active
row per `prompt_name`; the documented, established pattern for updating a live agent prompt is
therefore: edit the `_LEGACY_*` source constant → re-run the seed generator → deprecate the old
active row → insert a new, higher-version active row (exactly how `injury_intelligence_agent`/
`weather_agent` are documented as "legitimately coexisting at different versions" in Volume 3).

### 2.2 What changed

- **New constant** `app.agents.sequential_base._LEGACY_CONTEXTUAL_EVIDENCE_GUARDRAILS` — the
  guardrail block, appended by plain string concatenation (not `.format()`, since the
  instructions string it's appended to contains literal JSON `{`/`}` characters) to
  `_LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS` wherever the two combine. Used **only** by
  `probability_modeling_agent` — the other three sequential agents (`expected_value_agent`,
  `risk_manager_agent`, `bankroll_coach_agent`) use `_LEGACY_AGENT_OUTPUT_INSTRUCTIONS`,
  untouched.
- **`scripts/generate_prompt_registry_seed.py`** updated to concatenate the guardrail onto the
  probability instructions before building `probability_modeling_agent`'s seed text — so the
  seed generator, `sequential_base.py`, and the live database row are now byte-identical by
  construction, never hand-transcribed.
- **`tests/agents/test_sequential_agents.py`**'s `_sequential_prompt` helper updated identically
  (it independently reconstructs each agent's expected prompt for exact-match assertions).
- **New migration**, applied live to dev Supabase (`nhwjtsdebgiwskshzqiq`) and committed:
  `supabase/migrations/20260915120000_probability_modeling_agent_contextual_evidence_
  guardrails_v2.sql` — deprecates `probability_modeling_agent` v1 (`status='active'` →
  `'deprecated'`) and inserts v2 (`status='active'`, `owner='phase-8-context-probability-
  control-comparison-2026-09-15'`), generated verbatim from the same seed script, never
  hand-typed. **Live-verified after apply:**

  | prompt_name | version | status | text_len |
  |---|---|---|---|
  | probability_modeling_agent | 1 | deprecated | 1762 |
  | probability_modeling_agent | 2 | active | 5070 |

  No other `prompt_registry` row touched. `supabase/seed.sql` deliberately left unmodified —
  a fresh database still seeds v1, then this new migration brings it to v2 on replay, matching
  the same seed+migrations layering every other prompt/schema change in this repo already uses.

### 2.3 The guardrail text (exact, live in prompt_registry v2)

> If the evidence includes a "contextual_evidence" key, treat it as SUPPORTING evidence only —
> it is never permission to invent a numeric adjustment. Follow these rules exactly:
> - Do not assign an arbitrary weight or point value to any contextual_evidence dimension...
> - "completeness" (joined/partial/unavailable) describes how much evidence exists, not how
>   confident you should be...
> - A dimension with completeness "partial" must be treated cautiously...
> - A dimension with completeness "unavailable" (or omitted entirely) contributes NOTHING...
> - contextual_evidence.player_performance with sample_size 1 is exactly one historical
>   observation — never describe or treat it as a trend, tendency, or pattern...
> - Do not change your probability merely because contextual_evidence.weather or
>   contextual_evidence.venue data exists...
> - contextual_evidence.venue evidence is normally informational/neutral...
> - The target game's own moneyline/spread/total line and any market-movement findings from
>   upstream committee agents... already reflect the target game's market. If
>   contextual_evidence.market repeats those same target-game facts, that repetition is NOT
>   independent confirmation...
> - If an upstream weather finding... already covers the same conditions
>   contextual_evidence.weather describes, that is one piece of evidence observed twice...
> - In general, do not count the same underlying fact more than once...
> - Never copy a sportsbook's implied probability... directly into modeled_probability...
> - Your reasoning must name which SPECIFIC, UNIQUE piece of evidence actually affected your
>   judgment...

(Full text: `app.agents.sequential_base._LEGACY_CONTEXTUAL_EVIDENCE_GUARDRAILS`, and live in
`prompt_registry` where `prompt_name='probability_modeling_agent' and version=2`.)

Every one of the directive's required rules is present: no arbitrary weights; completeness ≠
confidence; partial treated cautiously; unavailable contributes nothing; one player-game ≠
trend; no movement merely because weather/venue data exists; venue normally neutral; market and
weather double-counting guardrails naming the exact upstream overlap; no repeated-evidence
double counting; no sportsbook-probability copying; reasoning must name unique evidence.

---

## 3. Part B — Comparison harness (new, built)

### 3.1 Design

New module `app.orchestration.context_probability_comparison`, function
`run_context_probability_comparison(context, *, client, headers, routing_rule,
adapter_registry, ...)`:

- Runs `ProbabilityModelingAgent` via the existing `run_sequential_agent` **twice** against the
  SAME `SequentialDecisionContext` — once with `context_package` stripped (**CONTROL**, via
  `dataclasses.replace(context, context_package=None)`) and once exactly as given
  (**CONTEXT**). Candidate, `upstream_outputs`, and `participation` are held byte-identical
  between the two runs — only `context_package` differs.
- When `context.context_package` is already `None`, CONTROL and CONTEXT are literally the same
  evidence — only **one** model call is spent, never a wasted second call.
- Never persists anything (unlike `cycle.run_candidate_evaluation`) and never recomputes
  EV/Kelly/Risk — pure observation.
- Computes `probability_delta` (CONTEXT − CONTROL), which admitted dimensions are present vs.
  unavailable, which present dimensions overlap a real, already-built upstream fan-out agent
  (`DIMENSION_OVERLAPPING_AGENTS` — the exact market/weather HIGH/MEDIUM and venue/
  player_performance NONE/LOW risk audit from the prior design pass, carried forward as code),
  and which dimensions the model's own `reasoning`/`supporting_evidence` text actually names
  (`claimed_dimensions`, plain keyword matching).
- `SafetyFlags` (6 fields, exactly the directive's list) — **heuristic pattern-matching only,
  never a semantic judgment, and never auto-corrects anything**: `probability_moved_without_
  unique_contextual_reason`, `duplicated_evidence_appears_additionally_influential`,
  `unavailable_evidence_affects_probability`, `venue_alone_causes_unsupported_movement`,
  `player_history_described_as_trend`, `sportsbook_probability_appears_copied` (compared against
  `app.features.probability.implied_probability`, the existing deterministic American-odds
  conversion, within a disclosed ±0.005 band).
- `render_comparison_report` — plain-text rendering used to produce §4 below verbatim from real
  harness output, never hand-transcribed.

### 3.2 The "no provider calls" reconciliation

The directive asks this pass to "measure what the current LLM probability behavior actually
does when context is added" while also forbidding any provider call. Both cannot be literally
true at once — observing genuine model behavior requires a real call. **Resolution: every test
and every report entry below runs the harness against `FakeModelAdapter` with an explicitly
scripted response.** This proves the harness mechanism — evidence construction, duplicate
detection, flag pattern-matching — works correctly against a *known, chosen* output. **It does
not, and cannot under this pass's boundary, prove what the real model actually does** with the
new v2 guardrail prompt. That remains genuinely unobserved until a separately authorized live
pass. This report says so plainly rather than presenting scripted results as real behavior.

---

## 4. Comparison report — context-on vs. context-off, 6 cases

All 6 cases below are captured directly from `render_comparison_report`'s real output (script
run at `/tmp/.../run_reports.py`, reproduced verbatim), never hand-typed. Cases 1–4 and 6 use
hand-built, explicitly SYNTHETIC `ContextPackage` fixtures (architecture proof only). **Case 5
uses REAL data** — the live-queried JSN/SEA@NE fixture already established in
`tests/orchestration/test_cycle_candidate.py` (Jaxon Smith-Njigba, SEA@NE, 2026-09-10 real stat
line: 11 targets / 8 receptions / 122 receiving yards / 1 TD).

```
=== 1. Context absent ===
admitted_dimensions_present=()
control_probability=0.55 context_probability=0.55 delta=+0.0000
safety_flag.* = all False

=== 2. Venue only (SYNTHETIC) ===
admitted_dimensions_present=('venue',)
claimed_dimensions=('venue',)
control_probability=0.5 context_probability=0.58 delta=+0.0800
safety_flag.venue_alone_causes_unsupported_movement=True
(all other flags False)

=== 3. Market context, no upstream overlap (SYNTHETIC) ===
admitted_dimensions_present=('market',)
duplicated_dimensions=()
claimed_dimensions=('market',)
control_probability=0.5 context_probability=0.53 delta=+0.0300
safety_flag.* = all False

=== 4. Weather PARTIAL, no movement (SYNTHETIC) ===
admitted_dimensions_present=('weather',)
claimed_dimensions=()
control_probability=0.5 context_probability=0.5 delta=+0.0000
safety_flag.* = all False

=== 5. Player performance sample_size=1, REAL JSN/SEA@NE data ===
admitted_dimensions_present=('market', 'player_performance', 'venue', 'weather')
context_evidence player_performance sample_size = 1  (real: 11 targets/8 rec/122 yds/1 TD)
claimed_dimensions=('player_performance',)
control_probability=0.55 context_probability=0.63 delta=+0.0800
safety_flag.player_history_described_as_trend=True   <-- deliberately violated by the
                                                            scripted reasoning to prove the
                                                            flag catches it
(all other flags False)

=== 6. Duplicated market+weather exposure (SYNTHETIC) ===
admitted_dimensions_present=('market', 'weather')
duplicated_dimensions=('market', 'weather')   <-- upstream_outputs already contained
                                                     vegas_line_agent + weather_agent findings
claimed_dimensions=('market', 'weather')
control_probability=0.5 context_probability=0.61 delta=+0.1100
safety_flag.duplicated_evidence_appears_additionally_influential=True
(all other flags False)
```

### 4.1 Observed probability deltas

| Case | Delta | Note |
|---|---|---|
| 1. Context absent | +0.0000 | Trivial — no context to move it |
| 2. Venue only | +0.0800 | Scripted; heuristic-flagged as unsupported |
| 3. Market, no overlap | +0.0300 | Scripted; no duplication, no flag |
| 4. Weather PARTIAL, unused | +0.0000 | Scripted; PARTIAL sitting unused triggers nothing |
| 5. Player performance, real data | +0.0800 | Scripted; correctly flagged as trend-language misuse |
| 6. Duplicated market+weather | +0.1100 | Scripted; correctly flagged as duplicated influence |

**These deltas are entirely artifacts of the scripted `FakeModelAdapter` responses chosen to
exercise each flag** — they carry no information about what a real model would actually do and
must not be read as calibration evidence of any kind.

### 4.2 Double-counting findings

Confirmed exactly as the prior design pass audited, now expressed as live, testable code
(`DIMENSION_OVERLAPPING_AGENTS`): `market` overlaps `vegas_line_agent`/`closing_line_movement_
agent` (both real, both built); `weather` overlaps `weather_agent` (real, built); `venue` and
`player_performance` overlap no existing agent (genuinely new signal). Case 6 proves the
detection correctly identifies duplication *and* the additional-influence flag correctly fires
only when the model's own text actually claims the duplicated dimension moved its probability
(Case 3 proves the same detection correctly stays silent when there is no upstream overlap to
duplicate in the first place).

### 4.3 Safety flags triggered (this pass, scripted proof only)

`venue_alone_causes_unsupported_movement` (Case 2), `player_history_described_as_trend`
(Case 5), `duplicated_evidence_appears_additionally_influential` (Case 6) — each deliberately
provoked by a scripted response chosen to violate exactly the rule it tests, proving the
heuristic catches it. `probability_moved_without_unique_contextual_reason` and `unavailable_
evidence_affects_probability` were not provoked in this pass's 6 cases (no scripted response
was written to move probability while claiming nothing, or to move it while citing an
unavailable dimension) — the mechanism exists and is unit-tested for both, just not exercised in
this specific 6-case report. `sportsbook_probability_appears_copied` did not fire in any case
(no scripted probability was chosen within 0.005 of the candidate's book-implied probability).

---

## 5. Answers to the directive's required STOP AND REPORT items

1. **Prompt guardrails implemented** — yes, live in `prompt_registry`
   (`probability_modeling_agent` v2, active), source in `sequential_base.py`, §2 above.
2. **Comparison harness design** — `app.orchestration.context_probability_comparison`, §3.1.
3. **Context-on/off results** — §4, all 6 required case shapes covered (context absent, venue
   only, market context, weather PARTIAL, player_performance sample_size=1 on real data,
   duplicated market/weather exposure).
4. **Observed probability deltas** — §4.1 — scripted, not real-model, exactly as disclosed in
   §3.2.
5. **Double-counting findings** — §4.2 — confirmed as code, proven live in Case 6.
6. **Safety flags triggered** — §4.3.
7. **Is current LLM behavior stable enough to remain the base probability estimator
   temporarily?** — **Cannot be answered by this pass.** No real model call was made (forbidden
   by this pass's own boundary), so there is no genuine observation of current LLM behavior to
   judge stability from. What this pass *does* establish: the guardrail prompt is now live, and
   a harness exists that can measure real behavior the moment a live-call pass is authorized.
   Recommend treating this question as still open, not answered "yes" by default.
8. **What evidence exists for designing the first deterministic contextual adjustment
   methodology?** — None new this pass (none was permitted to be gathered, by design). The
   evidence still required, unchanged from the prior design pass: real graded outcomes (the
   Consensus Engine's outcome-grading pipeline, not yet built) to measure whether admitted
   context actually improves calibration — inventing a numeric adjustment before that exists
   would still be exactly the "arbitrary weight" both the guardrail and the design pass forbid.
9. **Exact next implementation recommendation** — two independent, separately-authorizable
   next steps: (a) a live-call pass (still zero deterministic weights) that runs this exact
   harness against a real Anthropic call, with the v2 guardrail prompt live, to observe genuine
   current LLM behavior — the first real answer to item 7; (b) begin the Consensus Engine's
   outcome-grading pipeline, the actual prerequisite for any future calibrated deterministic
   adjustment. Neither is built this pass.

---

## 6. Test results

6 new tests (`tests/orchestration/test_context_probability_comparison.py`), full
`apps/ai-orchestrator` suite: **935 passed, zero regressions** (up from 929).

## 7. Out of scope, exactly as instructed

No deterministic context weight; no arbitrary aggregate movement cap; no EV/recommendation
logic change; no provider call (MSF or Anthropic); no player-prop pipeline work; no news/
injury/PBP work; no unrelated cleanup; no safety flag auto-fixed (all are report-only).

## 8. Files changed

`apps/ai-orchestrator/app/agents/sequential_base.py`,
`apps/ai-orchestrator/scripts/generate_prompt_registry_seed.py`,
`apps/ai-orchestrator/tests/agents/test_sequential_agents.py`,
`apps/ai-orchestrator/app/orchestration/context_probability_comparison.py` (new),
`apps/ai-orchestrator/tests/orchestration/test_context_probability_comparison.py` (new),
`supabase/migrations/20260915120000_probability_modeling_agent_contextual_evidence_
guardrails_v2.sql` (new, applied live to dev Supabase `nhwjtsdebgiwskshzqiq`),
`docs/ops/phase-8-context-probability-control-comparison-2026-09-15.md` (new) — confirmed via
`git status`. One live database mutation this pass (the prompt_registry version bump, §2.2,
data-only, no schema change). Zero provider calls. Zero Railway changes.
