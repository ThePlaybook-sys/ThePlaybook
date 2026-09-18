# Pre-LLM Eligibility Gate + Fan-Out Reorder (2026-09-18)

**Directive:** MANSA HQ — all cheap deterministic eligibility checks must happen before any LLM agent
executes; and verify a true run-level ceiling exists at the outbound model adapter boundary.

**Compliance:** zero LLM calls. Zero provider calls. `REFERENCE_SPORTSBOOK_PREFERENCE` **not set**.
No semantic change to scoring, probability, EV or candidate construction. Dev only.

**Owner decisions carried in:** `MAX_GAMES_PER_RUN = 20` kept. Approved hierarchy
`draftkings,fanduel` recorded, not yet applied.

---

## 1. Old execution order

`run_game_recommendation`, as it stood:

| # | Step | Cost |
|---|---|---|
| 1 | `get_game` | free |
| 2 | idempotency (`cycle_completed_at`) | free |
| 3 | **`run_recommendation_cycle` — creates the `recommendations` row, runs 6 game-level agents** | **6 LLM calls** |
| 4 | `read_odds_snapshots` + `generate_candidates_for_game` — *and* `reference_sportsbook_preference()` | free |
| 5 | `read_active_subscribers` | free |
| 6 | per candidate: shared chain, consensus, Elite, Bankroll Coach | LLM |

**Every deterministic reason to refuse a game sat at step 4, one step after the spend.** A game with
no odds, stale odds, or no configured book still cost 6 calls to discover it was ineligible. An
unset `REFERENCE_SPORTSBOOK_PREFERENCE` raised at step 4 too — which is why the 2026-09-17 06:15 run
invoked the committee on all 257 games before anything could stop it.

## 2. New execution order

| # | Step | Cost |
|---|---|---|
| 1 | `get_game` (canonical game exists) | free |
| 2 | *(caller)* upcoming / authorized horizon | free |
| 3 | idempotency — `cycle_completed_at` set → `skipped_already_computed` | free |
| 4 | `read_odds_snapshots` | free |
| 5 | `generate_candidates_for_game` — reference sportsbook + freshness + V1 markets | free |
| 6 | **no candidates → return `skipped_ineligible`, zero fan-out, explicit reason** | **free** |
| 7 | **── LLM authorized only past this line ──** | |
| 8 | `run_recommendation_cycle` — 6 game-level agents | LLM |
| 9 | `read_active_subscribers` | free |
| 10 | per candidate: probability → EV → risk → meta → Elite → Bankroll Coach | LLM |

`generate_candidates_for_game` is called with **identical arguments**. Only *when* changed. No
invented odds, no invented candidates, no change to probability or EV.

## 3. Deterministic prerequisites before any LLM

| Prerequisite | Enforced by | Where |
|---|---|---|
| canonical game exists | `get_game` → `RecommendationWorkerError` (404) | orchestrator |
| not final / live / postponed / canceled | `status='scheduled'` in the query | worker |
| genuinely upcoming | `scheduled_start >= now` | worker |
| inside the authorized horizon | `scheduled_start < now + 7d` | worker |
| **fresh odds available** | `_is_fresh` vs `max_snapshot_age_seconds` | orchestrator, **now pre-LLM** |
| provider identity resolved | `odds_game_linking` (odds only exist for linked games) | upstream |
| **configured reference sportsbook available** | `select_reference_sportsbook` | orchestrator, **now pre-LLM** |
| retry/backoff eligibility | `cycle_completed_at` (orchestrator) + consecutive-identical-failure breaker (worker) | both |
| run-level cost/budget gate | `max_games_per_run()` fail-closed | worker |

A game failing any of these gets: **zero LLM calls, zero fan-out**, an explicit
`game_skipped_reason`, no `recommendations` marker row (so it retries cleanly once odds arrive), and
Sentry visibility through `cron_dispatch`'s nested-failure census when the outcome is abnormal.

## 4. Hard max games per run

**`MAX_GAMES_PER_RUN = 20`**, unchanged, env `RECOMMENDATION_MAX_GAMES_PER_RUN`. Fail closed: a
larger slate dispatches **nothing** rather than being truncated and reported complete.

## 5. Hard max LLM requests per run — now counted, not assumed

HQ's requirement was explicit: do not rely on `games × assumed calls/game`. That is an estimate
about code, not a control over it — it holds only until someone adds an agent, a retry or a loop.

**`app/models/budget.py`** puts the ceiling at the outbound boundary:

```
Agent → ModelRouter.route → AdapterRegistry.get → ModelAdapter.complete
                                                   ↑ counted here
```

`complete()` is the only method that reaches a provider, which makes wrapping it both **sufficient**
(nothing else talks to a provider) and **necessary** (counting higher counts *intentions*, and the
retry engine turns one intention into several real requests).

- `CallBudget(limit)` — one allowance shared across **all** providers, so anthropic and openai spend
  the same pool.
- `BudgetedModelAdapter` — implements `ModelAdapter`, so the router, retry engine and every agent
  are unaware of it. That is what makes the ceiling unbypassable rather than merely conventional.
- **Counts before the request, never after.** A request that was sent and then failed has still been
  spent; counting on success would let a retry storm walk straight through the ceiling.
- Breach raises `LlmBudgetExceededError` — deliberately **not** an `app.models.errors` type, because
  those are per-attempt provider failures the retry engine is built to absorb and retry, which is
  the exact opposite of what a budget breach must do. The endpoint surfaces it as **HTTP 429**: a
  deliberate refusal by a control, not a fault.

**`MAX_LLM_CALLS_PER_GAME = 48`** (env-overridable), set *at* the committee's legitimate maximum
rather than above it: 6 game-level + 6 candidates × (3 shared chain + 1 Meta + 1 Elite) + Bankroll
Coach per active subscriber per candidate = 6 + 30 + 12 at dev's 2 subscribers.

| | |
|---|---|
| Hard max LLM requests **per game** | **48**, refused at the adapter |
| Hard max games per run | **20**, fail closed |
| **Hard max LLM requests per run** | **960** |
| Expected real 16-game slate | ≈ 768 |

**Flagged for HQ:** the subscriber term is the one that genuinely grows with the business. That is
precisely why it is an env var — raising it must be a deliberate, reviewable act, not something that
happens silently as users sign up. A breach is the signal to raise it consciously.

## 6. Failure / backoff behaviour

| Condition | Behaviour |
|---|---|
| no / stale odds, or no configured book | `skipped_ineligible`, 0 LLM, no marker row, retries freely next cycle |
| unset `REFERENCE_SPORTSBOOK_PREFERENCE` | `ConfigError` **before** any agent (was: after 6) |
| already-completed cycle | `skipped_already_computed`, 0 LLM |
| deterministic fault repeating across games | worker halts after 3 identical failures |
| slate over the ceiling | worker dispatches 0, `status="failed"` |
| per-game LLM ceiling breached | adapter refuses, HTTP 429 |

**No orphan marker rows for ineligible games** — the row is created inside `run_recommendation_cycle`,
which now runs *after* the gate. This is a behaviour change, and a deliberate one: previously a
permanently-ineligible game produced one `recommendations` row per run forever.

## 7. Sentry behaviour

Unchanged from the fix shipped 2026-09-17 and still correct here: `_nested_failure_census` inspects
`games`/`legs`/`products`/`items` **before** trusting a known-good top-level status. All items failed
→ `error`; some → `warning`; none → silent. A `skipped_ineligible` game carries no `error` and no
`status="failed"`, so **a slate that is simply not ready stays quiet** — which is the correct
behaviour for an NFL week where most days have nothing to price.

## 8. Tests and regressions

New: `apps/ai-orchestrator/tests/test_pre_llm_eligibility_gate.py` (13 tests).

| # | Property | Test |
|---|---|---|
| 1 | no odds → 0 LLM | `test_no_odds_means_zero_llm_calls` |
| 2 | stale odds → 0 LLM | `test_stale_odds_means_zero_llm_calls` |
| 3 | reference sportsbook unavailable → 0 LLM | `test_reference_sportsbook_unavailable_means_zero_llm_calls` |
| 3b | unset preference → 0 LLM | `test_unset_sportsbook_preference_costs_zero_llm_calls` (the 2026-09-17 shape) |
| 4 | final / out-of-horizon → 0 LLM | worker-side, `test_recommendation_worker_safety_gate.py` (2026-09-17) |
| 5 | retry/backoff suppressed → 0 LLM | `test_already_completed_cycle_costs_zero_llm_calls` + worker-side breaker |
| 6 | eligible game reaches fan-out | `test_eligible_game_reaches_fan_out` — the test that fails if the gate were too strict |
| 7 | `MAX_GAMES_PER_RUN` > 20 fails closed | worker-side (2026-09-17), 257 vs 20 → 0 dispatches |
| 8 | ceiling cannot be exceeded | `test_budget_refuses_at_the_adapter_boundary`, `test_budget_counts_before_the_request_so_failures_still_spend`, `test_ceiling_holds_end_to_end_through_a_real_game`, `test_budget_is_shared_across_providers`, `test_budgeted_registry_adds_a_ceiling_never_a_provider` |
| 9 | partial/failed run Sentry-visible | worker-side census tests (2026-09-17) |
| 10 | clean run non-reportable | worker-side census tests (2026-09-17) |
| 11 | zero real LLM/provider calls | `test_no_real_provider_call_is_reachable_from_this_suite` — structural |

**Regression: ai-orchestrator 1000/1000, workers 84/84**, sports-intel-layer unchanged this pass
(not modified; same 5 pre-existing wall-clock failures as previously recorded).

**Three existing tests were updated, and it is worth saying exactly why** rather than leaving it to
a diff:

- `test_run_game_success_round_trip_with_no_qualifying_sportsbook` asserted that a
  `recommendations` row (`r1`) was created for a game with no odds. That was true, and it was the
  defect. It now asserts the new contract: `skipped_ineligible`, `recommendation_id is None`, zero
  agent-output writes, zero marker rows.
- The two idempotency tests passed `odds_rows=[]`, which now short-circuits before the committee.
  They were given **qualifying odds and a pinned `now`**, so they still test what they were written
  to test — retry semantics — rather than accidentally testing the new gate.

## 9. Would any eligible Week 2 game reach an LLM today?

**Yes — 15 of 16.** This changed since the last pass: the odds worker has ramped and
`odds_worker_poll_state` now holds 16 rows (was 0).

Measured at **2026-09-18 12:04 UTC**, freshness ceiling = FAR tier 86400s + 300s grace = **1445
minutes**:

| Games | Hours to kickoff | Odds age | Verdict |
|---|---|---|---|
| 10 | 52.4 – 83.6 | 1208 min | **fresh** (237 min margin) |
| 5 | 52.4 – 55.8 | 1417 min | **fresh** (**28 min margin**) |
| 1 (GB @ ATL) | 155.6 | no DK/FD odds | correctly skipped, zero cost |

All 15 carry all 3 V1 markets (moneyline, spread, total) from DraftKings or FanDuel.

**One honest caveat:** five games sit **28 minutes** from their freshness ceiling. The `*/15` odds
worker should refresh them well before that, but if a refresh were missed those five would fall to
`skipped_ineligible` — costing nothing and retrying next cycle, which is the gate behaving correctly
rather than a failure.

## 10. Is it safe to set `REFERENCE_SPORTSBOOK_PREFERENCE=draftkings,fanduel`?

**Yes. The architectural blocker named in the last directive is closed.**

Every deterministic prerequisite now precedes the committee; an ineligible game costs exactly zero
model requests; the per-game ceiling is refused at the adapter rather than assumed; the run ceiling
of 20 games fails closed; and a total failure can no longer hide inside a `completed` status.

Worst case if every check passed on a full slate: **≤960 model requests**, ~768 expected.

## 11. Exact next step for the first legitimate pre-kickoff recommendation

1. **HQ sets** `REFERENCE_SPORTSBOOK_PREFERENCE=draftkings,fanduel` (lowercase) on
   `ai-orchestrator` **dev**. This is the only remaining action, and it is HQ's.
2. The next natural **06:15 UTC** `cron-recommendation-worker` tick selects the 16-game horizon
   slate, passes the gate on those with fresh DK/FD odds, and runs the committee.
3. Kickoffs begin **2026-09-20 17:00 UTC**, so a tick on **09-19 or 09-20** produces predictions
   that are genuinely pre-kickoff — the shape a legitimate calibration observation requires.

**No further code is required.** Recommended first-run watch items: `games_selected` should read
16; per-game `status` should be `computed` or `skipped_ineligible`, never `failed`; and no
`LlmBudgetExceededError` should appear — if one does, the committee shape has grown past 48 and the
ceiling is telling you so.
