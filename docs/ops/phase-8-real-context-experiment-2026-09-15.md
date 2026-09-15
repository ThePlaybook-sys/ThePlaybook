# Phase 8 — Real Context-On/Off Model Observation + Single-Game Evidence Floor

**Date:** 2026-09-15
**Directives:** MANSA HQ — "PHASE 8 REAL CONTEXT-ON/OFF MODEL OBSERVATION", then "PHASE 8 EXPERIMENT CLOSEOUT + SINGLE-GAME SAFETY RULE"
**Type:** Live experiment (6 real Anthropic calls, hard-capped) + resulting prompt-version change
**Outcome:** Experiment succeeded. Claude Opus 5 provisionally accepted as MANSA's TEMPORARY base probability estimator, with one new hard restriction.

---

## 1. What this pass finally measured

Every prior Phase 8 pass observed `contextual_evidence` behavior only through
`FakeModelAdapter` with scripted responses — proving mechanism, never model
behavior. This pass made **exactly 6 real Anthropic HTTP requests** against the
real MANSA probability path and observed what the model genuinely does when
context is added to otherwise identical evidence.

### 1.1 Execution mechanism (and why it took four attempts)

The credential lives only in Railway. Three approaches were audited and rejected
before one worked:

1. **Read the key into this session and call locally** — blocked: Railway returns
   `valuesRedacted: true` to this connection type. Reported as a 0-call STOP.
2. **Existing in-container execution mechanism** — none exists: no exec/SSH tool,
   and no non-persisting endpoint on `ai-orchestrator`.
3. **Temporarily override `ai-orchestrator`'s own `startCommand`** — designed, then
   superseded: it would have interrupted a live service and needed two deploys.
4. **A separate temporary service** (chosen): `phase8-context-experiment`, dev only,
   same repo/branch/rootDirectory, `restartPolicyType: NEVER`, **no domain**, with
   its variables set as Railway *references* (`${{ai-orchestrator.ANTHROPIC_API_KEY}}`)
   so the secret resolved server-side and never entered this session. The Anthropic
   call happened inside that container; only the JSON report came back, via logs.

**A real failure worth recording:** the first deployment crashed with
`python: can't open file '/app/scripts/phase8_context_probability_experiment.py'`
and made **zero** Anthropic requests. Root cause, confirmed from the build log and
the Dockerfile itself: `apps/ai-orchestrator/Dockerfile` copies only `COPY app ./app`,
so a repo-level `scripts/` directory is simply absent from the built image. Fixed by
moving the script inside `app/` (no change to the shared Dockerfile) and adjusting its
`sys.path` bootstrap from two levels up to three. That fix lives on `gateb-diag-tmp`
only, deliberately kept off `dev` so it could not trigger an `ai-orchestrator` autodeploy
mid-experiment.

### 1.2 Budget enforcement (held exactly)

A counter wrapped the single real `AnthropicModelAdapter` instance at the lowest
outbound boundary. Because `probability_modeling_analysis` routes primary
(`claude-opus-5`) and fallback (`claude-sonnet-5`) to the *same* `"anthropic"` adapter,
every attempt — primary, in-model retry, or fallback — incremented one shared counter,
and a 7th request would have been refused before the HTTP call. Calls ran strictly
sequentially with an abort check after each; the script would have stopped the entire
experiment the moment any call failed.

**Final count: exactly 6.** No fallback was used; all 6 served by `claude-opus-5`.

---

## 2. Results — three CONTROL/CONTEXT pairs

All six calls: model `claude-opus-5`, provider `anthropic`, `used_fallback: false`,
prompt `probability_modeling_agent` **version 2** (the guardrail prompt), resolved live
through the real `resolve_active_prompt` path. Everything within each pair was held
identical except `contextual_evidence`.

| Pair | CONTROL | CONTEXT | Δ | Book break-even |
|---|---|---|---|---|
| 1. Market (KC ML −125, SYNTHETIC candidate) | 0.54 (conf 0.22) | **0.54** (conf 0.32) | **0.00** | 0.5556 |
| 2. Weather PARTIAL (Over 44.5 −110, SYNTHETIC) | 0.50 (conf 0.18) | **0.50** (conf 0.18) | **0.00** | 0.5238 |
| 3. Player performance (JSN/SEA@NE, **REAL** 11 tgt / 8 rec / 122 yds / 1 TD, sample_size 1) | 0.51 (conf 0.22) | **0.55** (conf 0.30) | **+0.04** | **0.5349** |

### 2.1 Reasoning differences (verbatim excerpts)

**Pair 1 — examined the market dimension and explicitly refused to weight it:**
> "The single specific piece of contextual evidence that I examined is the comparable-pool
> movement split (4 of 6 comparable games moved toward the favorite, 2 toward the underdog).
> I did NOT let this move my number: six observations split 4-2 is statistically
> indistinguishable from a coin flip, and the pool is cross-game rather than about Kansas
> City in this matchup."

**Pair 2 — PARTIAL weather produced zero movement, with the right reasoning:**
> "Calm, mild, mostly dry conditions matter for a total only as the ABSENCE of a
> scoring-suppressing factor — they remove a reason to lean Under, but they do not supply an
> affirmative reason to lean Over, so I did not shift my number for them. That dimension is
> also flagged completeness 'partial' with sample_size 1, which I am not treating as any kind
> of pattern."

The CONTROL run in this pair also resisted a cue nobody planted deliberately:
> "I note the game_id string contains the token 'weather-synthetic', but an identifier is not
> evidence... I am explicitly not allowed to invent a weather effect from the existence or
> naming of data."

**Pair 3 — the one real movement:**
> "That is exactly one game, not a trend or tendency, so I treat it only as weak corroboration
> that the player has occupied a genuinely high-volume receiving role (double-digit targets) in
> at least one prior outing... That single-observation usage signal is the one specific piece of
> evidence that nudged me modestly above a coin flip."

---

## 3. V2 guardrail compliance — strong

| Rule | Observed |
|---|---|
| No arbitrary per-dimension weights | **Held** — explicitly refused to weight a 4–2 split |
| Completeness ≠ confidence | **Held**, with one soft note (§5) |
| PARTIAL treated cautiously | **Held** — named partial/sample_size 1, no movement |
| UNAVAILABLE contributes nothing | **Held** in all 6 calls; never inferred from absence |
| One player game ≠ trend | **Held** verbally — explicitly "not a trend or tendency" |
| No movement merely because weather/venue data exists | **Held** strongly |
| Venue normally neutral | Not exercised (no venue dimension in any pair) |
| Market double-counting | **Held** on the cross-game pool; agent-level duplication untested (§4) |
| Weather double-counting | Not exercised (no WeatherAgent finding present) |
| Never copy sportsbook implied probability | **Held strongly** — all three CONTROL calls named the break-even and explicitly declined to adopt it (0.54 vs 0.5556; 0.50 vs 0.5238; 0.51 vs 0.5349) |
| Reasoning names unique evidence | **Held strongly** — every call named specifics and stated what did *not* move the number |

---

## 4. Double-counting: what this run could and could not test

`upstream_outputs` was empty for all six calls — running real committee agents would
have required additional LLM calls outside the 6-call budget. So `duplicated_dimensions`
was `[]` everywhere and **agent-level duplication (market ↔ VegasLine/ClosingLineMovement,
weather ↔ WeatherAgent) remains untested against a real model.** What was observable is
encouraging: the cross-game market pool was examined and explicitly given zero weight.

---

## 5. Findings that drove the closeout decision

**Primary finding (the reason for the new rule).** A single historical observation moved
the estimate **+0.04**, from 0.51 to 0.55 — across the candidate's own −115 break-even of
**0.5349**. That converts "no demonstrated edge" into an *apparent* edge. The model was
honest throughout (explicitly "not a trend", confidence held low at 0.30), and v2 never
forbade this — it forbade calling one game a trend, not letting one game move the number.
Because EV, Kelly and stake sizing are deterministic downstream of `modeled_probability`,
that 0.04 would have flowed straight into a stake recommendation.

**Secondary finding (recorded, not acted on).** In pair 1, `confidence_in_probability` rose
0.22 → 0.32 while the probability stayed identical, on evidence the model itself called
directionally worthless. Not a v2 violation, and arguably defensible (having checked and
ruled out a dimension is information), but adjacent to the completeness-≠-confidence rule
and worth watching.

**Safety-flag finding (fixed this pass).** Two flags fired on pair 3 —
`unavailable_evidence_affects_probability` and `player_history_described_as_trend` — and
**both were false positives of our own heuristics**, not model violations. They fired because
the model named things precisely in order to deny them ("No venue, weather, or market
contextual dimensions were provided, so nothing there moved my estimate"; "not a trend or
tendency"). Precision on this run was 0 of 2.

---

## 6. Closeout decision and what changed

**Decision (MANSA):** Claude Opus 5 may remain MANSA's **temporary** base probability
estimator. But `player_performance` with `sample_size=1` **may not numerically change**
`modeled_probability`.

### 6.1 Prompt v3 — the single-game evidence floor

`probability_modeling_agent` **v2 → v3** (v2 deprecated; exactly one active row per
`idx_prompt_registry_one_active_per_name`). Applied through the normal mechanism: source
wording in `app.agents.sequential_base._LEGACY_CONTEXTUAL_EVIDENCE_GUARDRAILS`, generated
verbatim by `scripts/generate_prompt_registry_seed.py`, applied via migration
`20260915163000_probability_modeling_agent_single_game_evidence_floor_v3.sql`. Live-verified:

| version | status | text_len |
|---|---|---|
| 1 | deprecated | 1762 |
| 2 | deprecated | 5070 |
| **3** | **active** | **5846** |

The new rule, verbatim:

> **HARD RULE, evidence floor (this is a floor, not a weight):**
> `contextual_evidence.player_performance` with sample_size 1 must NOT change your
> `modeled_probability` in either direction, by any amount. You MAY cite it in your reasoning,
> and you MAY describe the role or usage it shows. Your `modeled_probability` must nevertheless
> be exactly the number you would have produced had that dimension been absent entirely. It must
> never be the reason your estimate crosses the candidate's own break-even price, and it must
> never be what creates an apparent edge. One game sits below the evidentiary floor for moving a
> number at all — it is not a small effect to be weighed, it is no effect. This restriction
> applies only at sample_size 1; it does not apply once sample_size is 2 or more.

**This is an evidence floor, not an invented weight.** No deterministic probability math was
added. No EV/Kelly/Risk change. Every market/weather/venue guardrail carried forward
byte-identical.

### 6.2 Safety-flag negation fix

`app/orchestration/context_probability_comparison.py` gained `NEGATION_CUES` /
`NEGATION_WINDOW_CHARS` and a `_mentioned_affirmatively` helper: a keyword only counts when it
appears *without* a negation cue in the preceding 48 characters. Applied to both
`_dimension_mentioned` and the trend-keyword check. Small and isolated — no behavior change
to anything outside these flags.

Four regression tests were added using the **verbatim reasoning text claude-opus-5 actually
produced** in the live run: the two real false positives must not fire, and two affirmative
counter-cases must still fire. **This remains a disclosed keyword heuristic, not semantic
analysis** — the fix narrows a known failure mode, it does not eliminate false positives, and
these flags remain non-gating (they report, they never correct).

---

## 7. What this pass does NOT claim

**No predictive improvement of any kind is claimed.** Three pairs on one day, with no graded
outcomes, measures behavior — not accuracy, not calibration, not edge. The acceptance of the
LLM as base estimator is explicitly **provisional and temporary**.

---

## 8. Cleanup and verification

- `phase8-context-experiment` deleted from dev (see §9 for the retry detail).
- `ai-orchestrator` never touched by the experiment: config, variables, domain and branch all
  unchanged throughout; its only redeployments were the pre-existing dev autodeploy reacting to
  normal `dev` pushes.
- No domain was ever created for the temp service (`serviceDomains: []` for its whole life).
- **No secret value appeared anywhere** in logs or output. The script also ran a final
  redaction pass over its own report as a last-resort safety net.
- Final Anthropic request count: **exactly 6**, never exceeded, never retried.

## 9. Test results

`app/agents/sequential_base.py`, `app/orchestration/context_probability_comparison.py`,
`scripts/generate_prompt_registry_seed.py` (v2 pass), plus 4 new negation tests.
Full `apps/ai-orchestrator` suite: **939 passed, zero regressions** (up from 935).

## 10. Next step (named, not started)

Outcome tracking and probability calibration — the Consensus Engine's graded-outcome pipeline.
Until real settled results exist for recommendations, no calibrated deterministic contextual
adjustment can be designed, and any numeric weight would still be invented. **Not begun this
pass, by instruction.**
