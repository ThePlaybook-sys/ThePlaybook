# Phase 8.5 Pass 4 — Top-N Retrieval Audit and Implementation (2026-09-09)

**Status: implemented, HQ-authorized.** Extends `POST /v1/recommendations/ask`
(Pass 1/2/3) so a user can request multiple ranked recommendations instead of
one — retrieval only, no generation/recomputation. Part B of the same HQ
directive (the Extensible Market & Player-Prop Taxonomy Architecture Lock) is
documented separately: `docs/ops/phase-8.5-part-b-market-taxonomy-architecture-lock-2026-09-09.md`.

## Step 1 — Response contract audit (performed before any code, per HQ's gate)

Traced directly against current source (`app/recommendations.py`,
`app/request_intent.py`), not assumed from prior passes' reports.

1. **Is the result structurally singular?** Yes. `"result": {"label",
   "selectionMetric", "disclosure", "recommendation"} | None` — a single
   object, never a list, in Pass 1/2/3.
2. **Is a new plural field required?** Yes. A single-object field cannot
   represent an ordered list of 1-5 results without either overloading its
   meaning or breaking every existing consumer that reads `result` as one
   card. A new, additive `results` field (list) was the only option that
   avoids both.
3. **Can the existing response be extended compatibly?** Yes, in the sense
   this project's own Pass 2/3 precedent already established (additive keys,
   not a redesign): `result` keeps its exact Pass 1-3 meaning — the single
   top-ranked pick, byte-identical whether the request asked for 1 or 5 — and
   a new `results` key carries the full ranked list actually returned.
   `intent` gains one new key, `count` (the resolved request count), the same
   kind of additive extension Pass 2 (`selectionMetric`) and Pass 3
   (`marketType`) already made to this same object. No field was renamed,
   removed, or given new meaning.
4. **Default count when none requested:** 1 — `_DEFAULT_COUNT` in
   `request_intent.py`. Every Pass 1-3 request path that constructs a
   `ResolvedIntent`/`ExecutionPlan` without an explicit count now gets `1` via
   the dataclass field default, so no existing call site needed editing.
5. **Which existing contract/tests break:** Exactly the same two tests broken
   by Pass 2 and Pass 3's own additive changes — `test_ask_returns_highest_confidence_pick`
   and `test_ask_returns_highest_value_pick` — both assert `body["intent"] ==
   {...}` as an exact 4-key dict; adding `count` makes that a 5-key dict. Fixed
   the same way Pass 2/3 fixed their own analogous breaks: added the new key's
   expected value (`"count": 1`) to both literal dicts, plus a new assertion
   (`body["results"] == [body["result"]]`) proving the new field's default-count
   behavior. No other test in the 147-test baseline does whole-body or
   whole-`intent` equality, so no other test needed touching. **No major
   response-contract redesign was required** — the extension is additive
   throughout.

**Verdict: proceed with the additive design.** No STOP was triggered.

## Step 2 — Request count grammar

`app/request_intent.py`: `_match_requested_count(text) -> (count, over_max_reason)`.

**Supported forms, exhaustive:**
- Digit form: `top <digits>` (regex `\btop\s+(\d+)\b`) — any positive
  integer is captured, then range-checked; not limited to 1-5 by the regex
  itself, so an over-ceiling digit request (`top 12`) is recognized and
  honestly rejected rather than silently falling through as unrecognized text.
- Word form: `top <word>`, word drawn from a fixed, bounded 10-entry lookup
  table (`one`..`ten`) — not a general number-word parser. Bounded to ten
  (twice the ceiling) so both in-range wording (`top three`) and the most
  common over-ceiling wording (`top ten`) resolve honestly; a word above
  "ten" (`top twelve`) is simply not recognized as a count phrase at all and
  falls through to whatever the rest of the sentence resolves to — a
  documented, deliberate scope limit, not a silent gap.

**Explicitly NOT supported, per HQ's own instruction:** a bare number
anywhere else in the sentence. `"give me 5 highest confidence picks"` does
**not** resolve count=5 — no `top` keyword, so it resolves count=1 (the
default), exactly like every Pass 1-3 request. Proven by
`test_resolve_intent_bare_number_does_not_auto_resolve_count` and
`test_ask_bare_number_never_auto_resolves_a_count`.

**Default:** `count = 1` whenever no `top <N>` phrase is recognized —
byte-identical to every existing Pass 1-3 request. Verified: full 147-test
baseline passes unmodified except the two documented additive-key updates
(Step 1 item 5); every Pass 1-3 phrase list, alias, and unsupported-wording
proof re-passes unchanged.

**Order in the resolver:** count is matched last, after the known-unsupported
check, selection-mode match, and market-type match all succeed — mirroring
Pass 3's own precedent that a market constraint is "only ever recognized
alongside a recognized selection-mode phrase." A count phrase never overrides
or is shadowed by any of those checks; `"top 3 safest picks"` still resolves
UNSUPPORTED (the "safest" guardrail fires first, before count is even
examined) — proven by `test_resolve_intent_top_n_never_shadows_unsupported_terminology`.

## Step 3 — Bounding the count

**Ceiling: 5** (`_MAX_SUPPORTED_COUNT`), the HQ-preferred initial value — no
architectural finding argued for a different number.

**Over-max behavior:** a recognized `top <N>` phrase with `N > 5` resolves
`RequestType.UNSUPPORTED` with an honest reason naming the limit (`"MANSA
supports up to the top 5 recommendations per request..."`) — the same
structured-rejection shape already used for "safest"/"parlay"/unsupported
markets. **No retrieval is attempted at all** for an over-max request — proven
by `test_ask_over_max_count_is_rejected_honestly_never_silently_truncated`
registering zero `recommendation_products`/`legs`/`games` mocks; respx would
fail the test if the endpoint tried to reach any of them, exactly the same
proof mechanism Pass 1-3 used for their own rejected-request paths. This
directly satisfies HQ's instruction: never silently return a subset (e.g. 5
of the 6 asked for) while pretending the full request was honored.

## Step 4 — Filter, then rank, then limit (mandatory order)

`app/recommendations.py`: `_select_highest_confidence_card`/
`_select_highest_value_card` replaced by one shared `_rank_and_limit` helper
(plus two thin, metric-specific wrappers, `_select_highest_confidence`/
`_select_highest_value`, preserving `_RETRIEVAL_MODES`'s existing data-driven
dispatch pattern unchanged). Implements the exact mandated order in one pass:

1. Iterate only *active* cards' legs (unchanged from Pass 1-3 — withdrawn
   products are never presented as "a pick").
2. Apply the market filter, if present, **inside the same loop** — a leg from
   a different market is never even added to the candidate list, let alone
   ranked (Pass 3's filter-before-rank rule, unchanged, now shared by every
   caller through the one helper instead of being duplicated per selection
   function).
3. Apply the existing qualification/eligibility constraints: skip a `None`
   metric (never treated as zero); for `evPerDollar`, also skip non-positive
   values (Pass 2's defensive check, preserved via `require_positive=True`).
4. Sort the **surviving** candidates by the requested objective descending
   (`finalAggregateConfidence` or `evPerDollar`), with a deterministic
   tiebreak (Step 6, below).
5. Return the first `count` entries.

Verified directly against HQ's own worked example: "top 3 highest-confidence
spreads" = FILTER market=spread → SORT by confidence desc → TAKE 3, **not**
global-top-3-then-remove-non-spreads and **not** single-best-spread-then-invented-
filler. Proven by `test_ask_market_scoped_top_3_filters_before_ranking_never_admits_stronger_other_market_leg`,
which engineers a moneyline leg at confidence 0.99 — far stronger than any of
the three spread legs (0.80/0.75/0.70) — and confirms it never enters a
`top 3 highest-confidence spread` result, which returns exactly the three
spread legs ranked among themselves.

## Step 5 — Fewer than N results

When fewer than `count` legs qualify, `_rank_and_limit` returns exactly what
survived filtering — `ranked[:count]` on a shorter-than-`count` list is simply
the whole list, in Python, with no padding logic to write or forget. **Never**
fabricated filler, **never** a fallback to a different market or metric to
fill the remaining slots. Proven by
`test_ask_fewer_than_n_returns_only_what_qualifies_never_fabricates_or_falls_back`
(4 candidate legs, one null-EV and one negative-EV correctly excluded by
existing defensive checks, `top 5` requested, exactly 2 returned) and
`test_ask_market_scoped_top_n_with_zero_qualifying_is_honest_insufficient_evidence`
(0 qualify, `top 3` requested).

**`insufficientEvidence`/partial-success semantics — smallest consistent
choice, per HQ's own instruction to pick the smallest one:** `insufficientEvidence`
stays exactly what it already meant in Pass 1-3 — `true` only when **zero**
results qualify, `false` whenever at least one real result was found and
returned, regardless of whether that's fewer than requested. No new
tri-state/partial-success flag was invented. The actual returned count is
already unambiguous from `len(results)` plus the `intent.count` that was
requested — a client can trivially detect "got fewer than asked" without a
new field, so no new field was added for this. `results` itself distinguishes
the two zero-result cases that were previously collapsed into `result: null`
in every prior pass: `results: null` means **nothing was attempted at all**
(a rejected/unsupported/ambiguous request — the request never reached
retrieval), while `results: []` means **retrieval was attempted and genuinely
found nothing** (the existing `insufficientEvidence: true` case). This mirrors,
rather than replaces, `result`'s own pre-existing null-in-both-cases behavior.

## Step 6 — Ties

Strategy Engine's own `rank_key` (`ai-orchestrator/app/features/strategy.py:158-163`)
uses `(-ev_per_dollar, -final_aggregate_confidence, candidate_key)` — `candidate_key`
ASC as its final, purely deterministic (explicitly documented as "never a
quality signal") tiebreak. **Audited and found not directly reusable in this
context**: `candidate_key` is a generation-time field, present on
`EvaluatedCandidate`/`recommendation_agent_outputs`, but never persisted to
`recommendation_legs` and never exposed by `_serialize_leg` — the already-
serialized card/leg data this endpoint's selection functions operate on
simply does not carry it. Reusing it directly would require adding a new
field to the serialized leg contract (and, transitively, to every other route
in this module that reuses `_serialize_leg`), which is a response-contract
expansion Pass 4 was not authorized to make.

**Minimum equivalent added instead**: `displayId` (globally unique per
product, already present on every serialized card) ascending, then `legOrder`
(already present per leg) ascending, as the final tiebreak — `ranked.sort(key=lambda
row: (-row[0], row[1], row[2]))` in `_rank_and_limit`. This mirrors Strategy
Engine's own design intent exactly (a stable, deterministic, non-quality-
signal final tiebreak) without inventing new ranking logic, exposing a new
field, or redefining Strategy Engine's own ranking anywhere. Proven
deterministic by `test_ask_top_n_tied_values_produce_deterministic_ordering`,
which deliberately lists the higher-`displayId` product first in the fixture
to prove the ordering isn't accidentally just preserving input/arrival order.

## Step 7 — Terminology

Unchanged. "highest confidence" → `final_aggregate_confidence`; "highest
value" → `ev_per_dollar`; neither is a synonym for "best." Every phrase in
`_KNOWN_UNSUPPORTED_PHRASES`/`_UNSUPPORTED_MARKET_PHRASES` still resolves
UNSUPPORTED regardless of an accompanying `top N` phrase — proven directly by
`test_resolve_intent_top_n_never_shadows_unsupported_terminology`,
`test_ask_top_n_never_shadows_best_pick_unsupported_wording`, and
`test_ask_top_n_existing_market_aliases_still_work`. No new terminology
(safest/guaranteed/most likely to win/conservative/aggressive/strongest
parlay/player- or team-specific/arbitrary sport filtering/NL LLM
interpretation) was introduced or authorized.

## Step 8 — Tests

**28 new tests** — exceeding HQ's 19 required proof points, several HQ
categories covered by more than one test for thoroughness:
- 12 pure unit tests, `test_request_intent.py` (count defaulting, digit/word
  recognition, count+market+value combined, bare-number non-resolution,
  over-max digit/word rejection, exact-ceiling acceptance, terminology-
  guardrail non-shadowing, unsupported-market-ignores-count, execution-plan
  count threading for both the lookup and the rejected paths).
- 16 integration tests, `test_recommendations_ask.py` (default-count-
  unchanged, top-3 confidence ordering, top-3 value ordering, digit/word
  equivalence, market-scoped top-3 filter-before-rank with a deliberately
  stronger cross-market leg, fewer-than-N with mixed null/negative EV,
  market-scoped zero-qualifying honesty, over-max digit/word rejection with
  zero-retrieval proof, bare-number non-resolution, terminology non-shadowing,
  market-alias-plus-count combination, deterministic tie ordering, auth
  unchanged, no-unmocked-host proof, `result == results[0]` invariant).

**Full api-gateway suite: 175/175 passing** (147 pre-existing + 12 unit + 16
integration), **zero regressions** — confirmed by running the full suite
before adding any Pass 4 test (147/147, with only the two documented
additive-key updates) and again after (175/175).

```
$ python3 -m pytest -q
........................................................................ [ 41%]
........................................................................ [ 82%]
...............................                                          [100%]
175 passed, 1 warning in 18.33s
```

## No provider/external-call confirmation

Unchanged mechanism from Pass 1-3: every Pass 4 test registers respx mocks
only for the hosts it actually expects to be contacted (Supabase auth/REST
tables) — no ai-orchestrator, no provider, no worker host is ever mocked
anywhere in this pass's tests. respx fails a test on any unmatched request,
so every passing test is itself the proof. The over-max-count tests go
further: they register **zero** recommendation-table mocks at all, proving
retrieval is never even attempted for a rejected request.

## No worker/recomputation confirmation

`_rank_and_limit` and its two wrappers are pure, synchronous, in-memory
functions over already-serialized card/leg dicts — no new I/O, no new query,
no call to `call_ai_orchestrator`, Master Refresh, Probability Modeling, or
Consensus anywhere in this pass's diff. The one existing I/O call in the
route (`_todays_visible_products`) is unchanged from Pass 1.

## What was and wasn't done

Implemented exactly the objective HQ authorized: Top-N retrieval (filter →
rank → limit) up to a ceiling of 5, deterministic count-phrase recognition
(`top <digit>`/`top <word>`, bounded), honest over-max/fewer-than-N/zero-
qualifying behavior, a documented tiebreak. **Not implemented, deliberately**:
per-item rank labeling (`"#1 pick"`/`"#2 pick"`) — every item in `results`
shares the same `label` text (e.g. "MANSA's highest-confidence spread pick
today"), since HQ's directive didn't request distinct per-rank labels and
inventing one would be unauthorized scope; a new partial-success flag (Step
5's smallest-consistent-behavior decision); reusing `candidate_key` directly
(Step 6, would require a response-contract field addition beyond what was
authorized); parlays, player-specific requests, conservative/aggressive
modes, a "best pick" definition, LLM parsing, on-demand computation, sport
expansion, market-system redesign, any schema migration, staging, production.

## Contradictions discovered with the Architecture Lock (Part B)

None that required deviating from this pass's implementation. One notable
finding, documented in Part B rather than fixed here: the directive's own
illustrative phrase "top 2 best-value totals" (hyphenated) does not literally
match `_HIGHEST_VALUE_PHRASES` (`"best value"`, space, is recognized;
`"best-value"`, hyphen, is not) — a pre-existing, minor coverage gap in Pass
2's own phrase list, outside Pass 4's mandate to fix (Step 7: "preserve all
existing rules exactly"). Every test in this pass uses phrasing that does
match the existing lists (`"best value"`/`"highest-value"`/`"highest value"`).
