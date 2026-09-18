# Runbook Addendum — MSF Pause + Recomputation V1 (2026-09-18)

**Directive:** MANSA HQ — "RUNBOOK ADDENDUM: MSF PAUSE + RECOMPUTATION V1 OWNER DECISIONS".

**Compliance:** dev only. Zero LLM calls. Zero provider calls. The armed TB @ CLE proof was neither
cancelled nor triggered. No scoring/probability/EV semantics touched. No provider activated, no
cadence increased.

---

## PART A — MSF paused. **VERIFIED.**

`MSF_POSTGAME_ENABLED=false` set on `sports-intel-layer` dev, with the normal deployment.

**Seven consecutive natural `cron-msf-postgame` ticks**, 14:00 → 15:31 UTC:

```
result={'considered': 0, 'selected_game_ids': [], 'invoked_game_ids': [],
        'results': [], 'enrolled_game_ids': [], 'paused': True}
```

| Required | Result |
|---|---|
| `paused=True` | ✅ all 7 ticks |
| `considered=0` | ✅ all 7 ticks |
| zero MySportsFeeds HTTP calls | ✅ `invoked_game_ids: []`, and the pause check is the first thing `dispatch_due_msf_postgame_games` does — before any Supabase query, so a paused tick makes literally zero HTTP calls of any kind |
| successful exit | ✅ `cron_dispatch succeeded` |
| no Sentry error | ✅ no `failures`, no nested item errors — correctly silent |

**Preserved exactly as required:** credentials, provider mappings, ingestion state, raw captures,
player stats/history and the backlog-recovery architecture are all untouched. Nothing was deleted.
Games that become eligible while paused stay eligible — both selection queries are pure
re-derivations from persisted rows, never from dispatcher memory.

---

## PART B — Recomputation V1. **IMPLEMENTED. No schema change needed.**

### The identity question, answered from existing state

The directive said to stop and report if a schema addition were genuinely required. **It is not.**
`recommendations` already carries `game_id` **and** `cycle_completed_at`, so "this canonical game has
completed a paid cycle" is expressible today:

```sql
EXISTS (SELECT 1 FROM recommendations WHERE game_id = X AND cycle_completed_at IS NOT NULL)
```

Game-scoped, `run_id`-independent, already persisted. Nothing was added.

### 1. First paid run window — 36 hours

`apps/workers/app/persistence/games.py`, enforced **in the query**:

```
scheduled_start  gte.{now}                 # genuinely upcoming
                 lt.{now + 7 days}         # canonical horizon, PRESERVED
                 lte.{now + 36 hours}      # NEW: first-paid-run gate
```

All three bounds are sent separately rather than pre-collapsed to whichever is smaller, so the
7-day horizon is **preserved, not replaced** — they are different kinds of rule and the code says so.

**The boundary is inclusive (`lte`): exactly 36h out IS eligible.** That is the whole of the
determinism HQ asked for at the boundary, and it is asserted against the operator actually sent.

### 2–3. One successful paid cycle per game; `run_id` is not the reason

Two enforcement points, deliberately:

- **`apps/workers`** — `read_game_ids_with_completed_paid_cycle` subtracts finished games from the
  slate **before** the ceiling and the throttle, because an already-completed game is not part of
  this cycle's work at all; counting it toward either bound would misreport the slate.
- **`ai-orchestrator`** — `read_completed_paid_cycle_for_game` refuses at the service that actually
  spends. Defence in depth: a caller that skipped the filter (a manual call, a future scheduler, a
  bug) still cannot buy a second committee run.

**Why the pre-existing check was not enough, measured rather than argued:** it is keyed on
`correlation_id = f"{master_refresh_run_id}:{game_id}"`, and dev holds three `master_refresh_runs`
rows dated 2026-09-16, -17 and -18 — one per day. Each new day minted a fresh correlation, found no
prior row, and would have re-run the full committee on identical evidence. That check is a
crash-retry protection within one run; it provably never fires across days.

The guard also re-checks `cycle_completed_at` on the returned row rather than trusting the
server-side filter alone — a guard that spends money on the strength of a filter it did not verify
fails silently the moment the query changes shape.

### 4–5. Zero-cost and failed attempts stay retryable

Outcome-blind by construction. `mark_recommendation_cycle_completed` is the unconditional last step
once every candidate has been attempted, so a real recommendation, multiple singles, bankroll
preservation and **a legitimate No Bet all count as completed** — exactly HQ's rule.

What does *not* count, equally by construction: the deterministic pre-LLM gate creates **no row at
all** (stale odds, no odds, no reference book, outside 36h), and a failed paid attempt leaves
`cycle_completed_at` NULL. Both stay retryable, and neither is marked as having consumed the game's
one run. The existing 3-strike circuit breaker is preserved unchanged — bounded, never unlimited,
and a halted run reports `failed` rather than being dressed up as complete.

### 6. No automatic re-evaluation

Nothing was invented: no line-movement threshold, no injury trigger, no context-change trigger, no
lifecycle trigger, no timing-tier recomputation. V1 is deliberately bounded spend over premature
re-evaluation intelligence.

### Tests — all 11 required properties

`apps/workers/tests/test_recomputation_v1.py` (12 tests):

| # | Property | Test |
|---|---|---|
| 1 | 37h before kickoff → 0 LLM | `test_37h_before_kickoff_is_outside_the_paid_window` |
| 2 | exactly 36h deterministic | `test_exactly_36h_is_deterministic_and_inclusive` (asserts `lte` sent, `lt` not) |
| 3 | inside 36h + eligible → allowed | `test_inside_36h_and_eligible_allows_the_first_paid_run` |
| 4 | successful recommendation → cannot rerun | `test_completed_recommendation_cannot_run_again_next_day` |
| 5 | successful No Bet → cannot rerun | `test_completed_no_bet_also_cannot_run_again` |
| 6 | new `master_refresh_run` does not reopen | same test, run id `run-2-a-brand-new-day` |
| 7 | stale odds → zero-cost retry possible | `test_incomplete_cycle_does_not_consume_the_one_paid_run` |
| 8 | no odds → zero-cost retry possible | same |
| 9 | failed attempt bounded | `test_failed_paid_attempt_keeps_bounded_retry_not_unlimited` (3 calls, `failed`) |
| 10 | final game never runs | `test_final_game_never_runs` |
| 11 | no probability/EV/scoring change | `test_no_change_to_probability_ev_or_recommendation_semantics` (structural) |

Plus: horizon preserved, identity is game-scoped never run-scoped, empty slate makes no query.

**Regression: workers 101/101, ai-orchestrator 1000/1000.** A new `apps/workers/tests/conftest.py`
registers one inert default for the added read — mirroring the existing
`apps/sports-intel-layer/tests/conftest.py` idiom rather than inventing a second pattern — so the
fourteen pre-existing tests keep testing what they were written to test.

**The TB @ CLE proof still qualifies:** at the 06:15 tick it is **34h45m** from kickoff, inside 36h.

---

## PART C — STEP 5 under MSF-paused reality. **STOP.**

Re-audited with zero provider calls. The finalization chain has two halves and they now differ:

| Requirement | Source | State with MSF paused |
|---|---|---|
| **terminal canonical status** | daily SportsDataIO Schedule refresh writes `games.status` from `entry.status`, and holds `final` terminal via a server-side `finalized_at=is.null` filter | ✅ **ACTIVE, already authorized, no new cost** — 1 Schedule call/day, already running at 09:00 |
| **final score** | — | ❌ **no active path** |
| **grading evidence (`finalized_at`)** | — | ❌ **no active path** |

**Why, precisely.** `app/persistence/schedule.py` states it in its own words:

> "`final_score` and `finalized_at` are **never in the writable field set at all**, so a Schedule
> refresh could not clear them even if it tried… `finalized_at` [is] stamped by
> `app.workers.canonical_finalization` off real postgame evidence."

And that evidence is MSF `confirmed_complete` captures, which will not exist for Week 2 while paused.

Two further findings:

- **`canonical-finalization` has a cron *target* but no cron *service*.** The eight live crons are
  schedule-refresh, msf-postgame, weather, news, odds, adaptive-weighting, postgame-grading and
  recommendation-worker. Week 1 was finalized by a deliberate backfill, not by a recurring job — so
  even with MSF running, this step was never automated.
- **The SportsDataIO postgame path has no cron target at all.** `app.workers.postgame_worker` exists
  and derives `final_score` from TeamGameStats, but `_TARGET_PATHS` has no entry for it.

**Can already-persisted data solve it?** No. With MSF paused, no postgame capture for Week 2 will
ever be written, so there is nothing persisted to finalize *from*. This is not a wiring gap that
existing rows can close.

**Consequence for grading:** `read_grading_candidate_game_ids` selects `status='final'` **AND**
`finalized_at >= window_start`, and reconciliation-eligibility is `finalized_at + 72h`. Without
`finalized_at` the game never becomes a grading candidate, so **grading and calibration cannot
proceed for Week 2 as things stand** — regardless of whether the recommendation itself succeeds.

### Options — HQ's call, none taken

1. **Re-enable MSF for finalization only.** Contradicts the pause decision made in Part A today.
   Would also still need `canonical-finalization` wired to a cron or run manually.
2. **Wire the SportsDataIO postgame path.** The worker exists; it needs a `_TARGET_PATHS` entry, a
   cron service, and real SportsDataIO TeamGameStats calls. **I have not established that key's
   remaining quota or billing state**, and will not assume it.
3. **One-off manual finalization after the game**, using whichever provider HQ authorizes. Smallest
   possible spend, but not autonomous.

**I did not reactivate MSF, did not wire a new path, and did not call any provider.**

---

## Governance

Nothing forced. No provider data, sportsbook price or model output invented. No deterministic
eligibility bypassed. No authorized ceiling exceeded. Nothing truncated and called complete. No
recomputation philosophy invented beyond the V1 rules HQ supplied verbatim.
