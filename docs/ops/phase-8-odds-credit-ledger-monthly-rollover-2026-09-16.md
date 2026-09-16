# Odds Credit Ledger — UTC Monthly Rollover (2026-09-16)

**Directive:** MANSA HQ — "ODDS CREDIT LEDGER MONTHLY ROLLOVER — IMPLEMENT." Authoritative rule
supplied: The Odds API's official FAQ, *"Usage credits are automatically reset on the first of
every month."*

**Compliance:** zero provider calls, zero LLM calls. Odds cadence untouched, no cron changed,
`MASTER_REFRESH_ENABLED` still `false`.

---

## Schema / data-model change

Migration `20260916190000_odds_api_credit_ledger_monthly_periods.sql`, applied to dev and
verified.

| Change | Detail |
|---|---|
| `period_key text not null` | UTC calendar month, `YYYY-MM` |
| **Uniqueness moved** | `unique(provider_name)` → **`unique(provider_name, period_key)`** |
| `provider_reported_used` / `_remaining` / `_last` / `_at` | the vendor's own quota report |
| `last_discrepancy text` | audit trail when the vendor's number and ours disagree |
| `increment_odds_api_credits(...)` | atomic upsert, replaces read-then-write |
| `reconcile_odds_api_provider_usage(...)` | records the vendor snapshot without touching our count |

**The old constraint was the actual blocker.** `unique(provider_name)` permitted exactly one row
per provider *for all time* — a second period was not representable, so no amount of application
logic could have rolled over correctly.

Code: `app/persistence/odds_api_credit_ledger.py` (rewritten), `app/workers/odds_worker.py`
(period-scoped guard + reconciliation), `app/adapters/models.py` (new `ProviderQuota`,
`AdapterResponse.provider_quota`), `app/adapters/providers/the_odds_api.py` (header parsing).

---

## UTC month-key behaviour

`utc_period_key(now)` → `now.astimezone(utc).strftime("%Y-%m")`. Computed **once per cycle** from
the clock and used for every ledger read and write in that cycle.

**Always UTC, never local.** A local boundary would put the same instant in different periods in
different deployments — exactly the class of bug a spending guard cannot afford. Every other
time-keyed table here (daily call budget, news quota) makes the same choice.

**The design point: rollover is a LOOKUP, not a MUTATION.** A new month simply has no row, so it
reads zero. There is no reset step to run, nothing that can half-apply at the boundary, and no
date arithmetic beyond formatting a month. That is what makes requirements 1, 4, 6 and 7 fall out
structurally rather than needing defensive code:

- **new period starts at 0** — no row exists;
- **no provider call to discover rollover** — the key comes from the clock;
- **a stale prior-period row can never block a new month** — it is never read;
- **a restart cannot reset usage** — state lives in the database keyed by period, never in memory.

Reused deliberately, not invented: `odds_api_daily_call_budget` and `news_provider_daily_quota`
are both day-keyed, and the former's own migration records the reason — *"Day-keyed, so there is
no rollover logic at all."*

---

## Provider-header reconciliation

The three headers are now **CONFIRMED** (previously ASSUMED, logged as text and discarded). They
are parsed into a typed `ProviderQuota` and carried up on `AdapterResponse.provider_quota` from
the bulk odds call only — the only call that spends credits.

**The vendor is authoritative for the guard.** `effective_used_credits()` prefers
`provider_reported_used` when present, falling back to our deterministic count.

**Why that preference matters — it is correct on *both* sides of the boundary**, which is the
whole reason the directive asked for it:

| Situation | Local | Vendor | Guard uses | Outcome |
|---|---|---|---|---|
| 00:05 on the 1st, vendor hasn't reset yet | 0 (new row) | 490 | **490** | correctly **blocks** — trusting only ourselves would overspend a real allowance |
| Vendor resets slightly early | 276 (carried) | 5 | **5** | correctly **allows** — our own count would have blocked legitimate spending |

**Our count is never overwritten.** `credits_used_this_period` stays ours; the vendor's figure
lives beside it. That is what makes a disagreement *visible* rather than silently resolved — and
a discrepancy is triple-reported: written to `last_discrepancy` as a readable signed-delta string,
logged at WARNING, **and appended to the worker's `failures` list** so the cron's Sentry capture
(shipped earlier today) sees it rather than it living only in a log line.

**Parsing is deliberately strict.** Missing, blank, non-numeric and negative all yield `None` —
"no signal" — and fall back to our own count. For a spending guard the dangerous invention is a
**low** number: a fabricated zero reads as a completely unused allowance. Reconciliation is a
no-op when the vendor reported nothing, and is gated on `from_cache` exactly as both ledgers are —
a cache hit made no round-trip, so any quota on it is a stale echo.

---

## Historical preservation

**Nothing ever writes to a closed period again**, because the period is part of the row's
identity. That is stronger than preserving history by policy — it is preserved by construction.

This is also why the period-keyed design was chosen over mutating `period_start` in place:
mutation would have destroyed the audit trail the directive requires be kept.

---

## Concurrency / idempotency

Both writes are **single atomic upserts** keyed on `(provider_name, period_key)` with
expression-based increments, executed inside Postgres:

```sql
insert into odds_api_credit_ledger (...) values (...)
on conflict (provider_name, period_key)
do update set credits_used_this_period = odds_api_credit_ledger.credits_used_this_period + p_credits
returning credits_used_this_period;
```

- **Idempotent** in the sense that matters: "rolling over" repeatedly is a no-op, because there is
  no rollover step — only an upsert that either creates the period or adds to it.
- **Concurrency-safe** under Postgres's own row-lock semantics: two workers crossing midnight
  together converge on one row. Neither a lost update nor a conflicting second "active period" is
  representable, because the unique index forbids it.

This deliberately **replaces** the previous read-then-write upsert, whose race was an accepted,
disclosed risk on the old single-row design. With per-month rows, the boundary is precisely when
that race would have bitten — and a hard spending guard should not inherit a known race.

---

## Migration / backfill of the 276-credit row

```sql
update odds_api_credit_ledger
set period_key = to_char(period_start at time zone 'UTC', 'YYYY-MM')
where period_key is null;
```

**Derived from each row's own data, not hardcoded**, so it is correct in every environment
regardless of when that environment's row was created.

Verified live after applying:

| Field | Value |
|---|---|
| `period_key` | **`2026-09`** (from `period_start` 2026-09-07, which falls in September) |
| `credits_used_this_period` | **276 — preserved, not reset** |
| `period_start` | `2026-09-07 02:30:23.554545+00` (untouched) |
| new unique constraint present / old one gone | **yes / yes** |
| both RPCs present | **yes** |

September's 276 is kept as genuine history, matching the discipline already applied to this ledger
once before (*"not reset, an honest record of real (if wasted) usage"*).

---

## Tests / regressions

**`sports-intel-layer`: 1042 passed / 5 failed** (was 1021/5 — **+21, zero new failures**).
**`ai-orchestrator`: 987. `apps/workers`: 67.** The 5 are the known pre-existing wall-clock rot in
`test_odds_cadence_persistence.py`, verified identical on a clean tree in an earlier pass.

New file `tests/test_odds_credit_ledger_monthly_rollover.py` (21 tests). All twelve required
proofs:

| # | Proof | Test |
|---|---|---|
| 1 | same-month usage persists | `test_1_same_month_usage_persists` |
| 2 | Sep 30 → Oct 1 selects a new period | `test_2_sep_30_to_oct_1_crosses_into_a_new_period` |
| 3 | Dec 31 → Jan 1 works | `test_3_dec_31_to_jan_1_rolls_the_year_too` |
| 4 | old periods remain queryable | `test_4_old_periods_remain_queryable` |
| 5 | repeated rollover is idempotent | `test_5_and_6_…`, `test_5_repeated_increments_…` |
| 6 | concurrent rollover is safe | `test_5_and_6_increment_is_a_single_atomic_upsert` |
| 7 | new period starts locally at 0 | `test_7_and_9_…` |
| 8 | provider `x-requests-used` reconciles | `test_8_provider_usage_is_authoritative_…`, `test_8_…_both_sides_of_the_reset_boundary` |
| 9 | stale prior period cannot block | `test_7_and_9_a_new_month_reads_zero_and_cannot_be_blocked_by_the_old_one` |
| 10 | daily budget independent | `test_10_the_daily_budget_is_keyed_independently_…` |
| 11 | restart does not reset usage | `test_11_usage_lives_in_the_database_not_in_process_memory` |
| 12 | no provider call for rollover | `test_12_rollover_itself_needs_no_provider_call` |

Worth calling out:

- **Proof 9 is the heart of it**: September sits at **450** — past the trip point — and October
  still reads zero and passes the guard arithmetic (`500 − 0 > 50`). That is the permanent block,
  proven impossible.
- **Proof 12** runs inside `respx.mock(assert_all_mocked=True)`, so *any* HTTP request at all
  would raise. Rollover makes none.
- **Proof 3** catches the classic naive-month bug: `2026-12` → `2027-01` must change the year too.
- An extra boundary test proves the key is **UTC, not local** — `2026-09-30 20:30` in UTC−05:00
  normalizes to October.
- Strict-parsing tests prove absent/blank/non-numeric/negative headers all degrade to "no signal",
  never to a fabricated zero.

Two pre-existing credit-guard tests were updated (not weakened): they asserted the old
table-upsert write path, which moved to the RPC. The behaviour under test is unchanged — only
where the write lands.

---

## Current period and next rollover

| | |
|---|---|
| **Current active period** | **`2026-09`** — 276/500 used, trip at 450 |
| **Next rollover** | **`2026-10-01 00:00:00 UTC`** (verified by SQL: `date_trunc('month', now()) + 1 month`) |
| What happens then | The first cycle on/after that instant computes `period_key = 2026-10`, finds no row, reads **0 used**, and proceeds. No reset runs. No provider call is needed. September's row is left untouched and queryable. |

---

## `cron-news-worker` natural tick — OBSERVED, and it succeeded

The 20:00 UTC tick fired while this session was still open and was observed **read-only**. It was
not triggered.

```
2026-09-16 20:02:27  cron_dispatch starting target=news-worker
                     base_url=https://sports-intel-layer-dev.up.railway.app
2026-09-16 20:02:29  POST .../v1/internal/news-worker/run "HTTP/1.1 200 OK"
2026-09-16 20:02:29  cron_dispatch succeeded target=news-worker result={'status': 'success',
                     'games_considered': 16, 'teams_considered': 32, 'teams_due': 0,
                     'teams_skipped_not_due': 32, 'teams_unresolved': [],
                     'failures': [], 'error': None}
```

Railway agrees: `lastExecutionStatus: succeeded` at `2026-09-16T20:02:30.724Z`, zero failures,
`state: cronSucceeded`. **The crash loop that had been running since 16:05 is over.**

**One honest qualification.** This tick completed in **1.2 seconds** because `teams_due: 0` — every
team was correctly throttled by the News Worker's own cadence, so no GNews fetch happened. That
proves the dispatcher is healthy and the service is no longer crashing, but it does **not**
independently re-prove the 120s-`ReadTimeout` diagnosis, because nothing slow ran. The evidence
for that diagnosis remains what it was: a failure at exactly 120 seconds with an empty httpx
message, on an image built one day before the timeout went 120s → 600s. The first tick that
actually fetches will be the conclusive one — and if it still times out, the fault is in the
endpoint rather than the dispatcher, and **Sentry will now report it** instead of it being
invisible.

A second, quieter confirmation: this run produced **no Sentry event**, which is correct. `success`
is on the non-reportable list shipped earlier today, so the new cron instrumentation stayed silent
on a healthy cron exactly as designed.

---

## Is odds collection now safe across month boundaries?

**Yes.** The permanent-block failure mode is now structurally impossible rather than merely
unlikely:

| Risk | Before | After |
|---|---|---|
| Guard compares lifetime usage to a monthly budget | **yes** — would trip and stay tripped | **no** — usage is period-scoped |
| A stale period row blocks a new month | **yes, permanently** | **impossible** — never read |
| Rollover needs a manual reset | **yes** | **no** — it is a lookup |
| Rollover can half-apply | n/a (never ran) | **no** — nothing mutates |
| Boundary-time disagreement with the vendor | **unprotected** | **covered both ways** by header reconciliation |
| Concurrent writes at the boundary | read-then-write race | **atomic upsert** |
| Restart resets usage | no | no (unchanged) |

Also preserved exactly as required: **500-credit allowance, 50-credit floor, daily call budget
(20/6), near-kickoff reserve, and odds backoff logic** — all untouched.

One honest limit: the vendor's reset is now handled correctly *as documented*. If the vendor's
actual reset instant drifts from UTC midnight on the 1st, header reconciliation is what absorbs
it — which is precisely why it was built rather than relying on date arithmetic alone.

---

## Can `MASTER_REFRESH_ENABLED` be enabled permanently?

**Yes. This was the last stated blocker, and it is closed.**

The reasoning, laid out plainly:

- The blocker you named — *"fix the rollover before enabling additional permanent automation"* —
  is resolved, tested, migrated and deployed.
- The coupling I flagged last pass (schedule refresh creates games → games become odds candidates
  → more odds spend → trip date closer) is no longer dangerous, because a trip is now bounded to
  a single month and self-clears on the 1st rather than being permanent.
- Master Refresh itself spends **SportsDataIO, 1 call/day** — an independent provider with no
  shared guard. It cannot be blocked by, and cannot exhaust, the odds ledger.
- Everything else was already verified: `cron-schedule-refresh` is on `dev`, built from current
  code, Sentry-instrumented, scheduled `0 9 * * *`, targeting the 1-call `schedule-refresh` path.

**Exact step:** set `MASTER_REFRESH_ENABLED=true` on `sports-intel-layer` (dev) **without**
`skipDeploys` (or push), and confirm a new SUCCESS deployment before the 09:00 UTC tick. The first
enabled run auto-recovers GameKey `202610902` (CIN @ ATL, Week 9), taking the season 271 → 272.

Two things I would still watch on the first enabled day, neither a blocker: the 09:00 run's
`schedule_entries_persisted` (expect ~272 now that the venue alias fix has shipped), and the first
odds cycle that actually spends a call, which will be the first live exercise of the reconciliation
path — it will populate `provider_reported_used` and reveal any real disagreement with our 276.

---

## What was NOT done

- **Zero provider calls. Zero LLM calls.**
- **No odds cadence change**, no cron change, `MASTER_REFRESH_ENABLED` still `false` (enabling it
  is your call, per the report above).
- **No manual counter reset** — no longer needed; the design makes it unnecessary rather than
  merely deferred.
- **`cron-news-worker` not triggered** — 20:00 UTC tick still pending.
- **Staging/production untouched** — the migration was applied to dev only, matching where this
  ledger has always lived.
- No unrelated repairs: the 5 pre-existing wall-clock failures, Player Props Worker's missing
  attempt state, and `sports-intel-layer`'s pre-init startup window all remain reported, not fixed.
