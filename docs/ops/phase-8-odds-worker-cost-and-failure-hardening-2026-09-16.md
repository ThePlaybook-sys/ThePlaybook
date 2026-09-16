# Odds Worker Cost + Failure Hardening (2026-09-16)

**Directive:** MANSA HQ — "ODDS WORKER COST + FAILURE HARDENING." Separate attempt from
success; design a credit-aware polling contract; add a hard daily budget; prove it all by
test/simulation. ZERO provider calls.

**Compliance:** zero provider calls of any kind. No cron cadence changed. No recommendations
run. `MASTER_REFRESH_ENABLED` untouched (`false`). The only live write was an **additive**
migration creating two new empty tables and one function.

---

## 1. Attempt-state design

### The defect, stated precisely

`last_polled_at` came from `odds_snapshots.captured_at`. `odds_snapshots` is written **only**
when an event resolves to a canonical game. So a poll that succeeded at the provider but could
not be *used* left no trace at all:

```
provider call succeeds
  → event cannot be linked (no team mapping / kickoff out of tolerance / ambiguous)
  → no snapshot row written
  → game reads as NEVER POLLED
  → due again on the very next tick
  → forever
```

**Attempt and success were the same signal, and only success was recorded.**

### The fix: `odds_worker_poll_state`

A new table recording the other half — *a real attempt was made for this game, whatever came
of it*.

| Column | Purpose |
|---|---|
| `game_id`, `provider_name` | Composite PK — one row per game per provider |
| `last_attempt_at` | Every real attempt stamps this, whatever the outcome. **This is the half that did not exist.** |
| `last_attempt_outcome` | `success` / `unresolved` / `provider_failure`, CHECK-constrained |
| `last_success_at` | Last attempt that actually persisted. **Advanced only on success.** |
| `consecutive_failure_count` | Drives backoff. Reset to 0 by any success. |
| `last_failure_reason` | Preserved so a failure is never silently dropped. Cleared on success. |
| `updated_at` | |

**This is not a new invention — it is the fix the News Worker already shipped.**
`news_worker_poll_state`'s own migration comment reads: *"news_article_history cannot serve
this purpose despite carrying an ingested_at column: it is insert-once-per-(provider_name,
article_url), so a team whose fetch succeeds with zero NEW articles writes no row at all —
indistinguishable from 'never polled.'"* Identical trap, identical fix. Odds is the same
problem with a bigger bill.

**Current-state, not history.** One row per game, always overwritten — scheduling metadata, not
a fact worth preserving. The deliberate opposite of `odds_snapshots`, which is append-only
because an observed market price *is* a fact. Same judgment `news_worker_poll_state` makes.

**The outcome vocabulary is CHECK-constrained**, not free text. A typo would otherwise write a
status no backoff branch matches — which fails **open**, straight back into every-tick spending.

### Due-selection now consults both halves

```
last SUCCESS → "is fresh odds data due?"                (cadence, app.workers.windows)
last ATTEMPT → "have we already tried recently and failed?"  (backoff, app.workers.odds_backoff)

due = cadence_says_yes AND backoff_has_elapsed
```

Two invariants, both tested:

- **Cadence is fed only by a real capture**, never by a bare attempt — so an unresolved poll can
  never masquerade as fresh odds data.
- **Backoff can only ever suppress a poll.** It can never cause one. If the due set empties as a
  result, the worker makes no provider call at all — which is the entire economic point.

**Migration safety:** a game with snapshot history but no attempt row (i.e. every game that
captured before this shipped) falls back to the snapshot-derived timestamp. Without that
fallback all 16 Week 2 games would read as never-successful on the first run afterwards and come
due at once, spending a call to rediscover what `odds_snapshots` already knows. Test `B3`.

---

## 2. Retry / backoff rules

Exponential, base one cron tick, doubling, capped at 6 hours:

| Consecutive failures | Wait | |
|---|---|---|
| 1 | 15 min | exactly one cron tick |
| 2 | 30 min | |
| 3 | 1 h | |
| 4 | 2 h | |
| 5 | 4 h | |
| 6+ | 6 h | cap |

Three deliberate properties, each with its own test:

1. **The base is one cron tick, not less.** A backoff shorter than the cron period cannot change
   behaviour — the worker simply would not run during it. 15 min is the smallest value that
   actually suppresses a tick, so a transient hiccup costs exactly one skipped tick.
2. **The cap is 6 hours, not infinity.** A permanently-broken game still retries **4×/day**, so a
   repair lands within hours with nobody re-running anything. This is the directive's "no
   permanent quarantine unless explicitly justified" — and nothing here justifies one: the real
   2026-09-16 incident was repaired by inserting 15 rows, after which the games needed to become
   due on their own. Test `A5` reproduces exactly that.
3. **Success resets unconditionally.** One genuine capture proves the game resolves, so it
   returns to ordinary cadence immediately rather than serving out a residual penalty.

**Flagged as ASSUMED.** No Blueprint volume specifies a backoff schedule for a provider-side
resolution failure — the concept did not exist before this pass. These are explicit, disclosed
policy defaults in the same tradition as `MANUAL_SEED_MAX_ATTEMPTS`,
`ADAPTIVE_WEIGHT_LEARNING_RATE` and `THRESHOLD_VERSION`. Never presented as confirmed numbers.

**Relationship to `MANUAL_SEED_MAX_ATTEMPTS`.** That cap (2026-09-07, after an identical
incident) excludes a manually-seeded game after 3 unproductive attempts, and is explicitly
documented as *"never applied to a normal Schedule/Master-Refresh-sourced game… those correctly
keep retrying a real, temporarily-unresolved team mapping forever."* That judgment assumed such
gaps are transient. The 2026-09-16 gap was permanent and the "forever" ran literally for 12
ticks. This module is the general answer that cap was a narrow special case of. **The cap is
left in place and untouched** — it is a hard exclusion for a bad manual seed, this is a slowdown
for any game, and the two compose without conflict.

---

## 3. Schema / code changes

**New migration** `20260916180000_odds_worker_poll_state_and_daily_budget.sql` — applied to dev,
verified: both tables present, RPC present, **0 rows in each** (nothing backfilled, nothing
disturbed).

| File | Change |
|---|---|
| `supabase/migrations/20260916180000_…sql` | **new** — `odds_worker_poll_state`, `odds_api_daily_call_budget`, `increment_odds_api_daily_calls` |
| `app/workers/odds_backoff.py` | **new** — the backoff policy, pure functions, no I/O |
| `app/persistence/odds_worker_poll_state.py` | **new** — read/record attempt state |
| `app/persistence/odds_api_daily_call_budget.py` | **new** — day-keyed call ceiling |
| `app/workers/odds_worker.py` | due-selection consults both halves; daily-budget guard; attempt recording on every path |
| `app/workers/windows.py` | **+`effective_poll_interval_seconds`** — reporting only, zero behaviour change |
| `app/main.py` | feeds real attempt state; degrades to cadence-only on read failure rather than failing the run |
| `tests/conftest.py` | **new** — inert defaults for the two new tables |
| `tests/test_odds_worker_cost_and_failure_hardening.py` | **new** — 27 tests |

**Deliberate design choices worth naming:**

- **`odds_backoff.py` is separate from `windows.py`.** `windows.py` is the *shared*
  kickoff-proximity policy — Player Props Worker uses the same instance and Injury Worker extends
  it. Failure backoff is not a cadence concept and is not shared with those workers, so folding
  it in would widen a module three callers depend on in order to serve one.
- **`app/main.py` never names the service-role credential.**
  `tests/test_environment_safety.py` forbids that module from referencing any provider or
  service-role credential by name, so attempt state is read through a self-contained
  `read_poll_state_from_env()` — the same pattern `odds_snapshots.read_last_polled_at` already
  uses. The guarantee is kept intact rather than worked around.
- **A poll-state read failure degrades, it does not fail the run.** Losing backoff for one cycle
  costs at most one extra provider call; failing the run costs every game's odds. The degradation
  is reported (`status` drops to `partial` with a named failure), never silent.
- **Atomic increment for the budget.** `increment_odds_api_daily_calls` mirrors
  `increment_news_provider_quota` — a single UPSERT with an expression-based increment, atomic
  under Postgres's row-lock semantics. Deliberately **stronger** than
  `odds_api_credit_ledger`'s accepted single-writer read-then-write race: this counter is a hard
  spending ceiling and should not inherit a known race, however narrow.

---

## 4. Game-day cost analysis

### 1. Practical maximum provider calls/day under the current `*/15` cron

**96.** The worker cannot run more often than the cron fires: 4 ticks/hour × 24 h. Each tick
makes at most one call (see #4 below).

### 2. Practical maximum credits/day

**288.** 96 × `CREDITS_PER_CALL` (3). This is not theoretical — it is exactly the rate the
2026-09-16 leak was running at.

### 3. Expected call pattern on a 13-game Sunday

Modelled against the **real** Week 2 Sunday (2026-09-20 UTC): 8 kickoffs at 17:00, 2 at 20:05,
3 at 20:25, plus SNF at 00:20 Monday.

| UTC window | Tier | Calls |
|---|---|---|
| 00:00–15:00 | all FAR (24 h interval) | ~2 |
| 15:00–16:00 | 8 games RAMP_2H (1 h interval) | 1 |
| 16:00–17:00 | 8 games RAMP_60M → **every tick** | 4 |
| 17:00–18:05 | no ramp games | ~1 |
| 18:05–19:25 | 20:05 and 20:25 games enter RAMP_2H | ~3 |
| 19:25–20:25 | both groups RAMP_60M → **every tick** | ~4 |
| 20:25–22:20 | no ramp games | ~1 |
| 22:20–00:00 | SNF RAMP_2H then RAMP_60M | ~3 |

**≈ 19 calls ≈ 57 credits**, with a realistic range of **18–24 calls / 54–72 credits**.

The shape is worth noting: **roughly half the day's spend happens in the final hour before each
kickoff cluster**, because RAMP_60M and below are due on every tick. That is exactly where the
spend belongs, and it is why the reserve mechanism protects that window specifically.

### 4. Does a single bulk call cover all currently-due games?

**Yes — and this is the load-bearing fact of the whole cost model.** One discovery-mode
`fetch_odds([])` against the bulk endpoint returns the full slate regardless of filter. **Ten due
games and one due game cost the same 3 credits.** Proven live on 2026-09-16 (one call served 10
due games, persisting 266 rows) and asserted in test `C1`.

Two consequences shape everything else:
- The budget layer counts **calls**, not games.
- There is nothing to rank *within* a call — so "prioritize games closer to kickoff" can only
  mean "decide whether **this cycle** is worth a call."

### 5. Which cadence tiers are actually valuable given the credit cost?

Measured honestly, **three of the five tiers are already indistinguishable**:

| Tier | Specified | Achievable under `*/15` | |
|---|---|---|---|
| FAR | 86400 s | 86400 s | honoured |
| RAMP_2H | 3600 s | 3600 s | honoured |
| RAMP_60M | 900 s | 900 s | honoured, exactly at the floor |
| RAMP_15M | 300 s | **900 s** | **FLOORED** (3× coarser) |
| RAMP_5M | 120 s | **900 s** | **FLOORED** (7.5× coarser) |

So RAMP_60M, RAMP_15M and RAMP_5M all poll at most once per tick and are operationally the same
tier today.

**Value judgment:** FAR and RAMP_2H carry the useful pre-kickoff market history cheaply. RAMP_60M
is where closing-line movement actually happens and is worth its every-tick cost. RAMP_15M and
RAMP_5M currently buy **nothing beyond RAMP_60M** — they cost the same and deliver the same
resolution.

### 6. How to prioritize as kickoff approaches if budget is constrained

`ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`. Once `calls_used >= max_calls − reserve`, the tail of the
day's budget is released **only** for a cycle with at least one due game out of the FAR tier —
i.e. inside 2 h of kickoff, where movement matters most and a missed poll can never be made up
later. FAR-only cycles are turned away while ramp cycles still get served.

This is shaped by the cost model rather than bolted on: since one call serves everything, the
only meaningful priority decision is *whether this cycle deserves a call*. Tests `D4`/`D5`.

### 7. How the existing credit guard interacts with polling priority

They are complementary, and **both** are checked, in this order:

```
due-selection  →  monthly credit guard  →  daily call budget  →  provider call
```

- **Monthly** (`odds_api_credit_ledger`, existing): the outer bound. Protects the *period*. Trips
  when `budget − used <= floor`. Checked first, so a blown month is the reported condition.
- **Daily** (`odds_api_daily_call_budget`, new): the inner bound. Protects any *single day* from
  consuming the period's allocation. The monthly guard cannot do this — 288 credits/day is
  reachable without it objecting once, right up until it slams shut, possibly mid-slate on a
  Sunday.
- The **reserve** sits inside the daily bound and never overrides the ceiling. Test `D6`.

Both fail **open** when unconfigured (a disclosed no-op, never an invented number) and **closed**
once configured. A budget stop returns `status="skipped_daily_budget"` cleanly — the cron exits 0
rather than CRASHING, the same discipline `master_refresh`'s `paused` status follows after a
daily CRASHED deployment once looked like real breakage.

### 8. Should the 120 s / 300 s cadence values change, be deprecated, or be reinterpreted?

**Reinterpreted — and the gap made visible in code. Not changed, not deprecated.**

The boundaries (2 h / 60 m / 15 m / 5 m) are **CONFIRMED from Volume 2 §8**. The intervals are a
long-standing documented assumption (the boundary-as-interval convention). Silently rewriting
either to match a deployment detail would be exactly the undocumented drift this project's
versioning discipline exists to prevent — and it would also bake today's cron period into a
module that outlives it.

Instead, `effective_poll_interval_seconds(window, cron_period_seconds=…)` reports what a tier can
*actually* achieve. It is **pure reporting with zero behaviour change** (`should_poll` is
untouched — a 120 s interval evaluated every 900 s already behaves identically to a 900 s one).
The floor stops being an invisible emergent property and becomes something a caller can read and
report. It also moves correctly with the cron period, so it stays true if the cadence ever
changes — asserted in the tests.

**Explicitly NOT done:** no higher-frequency cron was invented to chase the 120 s tier, per the
directive.

---

## 5. Recommended cadence interpretation (V1)

> The goal is not maximum polling frequency. It is **useful market history + reliable
> near-kickoff odds + bounded cost.**

1. **Keep the `*/15` cron.** It already honours FAR, RAMP_2H and RAMP_60M exactly. The only tiers
   it cannot honour are the two that buy nothing extra at this granularity.
2. **Read RAMP_15M and RAMP_5M as intent, not schedule.** They express "poll as fast as you can
   this close to kickoff," and under `*/15` that is once per tick — which is what happens.
3. **Treat RAMP_60M as the real closing-line tier.** It is the finest granularity actually
   achieved, it is where movement concentrates, and it accounts for roughly half of game-day
   spend.
4. **Revisit only with evidence.** If closing-line capture ever proves too coarse at 15 minutes,
   that is a cron-period decision with a measurable cost (a `*/5` cron triples the daily ceiling
   to 288 calls / 864 credits), not a code change. Nothing observed so far argues for it.

---

## 6. Daily-budget mechanism

- **`ODDS_API_MAX_CALLS_PER_DAY`** — hard ceiling on provider calls per UTC day. Unset ⇒ disclosed
  no-op (not even queried; test `D3`).
- **`ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`** — calls held back for near-kickoff cycles. Unset ⇒ 0,
  i.e. today's behaviour.
- **Day-keyed table, so there is no rollover logic at all.** Each UTC day is its own row; a new
  day has no row and reads as zero. Same rationale `news_provider_daily_quota` records for
  itself, reused deliberately rather than retrofitting rollover onto a ledger already trusted for
  real financial safety.
- **Counts calls, charges once per real round-trip.** A cache hit never consumes budget
  (test `D7`), matching the credit ledger's existing rule.
- **A skipped call is not a spent call** — the increment never fires on a guard stop (test `D1`).
- **No attempt is recorded when the budget blocks the cycle.** Nothing was attempted, and
  stamping one would push healthy games into a backoff they did not earn (asserted in `D1`).

---

## 7. Tests / regressions

**`sports-intel-layer`: 1021 passed, 5 failed** (up from 994/5 — **+27 tests, zero new
failures**).
**`ai-orchestrator`: 987 passed. `apps/workers`: 45 passed.**

The 5 failures are the same pre-existing wall-clock rot in `test_odds_cadence_persistence.py`
(hardcoded 2026-09-14 kickoffs now in the past → every game classifies STOPPED). **Verified by
stashing every change and re-running on a clean tree: byte-identical set of 5 test names.** Not
fixed — out of scope for this directive.

The 27 new tests map directly onto the directive's proof list:

| Proof | Tests |
|---|---|
| **A** — unresolved game: attempt recorded, not due next tick, backoff retries, recovers after repair | `A1`–`A6` |
| **B** — successful FAR game keeps its 24 h throttle | `B1`–`B3` |
| **C** — one bulk request services a mixed slate | `C1` |
| **D** — exhausted budget: no call, explicit paused result, no CRASH | `D1`–`D7` |
| **E** — success resets failure/backoff state | `E1`–`E2` |
| Backoff policy (pure units) | 6 tests |
| Cadence floor reporting | 2 tests |

Assertions worth calling out:

- **`A2` is the regression test for the leak itself.** Same fixtures, same unresolvable slate: the
  game is now `games_skipped_backoff`, `games_due == 0`, and **`odds_route.call_count == 0`**.
  Before this pass that tick cost 3 credits.
- **`A1` asserts `"last_success_at" not in row`** — the single most important line in the file.
  An unresolved attempt must never be able to masquerade as fresh odds data.
- **`A6`** covers a provider outage: without recording those attempts, an outage would leave every
  game reading as never-polled and hammering the provider for its whole duration.
- **`E2`** covers a persistence failure: lines fetched, nothing landed. Recording success there
  would both lie *and* re-open the leak — a repeating persistence fault would buy a bulk call
  every tick and throw the results away.
- **`B3`** is the migration-safety test described in §1.
- The new `conftest.py` defaults are **deliberately inert** (empty poll state, low call count), so
  the 42 pre-existing odds tests keep testing what they were written to test rather than silently
  exercising new machinery.

---

## 8. Owner-config values still needed

**Two values require your decision. I have not guessed them and nothing is set.**

| Variable | Status | What it needs |
|---|---|---|
| `ODDS_API_MAX_CALLS_PER_DAY` | **NOT SET** — currently a disclosed no-op | Your choice |
| `ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP` | **NOT SET** — defaults to 0 (no prioritization) | Your choice |

**What I can tell you from measurement**, to make the choice concrete:

- A real 13-game Sunday costs **≈19 calls (57 credits)**, range 18–24.
- The unbounded ceiling is **96 calls (288 credits)/day**.
- A quiet weekday with a healthy slate costs roughly **2 calls (6 credits)/day**.

**A defensible starting point would be `ODDS_API_MAX_CALLS_PER_DAY=40` with
`ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP=10`** — about 2× headroom over a real Sunday, capping the
worst case at 120 credits/day instead of 288, with a quarter of the budget held for the hour
before kickoff. **This is a recommendation derived from measured behaviour, not a value I can
confirm**, because the actual monthly plan is the missing input:

> `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` and `THE_ODDS_API_MIN_REMAINING_CREDITS` **are set** on
> `sports-intel-layer` in dev, but Railway returns variable **names only** to this session
> (`valuesRedacted`). I cannot read them and will not guess. **If you supply the monthly budget,
> the correct daily ceiling is arithmetic rather than judgment**: a season month with ~4 Sundays
> plus quiet weekdays runs roughly 4×57 + 26×6 ≈ **384 credits/month** at current behaviour, so
> the right ceiling is whatever leaves comfortable margin under your plan.

Until they are set, the daily layer is **inert but installed** — the tables exist, the code path
is live and tested, and enabling it is a single Railway variable with no deploy.

---

## 9. Is the Odds Worker now economically safe for unattended operation?

**Substantially yes, with one honest caveat.**

**What is now structurally impossible:**

| Failure mode | Before | After |
|---|---|---|
| Unresolvable game burns a call every tick forever | **288 credits/day** | 1st failure costs 1 tick, then 15m→6h backoff; **4 retries/day at worst** |
| Provider outage leaves every game "never polled" | hammered every tick | recorded as an attempt, backs off |
| Persistence fault silently re-buys the same data | every tick | recorded as non-success, backs off |
| A single day consumes the monthly allocation | possible, unnoticed until the monthly guard slams shut | capped by `ODDS_API_MAX_CALLS_PER_DAY` **once set** |
| Budget stop looks like breakage | — | explicit `skipped_daily_budget`, exit 0, no CRASH |

**The caveat, stated plainly:** the hard ceiling is **installed but not armed**, because arming it
needs a number only you can supply (§8). Until then the worker is protected by backoff and the
monthly guard, but not by a daily cap. Backoff alone already removes the specific failure that
caused the real incident, and the measured steady state is ~6 credits/day quiet / ~57 on a
Sunday — so unattended operation is **safe today and safer the moment the ceiling is set.**

One further limit, for honesty: this pass hardens the Odds Worker only. Player Props Worker
shares `windows.py` but has **no** equivalent attempt state, so the same class of leak remains
possible there. Not in scope for this directive, and flagged rather than fixed.

---

## 10. Next autonomy step

**Unchanged from the last pass, and now better supported: enable `MASTER_REFRESH_ENABLED=true`**
so `cron-schedule-refresh` (`0 9 * * *`) becomes real autonomy instead of an inert daily no-op.

It costs 1 SportsDataIO call/day (measured), auto-recovers GameKey `202610902` (season 271 → 272)
since the venue fix shipped in `84c6892`, and canonical schedule maintenance is now the **last**
layer still requiring a human to spend a call.

It is a better step *after* this pass than before it: the schedule refresh continuously creates
new canonical games, and every newly created game is exactly the input that previously risked an
unbounded spend if its provider identity was not yet mapped. That risk is now bounded by design.

**Ordered recommendation:**
1. Set the two budget variables (§8) — one Railway change, no deploy, arms the ceiling.
2. Enable `MASTER_REFRESH_ENABLED=true`.
3. Observe the kickoff ramp naturally at **DET @ BUF, Thu 2026-09-18 22:15 UTC** — the first real
   RAMP_2H → RAMP_60M exercise. Observe; do not simulate by moving clocks.

---

## What was NOT done

- **Zero provider calls.** No Odds API, SportsDataIO, MSF or LLM calls.
- **No cron configuration changed.** `cron-odds-worker` still `*/15`; `cron-schedule-refresh`
  still `0 9 * * *`.
- **No recommendations run.** `MASTER_REFRESH_ENABLED` still `false`.
- **No budget values guessed or set.**
- **No unrelated repairs.** The 5 pre-existing wall-clock test failures, the
  `InMemoryCacheBackend`-per-invocation observation, `cron-master-refresh`'s stale branch, and
  Player Props Worker's equivalent gap are all reported, not fixed.
- **Cadence tier values unchanged.** The floor is reported, not rewritten.
- **Nothing backfilled.** Both new tables are empty; existing games rely on the documented
  snapshot-history fallback.
