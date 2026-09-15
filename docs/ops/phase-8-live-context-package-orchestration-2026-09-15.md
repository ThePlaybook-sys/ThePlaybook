# Phase 8 Live Context Package Orchestration (2026-09-15)

MANSA HQ directive: "PHASE 8 LIVE CONTEXT PACKAGE ORCHESTRATION." Wires
`app/orchestration/cycle.py` so real candidates actually receive a real
`ContextPackage`, built through the existing, unmodified Context
Intelligence engine -- `build_evidence()` remains the sole admission
gate, unchanged. No probability math, no new weights, no historical
replay support.

---

## 1. Exact `cycle.py` wiring

One new private helper, one new optional parameter, three lines wired
into the existing function -- `apps/ai-orchestrator/app/orchestration/
cycle.py`:

```python
async def _attach_context_package(client, headers, *, game_id, player_id) -> ContextPackage | None:
    try:
        now = datetime.now(timezone.utc)
        intelligence = await build_contextual_intelligence(client, headers, game_id=game_id, player_id=player_id, now=now)
        return assemble_context_package(intelligence, player_id=player_id, target_event_timestamp=now.isoformat())
    except Exception:
        _logger.warning("Context Intelligence package construction failed ... -- continuing without contextual evidence", exc_info=True)
        return None


async def run_candidate_evaluation(..., player_id: str | None = None) -> SharedCandidateChainResult:
    context_package = await _attach_context_package(client, headers, game_id=game_id, player_id=player_id)
    context = SequentialDecisionContext(..., context_package=context_package)
    ...
```

**No Context Intelligence logic is reimplemented** -- `_attach_context_
package` calls only the existing, unmodified `app.context_intelligence.
engine.build_contextual_intelligence` and `app.context_intelligence.
context_package.assemble_context_package`, exactly as the prior two
passes built and tested them. `run_candidate_evaluation`'s own downstream
logic (the shared chain, persistence, candidate-key tagging) is
byte-identical except for the two new lines shown above.

**No other file was touched.** `recommendation_worker.py` (the real
production caller of `run_candidate_evaluation`, via `_evaluate_one_
candidate`) is unmodified -- it does not pass `player_id`, so every real
production call today gets `player_id=None` (Section 8).
`probability_modeling.py`/`context_package.py`/`engine.py` are all
unmodified.

---

## 2. Only admitted dimensions reach modeling -- unchanged, verified

`cycle.py` attaches the **full, unfiltered** `ContextPackage` (all ten
dimensions, exactly as the engine produces) -- it does not read, import,
or duplicate `ADMITTED_CONTEXT_DIMENSIONS`, and does not special-case any
blocked dimension. Filtering to the four admitted, non-unavailable
dimensions happens exactly where the prior pass put it: inside
`ProbabilityModelingAgent.build_evidence`, unchanged. The real live-path
proof (Section 5) confirms this end to end: all six blocked dimensions
remain absent from `contextual_evidence` even though the attached
`ContextPackage` itself computed real results for them (the four
`unsupported.py` stubs, plus `news`, which the engine still, correctly,
computes as `unavailable` for this real game).

---

## 3. Live-only safety

**Structurally live-only, not just by convention.** `_attach_context_
package` always uses real wall-clock time (`datetime.now(timezone.utc)`)
-- there is no parameter anywhere on its own signature, or on `run_
candidate_evaluation`'s public signature, that lets a caller backdate
`target_event_timestamp`. This was a deliberate design choice: exposing
such a parameter (even for testing convenience) would itself be the one
thing that could turn the market/weather comparable-pool evidence
(undisclosed-until-the-Admission-Decision point-in-time gap) unsafe.

**No historical/replay execution path exists in this codebase.**
Confirmed by direct search this pass: `grep -rli "replay\|backtest"
app/` across the entire `apps/ai-orchestrator` tree returns only this
pass's and the prior pass's own disclosure text in `probability_
modeling.py` -- no actual replay/backtest code path, flag, or mode
exists anywhere in `app/orchestration/` or elsewhere. `run_candidate_
evaluation`/`_evaluate_one_candidate` (`recommendation_worker.py`) are
exclusively live-call sites. **Per the directive's own instruction, this
pass does not build replay/backtest support, and did not encounter a
historical/replay execution path to stop and report on** -- there is
none today.

The market/weather live-only caveat text (`_COMPARABLE_POOL_LIVE_ONLY_
CAVEAT`, `probability_modeling.py`, unchanged this pass) continues to
travel into every real `contextual_evidence` payload exactly as the
prior pass established.

---

## 4. Failure behavior

**Additive, isolated, never fails the cycle.** `_attach_context_package`
catches every exception (a deliberate, disclosed, narrow-purpose broad
`except Exception` -- justified specifically because this is a genuinely
optional, additive enrichment step whose failure must never propagate
into a real recommendation cycle, unlike this codebase's normal
discipline of raising typed exceptions for its core computations), logs
a `_logger.warning` naming the `game_id`/`player_id` and the real
traceback (`exc_info=True`), and returns `None`. `build_evidence()`
already treats `context.context_package is None` identically to "no
Context Intelligence attempted" -- the exact same code path every real
call used before this pass existed.

**Proven directly**: `test_context_package_construction_failure_does_
not_fail_candidate_evaluation` -- zero Context Intelligence boundaries
mocked at all (respx's own unmocked-request error fires internally,
caught, logged) -- `chain_result.status == "full"`, all 3 shared-chain
outputs still persist, `chain_result.context.context_package is None`.

**Partial/unavailable dimensions never become zero** -- unchanged,
already-proven behavior from the two prior passes
(`assemble_context_package`'s own derivation rule, `build_evidence()`'s
own admission-gate exclusion of `unavailable`-completeness admitted
dimensions) -- this pass adds no new logic here, only the plumbing that
lets that already-correct behavior reach a real candidate.

---

## 5. Real live-path proof

`test_jsn_sea_ne_live_path_cycle_to_build_evidence`
(`tests/orchestration/test_cycle_candidate.py`) runs the full real chain
-- `run_candidate_evaluation` (cycle.py) -> the real Context Intelligence
engine -> a real `ContextPackage` -> a real `SequentialDecisionContext`
-> `ProbabilityModelingAgent().build_evidence()` -> `contextual_evidence`
-- using the exact same real, live-queried DEV values (2026-09-15) every
prior pass in this series used, with `player_id=JSN_PLAYER_ID` passed
explicitly (simulating the one real future caller shape this codebase
doesn't have yet -- see Section 8).

Confirms directly:

- `chain_result.context.context_package` is a real `ContextPackage`
  (`player_id == JSN_PLAYER_ID`).
- **venue reaches `contextual_evidence`.**
- **`player_performance` reaches `contextual_evidence` with the real
  stat line**: `role_usage_signals["receiving"] == {"targets": 11,
  "receptions": 8, "recYards": 122, "recTD": 1}`.
- **market reaches `contextual_evidence`**, `completeness == "joined"`.
- **weather reaches `contextual_evidence`**, `completeness == "partial"`.
- **Blocked dimensions remain excluded**: `news`/`injuries`/
  `roster_role`/`team_performance`/`depth_lineup`/`game_state_pbp` all
  absent.
- **No context-derived confidence anywhere** (recursive key scan across
  the entire `contextual_evidence` payload).
- **No probability calculation changes**: `chain_result.probability.
  modeled_probability == 0.57` and `.confidence_in_probability == 0.72`
  -- exactly the `FakeModelAdapter`'s own scripted values, unaffected by
  whether contextual evidence was attached (the LLM call itself is
  mocked identically either way; only the evidence dict handed to it
  differs).
- **No recommendation-ranking change**: `chain_result.status == "full"`,
  identical to every pre-existing test of this same function.

---

## 6. Regression results

- **Candidates with no `ContextPackage` behave exactly as before**:
  every one of the 8 pre-existing `test_cycle_candidate.py` tests (none
  of which mock any Context Intelligence boundary) passes unmodified --
  `_attach_context_package` degrades to `None` internally for all of
  them, exactly reproducing pre-pass behavior.
- **Existing cycle behavior remains unchanged apart from additive
  evidence**: `test_cycle.py`'s 3 tests (covering `run_recommendation_
  cycle`, a different function this pass didn't touch at all) pass
  unmodified.
- **Probability outputs remain unchanged**: proven directly in the real
  proof (Section 5) -- the scripted `FakeModelAdapter` output is
  byte-identical whether or not `contextual_evidence` was attached to
  the evidence dict handed to it.
- **Recommendation outputs remain unchanged**: `chain_result.status`/
  `.ev`/`.risk` unaffected in every test.
- **Existing tests remain green**: full `apps/ai-orchestrator` suite --
  **929 passed, zero regressions** (up from 926; +3 new tests in this
  pass: construction-failure, successful-attachment, and the full real
  live-path proof).

---

## 7. Performance / read impact

**One `ContextPackage` construction per `run_candidate_evaluation` call
-- never more than once per candidate, no duplicate calls introduced
within this function.** No caching was added (per the directive's own
"do not add caching unless needed" instruction).

**Honest disclosure of real read cost, not claimed away**: one full
`build_contextual_intelligence` call (with `player_id` set) issues
roughly a dozen real Supabase reads -- the four Phase 8.1 dimensions'
own existing reads (`games`, target + all `odds_snapshots`, all
`weather_snapshots`, team-name resolution + `news_article_history`,
conditional `venues`/`games`-sharing-venue), plus, when `player_id` is
given, `player_performance`'s own reads (`players`, this player's
`player_stats`, the referenced `games`, and `resolve_team_identity_for_
games`'s own composed reads: `game_events` + `team_provider_ids` +
`teams`). **All of these are real, already-existing, already-tested
reads this pass invented none of** -- `_attach_context_package` composes
them, it does not add a new one.

**A real, disclosed optimization opportunity exists but was NOT built
this pass**: multiple candidates for the SAME `game_id` within one
recommendation cycle each currently trigger their own, fully independent
`_attach_context_package` call -- the game-level dimensions (venue/
market/weather, which don't depend on `player_id`) could in principle be
constructed once per game per cycle and reused across candidates. Doing
so would require changes to `recommendation_worker.py`'s own candidate-
iteration loop (out of this pass's authorized scope, which named only
`cycle.py`) and/or explicit caching (which the directive explicitly says
not to add "unless needed" -- not established as needed by this pass).
Named here as the honest next-step candidate, not silently built.

---

## 8. Remaining limitations

- **`player_id` has no real source in production today.** `MarketCandidate`
  carries no structured player identity -- a `"prop"` candidate's player
  is only ever free text inside `selection`. This pass deliberately does
  NOT attempt to parse/match that text against a real player (the same
  fuzzy-matching-as-identity-resolution risk this whole Context
  Intelligence effort has avoided elsewhere). `run_candidate_evaluation`
  accepts an optional `player_id` for a future caller that has one;
  `recommendation_worker.py`'s real call site does not supply one, so
  **`player_performance` legitimately resolves to `unavailable` for
  every real live candidate today** -- an honest reflection of real
  capability, not a bug.
- **The market/weather comparable-pool point-in-time gap remains only
  documentation-level protected**, unchanged from the prior pass -- no
  code-level enforcement exists because no replay-mode concept exists to
  enforce against.
- **The same-game, cross-candidate read-reuse optimization (Section 7)
  is a real, identified opportunity, not built.**
- **`news`'s team-identity bug remains unfixed**, exactly as instructed
  across every pass in this series -- still blocked (C), untouched.
- **No trend/consistency scoring, no new weights, no probability
  adjustment** -- exactly as instructed; `build_evidence()`'s own
  contract (unchanged) still produces no confidence/probability from
  context anywhere.
- **This is still a one-game proof for `player_performance`.** No second
  real historical game exists for any player yet (unchanged conclusion
  from every prior pass in this series).

---

## 9. Exact next step for determining HOW contextual evidence should influence probability estimates

**This is explicitly a modeling-design question, not an implementation
one, and this pass does not answer it** (out of scope: "do not change
probability math yet"). The concrete next decision HQ would need to make:

1. **Where does the influence happen?** Two structurally different
   options exist today: (a) the LLM itself reads `contextual_evidence`
   as part of its prompt (already true today, automatically, since
   `build_messages` JSON-serializes the full evidence dict `build_
   evidence()` returns -- the model already "sees" venue/player_
   performance/market/weather context on every call where a `Context
   Package` is attached, and may already be informally weighing it in
   its own `modeled_probability`/`reasoning`, with zero code guarantee
   about how); or (b) a new, explicit, deterministic adjustment step
   (mirroring how EV/Risk/Kelly are already computed in application code
   between agent calls, never inside an agent's own `build_evidence`)
   that takes `contextual_evidence` and produces a numeric adjustment to
   `modeled_probability` before/after the LLM call. These are very
   different architectural choices with different risk profiles (b)
   requires a real, disclosed formula (weights, thresholds) the way
   `app/features/kelly.py`/`app/features/expected_value.py` already do
   for their own domains; (a) requires no new code but means the model's
   own use of context is currently unaudited/unconstrained (correctly
   inherited by this pass's prompt-inclusion, not newly introduced).
2. **What evidence is "enough" to move a probability?** `sample_size`/
   `completeness` (`joined` vs. `partial`) are already honest signals
   this pass carries into the payload -- but nothing today defines a
   rule like "a `partial` weather reading may adjust the total by at
   most X" the way `INSUFFICIENT_SAMPLE_FLOOR`/`MIN_SAMPLE_FOR_FULL_
   CONFIDENCE` already define thresholds for Context Intelligence's own,
   separate `confidence`/`similarity_score` concept (never conflated
   with probability, per every prior pass's own discipline).
3. **Does this require reopening Phase 4's consensus/weighting design**
   (Volume 4's own committee-weighting scheme), or is Probability
   Modeling's own `modeled_probability`/`confidence_in_probability`
   output the right place to absorb it? This is squarely a Volume 4
   design decision, not a code question this pass can resolve.

This document's own implementation makes no probability-calculation
change, no new weight, no context-derived confidence, and no
recommendation-ranking change -- confirmed by the regression suite
(Section 6) and the real proof (Section 5).
