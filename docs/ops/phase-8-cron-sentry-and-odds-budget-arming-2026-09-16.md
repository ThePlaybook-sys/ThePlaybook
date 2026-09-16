# Cron Sentry + Odds API Budget Arming (2026-09-16)

**Directive:** MANSA HQ — "CRON SENTRY + ODDS API BUDGET ARMING." Two goals: extend Sentry to the
autonomous cron pipeline, and arm the Odds API daily call budget. No LLM calls, no intentional
provider calls.

**Compliance:** zero LLM calls. No intentional provider call was made by this session. The DSN
value was never read or displayed — it is supplied as a Railway **variable reference** resolved
server-side. No synthetic Sentry debug event was fired.

---

## 1. Cron services now covered by Sentry

**All 8 active cron services.** `cron-master-refresh` is excluded because it is retired (§5).

| Service | `SENTRY_DSN` | Branch | Build | First tick on new code |
|---|---|---|---|---|
| `cron-schedule-refresh` | ✅ reference | dev | SUCCESS 18:35 | next 09:00 UTC (daily) |
| `cron-odds-worker` | ✅ reference | dev | SUCCESS 18:34 | ✅ **18:46:18, success** |
| `cron-msf-postgame` | ✅ reference | dev | SUCCESS 18:34 | ✅ **18:46:19, success** |
| `cron-weather-worker` | ✅ reference | dev | SUCCESS 18:34 | ✅ **18:45:23, success** |
| `cron-news-worker` | ✅ reference | dev | SUCCESS 18:34 | next 20:00 UTC (`0 */4`) |
| `cron-postgame-grading` | ✅ reference | **dev (was stale)** | SUCCESS 18:42 | next `*/30` |
| `cron-recommendation-worker` | ✅ reference | **dev (was stale)** | SUCCESS 18:42 | next 06:15 UTC |
| `cron-adaptive-weighting` | ✅ reference | **dev (was stale)** | SUCCESS 18:42 | next 08:00 UTC |

**Environment-status sweep after the work: 8/8 deployments SUCCESS, zero failures.**

### Three things had to be fixed before any of this could take effect

**(a) The entry point.** `apps/workers/app/main.py` already initialized Sentry, but the crons run
`python -m app.cron_dispatch` — a different entry point in the same image. The SDK was installed
and never initialized. `cron_dispatch.py` now initializes it itself.

**(b) The watch-pattern freeze.** Every cron carried
`watchPatterns: ["__gate_b_frozen__/do-not-match-anything/**"]`, a pattern deliberately matching
nothing, so every push produced a **SKIPPED** build. No code change could ever have reached these
services. Lifted to `apps/workers/**` on all 8 — which is what turned the push into 8 real builds.

**(c) A stale branch nobody had counted — the significant new finding of this pass.** The previous
audit flagged `cron-master-refresh` as being on `claude/new-session-fqsad5`. In fact **four**
services were on that branch, and **three of them are live**:
`cron-postgame-grading`, `cron-recommendation-worker` and `cron-adaptive-weighting` have been
running **2026-08-27 code for three weeks** while continuing to fire on schedule. They did not
rebuild from the push because they do not track `dev` at all. All three were reconnected to `dev`
via `connect-service-source` and rebuilt.

That is not a Sentry problem; it is a correctness problem that the Sentry work uncovered. Their
cron image only contains the dispatcher (the workers themselves are invoked over HTTP on
`worker-scheduled`), so the change they picked up is the dispatcher's accumulated targets and the
120s→600s timeout — additive, and exactly what they should have had.

### Flush is not optional, and is the easiest thing to get wrong here

Sentry's transport is background-threaded. That suits a long-lived web process and **not** a job
that calls `sys.exit` seconds later: without an explicit flush a captured event can be discarded
before it leaves the container. Every exit path calls `sentry_sdk.flush(timeout=5.0)`, bounded so
a Sentry outage can never hold a cron open. `main()` also defaults `exit_code = 1`, so a job that
dies in a way it cannot report still exits non-zero rather than raising an unbound name over the
top of the real fault.

---

## 2. Structured failure capture behaviour

### Captured

| Class | Mechanism |
|---|---|
| Unhandled dispatcher exceptions | bare `except Exception` → `capture_exception` |
| Transport failures | `CronDispatchError` (DNS, connect, timeout, malformed URL) |
| Invalid configuration | `KeyError` on a missing required variable, and unknown `CRON_DISPATCH_TARGET` |
| Non-2xx internal responses | `CronDispatchError` |
| **Structured `status="failed"` in a 200 OK** | `capture_message`, level **error**, full payload attached as context |

### Not captured (normal operation)

`success` · `completed` · `paused` · `disabled` · `skipped` · `no_eligible_run` ·
`skipped_credit_guard` · `skipped_daily_budget`

A cron that correctly does nothing is not an error. Treating it as one trains the alert to be
ignored, which costs more than having no alert at all. Both guard pauses are in this list on
purpose: they mean *the guard worked*.

### The half no HTTP status code can see

This is the gap that let the odds credit leak run unnoticed. Workers here are deliberately written
never to raise — `run_odds_worker`'s own docstring says *"Always returns an `OddsWorkerResult`,
never raises"* — so a total failure arrives as a `status` field inside a **200 OK**. Dispatch
succeeds, the deployment is green, and nothing ever throws. `result_failure_summary()` closes
that.

**One judgment call, flagged rather than buried.** The directive named `status="failed"` and named
the statuses to ignore, but said nothing about `partial`. A `partial` carrying a non-empty
`failures` list is reported at **warning** level, not error. Twelve consecutive `partial` cycles
were exactly the shape of the credit leak, and a `partial` with failures is not "successful
processing" under any reading — but it is also not a total failure, hence the lower severity.
**HQ can overrule this; it is a deliberate decision, not an assumption.**

A structured worker failure still **exits 0**. The dispatch itself worked and the worker returned
a well-formed answer; marking the Railway deployment CRASHED would conflate two different
conditions and make a budget pause look like a broken job. Sentry is now the channel for this,
which is the entire point of the change.

---

## 3. `cron-weather-worker` health — FIXED, verified on the next natural tick

**Root cause:** `CRON_DISPATCH_BASE_URL` was `sports-intel-layer.railway.internal` — no scheme,
no port — so every dispatch died with *"Request URL is missing an 'http://' or 'https://'
protocol."* At `*/15` that was ~96 crashed deployments a day, silently.

**A deliberate deviation from the literal instruction, and why.** The directive said to "fix the
missing `https://`". Prefixing `https://` onto a `railway.internal` host would **not** have
worked: Railway's private network does not terminate TLS. The value was set instead to
`https://sports-intel-layer-dev.up.railway.app` — the exact URL its working siblings use, proven
on real ticks today. (`cron-msf-postgame` shows the other valid form,
`http://sports-intel-layer.railway.internal:8080`, which would also work and is cheaper; noted as
an optional follow-up, not changed.)

**Verified live at 18:45:23 UTC:**

```
cron_dispatch starting target=weather-worker base_url=https://sports-intel-layer-dev.up.railway.app
POST .../v1/internal/weather-worker/run "HTTP/1.1 200 OK"
cron_dispatch succeeded target=weather-worker result={'status': 'success',
  'games_considered': 16, 'games_due': 16, 'snapshots_persisted': 14,
  'games_skipped_dome': [2 games], 'failures': [], 'error': None}
```

It is not merely un-crashed — it did real work: **14 weather snapshots persisted** (`weather_snapshots`
4 → 18, last capture 18:45:25), 2 dome games correctly skipped, zero failures.

**Disclosed honestly:** those 14 snapshots are real WeatherAPI calls. They were not an intentional
provider call by this session — they are the normal work of a cron resuming after a fix, on the
tick HQ explicitly asked to verify. WeatherAPI is the $0 free tier (1M calls/month), so the cost
impact is nil.

---

## 4. `cron-news-worker` health — cause identified and fixed, NOT yet verified

**Root cause, established from evidence rather than inferred:**

- The failure log showed start `16:03:11` → error `16:05:11` = **exactly 120 seconds**, with an
  **empty** httpx error message — the signature of `httpx.ReadTimeout`, whose `str()` is empty.
- `git log -S` shows the dispatcher's client timeout went **120s → 600s** in commit `1cde0c6`,
  dated **2026-09-14 13:09 UTC**.
- The service's active deployment `d1695e07` was created **2026-09-13** — one day *before* that
  commit.

So it was running a stale image that still used the 120s timeout, against an endpoint that takes
longer than 120s. **Fixed only at that cause:** the rebuild (SUCCESS, 18:34) carries the current
600s timeout. No code was changed for it, no other setting touched.

**NOT YET VERIFIED, stated plainly.** Its schedule is `0 */4 * * *`, so the next natural tick is
**20:00 UTC** — outside this pass. The fix is deployed and the reasoning is evidence-backed, but
until that tick runs I cannot claim it is healthy. If the endpoint turns out to need more than
600s, the remaining fault is in the endpoint, not the dispatcher, and Sentry will now say so
instead of the failure being invisible.

---

## 5. `cron-master-refresh` retirement

**Retired, cleanly, and not re-enabled:**

- `cronSchedule` **removed** — confirmed absent from the live config. `isCronJob` now reads
  **false**; no further executions will ever be scheduled.
- `restartPolicyType: NEVER` — its last CRASHED deployment (06:00) will not retry.
- Left on the stale branch `claude/new-session-fqsad5`, which receives no pushes, so nothing can
  trigger a rebuild.
- Deliberately **not** given a `SENTRY_DSN`: instrumenting a retired service would be noise.

`cron-schedule-refresh` is the canonical schedule cron, on `dev`, instrumented, and healthy.

**Deleting the service outright was NOT done.** It is irreversible, and "retire/disable cleanly"
reads as the reversible action. The service is inert in its current state. Say the word and it can
be deleted.

---

## 6. Service / release tagging

| Tag | Value | Status |
|---|---|---|
| `environment` | `RAILWAY_ENVIRONMENT_NAME` (`dev`) | ✅ |
| `service` | `RAILWAY_SERVICE_NAME` (e.g. `cron-odds-worker`) | ✅ **new** |
| `cron_target` | `CRON_DISPATCH_TARGET` (e.g. `odds-worker`) | ✅ **new** |
| `release` | `RAILWAY_GIT_COMMIT_SHA` → `RAILWAY_DEPLOYMENT_ID` → `None` | ⚠️ see below |

The `service` tag closes the audit's §6 finding directly: four backend services shared one Sentry
project with nothing but an opaque Railway container hostname to distinguish them, so a
per-service alert rule was not previously expressible. It is now.

**Release is honest about what it can get.** `RAILWAY_GIT_COMMIT_SHA` is the value actually wanted
(it maps an event to a commit) but it does **not** appear in any cron service's variable list, so
it may well be absent at runtime. The deployment id is the fallback — weaker, but it still
distinguishes one build from another. If neither is present, Sentry records **no release rather
than a fabricated one**. Tested for all three cases. If HQ wants firm commit attribution, the fix
is to expose `RAILWAY_GIT_COMMIT_SHA` (or set `SENTRY_RELEASE`) on these services.

---

## 7. Confirmed Odds API monthly allowance — **500 credits/month, no provider call needed**

Established entirely from existing configuration and account records in this repository.
**Five independent corroborations**, not one:

1. **The literal value, recorded the day it was set** (`PROGRESS.md`, 2026-09-07):
   *"Both `THE_ODDS_API_MONTHLY_CREDIT_BUDGET=500` and `THE_ODDS_API_MIN_REMAINING_CREDITS=50`
   … were set on `sports-intel-layer` DEV before the real call."*
2. **The plan it comes from** (2026-08-10 procurement checkpoint, corrected against Mac-supplied
   official vendor data): *"The Odds API's free Starter plan is 500 credits/month."*
3. **`174/500`** — ledger reading, 2026-09-07.
4. **`180/500`** — ledger reading, same period.
5. **`234/500`** — ledger reading, 2026-09-08.

Plus the derived trip point recorded twice as **"450-credit safety trip point"**, which is exactly
`500 − 50`. Every figure is mutually consistent.

This matches the directive's `~500` condition, so the values were set rather than reported back.

---

## 8–10. Final budget values and exposure

| | |
|---|---|
| **`ODDS_API_MAX_CALLS_PER_DAY`** | **20** |
| **`ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`** | **6** |
| Credits per call | 3 (`markets=h2h,spreads,totals` × `regions=us`) |
| **Maximum daily credit exposure** | **60 credits** |
| Reserved for near-kickoff ramp | 6 calls / **18 credits** |
| Reachable by ordinary (FAR-tier) polling | 14 calls / **42 credits** |

Both are live on `sports-intel-layer` dev, confirmed present on the running deployment
(`23953da9`, SUCCESS 18:33, commit `73bfdd2` — created *after* the variables were set, so it was
built with them).

**Context against measured behaviour:** a real 13-game Sunday costs ~19 calls / ~57 credits, so 20
is roughly one call of headroom on the single heaviest day of the week and materially tighter than
the 40 previously recommended. That is a deliberately conservative ceiling given a 500/month
allowance, and it is the daily *maximum*, not the expected spend (a quiet weekday costs ~2 calls /
6 credits).

**One caveat stated plainly:** 20 calls/day × 30 days × 3 = 1,800 credits, which is far above 500.
The daily ceiling bounds a **burst**; the *period* is bounded by the existing monthly guard
(trips at 450 used). The two are complementary by design and both are now armed. Current period:
**276/500 used**, 174 credits (58 calls) of headroom before the monthly guard trips.

---

## 11. Tests / regressions

**`apps/workers`: 67 passed** (was 45 — **+22, zero failures**).
**`sports-intel-layer`: 1021 passed / 5 failed. `ai-orchestrator`: 987 passed.**

The 5 are the same pre-existing wall-clock failures in `test_odds_cadence_persistence.py`,
verified on a clean tree in an earlier pass as byte-identical.

New file `tests/test_cron_dispatch_sentry.py` (22 tests), covering:

- **initialization** — environment, `send_default_pii=False`, both identity tags, the three-way
  release fallback, and that a missing DSN *disables* Sentry rather than failing the job
  (telemetry must never be the reason a scheduled job fails to run);
- **flush before exit** — asserted on both the success and failure paths;
- **all four captured failure classes** plus the unknown-target case;
- **structured `status="failed"`** — captured at error level with the payload attached, exiting 0;
- **`partial` with failures** — captured at warning;
- **nine parametrized normal-operation payloads** — each asserting `messages == []` and
  `exceptions == []`, so a future edit cannot quietly start alerting on a healthy cron;
- **the classifier directly**, pinning both guard pauses as normal, because those are the two a
  future edit is most likely to get wrong.

**Budget-exhaustion behaviour is proven by test, not by inducing it live** (per the directive):
`test_D1` asserts an exhausted budget makes **no provider call**, does **not** increment the
counter, records **no attempt**, and returns `skipped_daily_budget`; `test_D2` asserts the result
is **not** `failed`, carries **no** failures, and therefore exits 0 — a clean pause, never
CRASHED. And `cron_dispatch` now explicitly lists `skipped_daily_budget` as non-reportable, so a
budget pause will not generate a Sentry alert either.

**Live confirmation the new odds code is deployed:** the 18:46 tick returned
`'games_skipped_backoff': 0, 'daily_calls_used': None` — both fields are new in this build.
`daily_calls_used` is `None` because `games_due: 0`, so no call was made and the budget was never
queried, which is exactly correct. The first live *number* will appear on the next tick that
actually spends a call (Week 2 games are all FAR; next due ~2026-09-17 13:00 UTC).

---

## 12. Are cron monitoring and odds economics now safe for unattended use?

**Cron monitoring: yes, with one dependency outside this session.**

Eight of eight active crons initialize Sentry, carry a DSN by reference, tag themselves by service
and target, capture all five failure classes including the structured one no status code can see,
stay quiet on eight normal outcomes, and flush before exit. Three live faults were removed in the
process (a broken URL, a stale image, and three services silently three weeks out of date).

**The dependency:** whether an alert *rule* exists and delivers to Mac still cannot be inspected
from this session — there is no Sentry tooling here. The previous audit's cheapest check applies
and is now cheaper, because the crons are no longer silent. **Note the likeliest silent failure is
a rule scoped to `environment: production` while every service here tags itself `dev`.**

**Odds economics: yes, materially safer, with one finding that is not safe and is not mine to fix
silently.**

Safe now: backoff bounds a broken game to ≤4 retries/day; the daily ceiling bounds a day to 60
credits; the monthly guard bounds the period at 450; a pause is a clean exit-0, not a crash; and
the leak has now held closed for **2.5 hours** (ledger unmoved at 276 since 16:16:22).

> **⚠️ The monthly ledger has no rollover, and this will silently break.**
> `odds_api_credit_ledger.record_call` writes only `credits_used_this_period` and `updated_at` —
> it **never** advances `period_start`, which still reads **2026-09-07**. The vendor's month rolls
> over around **2026-10-07**; our counter will not. It will keep accumulating past 450 and the
> monthly guard will trip **permanently**, silently stopping all odds collection while the real
> allowance is full. Nothing in the code resets it. This is a genuine unattended-operation
> blocker, it was outside this directive's two goals, and it is **reported, not fixed.**

---

## 13. Exact next step to permanently enable `cron-schedule-refresh`

One variable, no deploy needed for the cron itself:

```
Set MASTER_REFRESH_ENABLED=true on sports-intel-layer (dev)
```

Everything else is already in place and verified: `cron-schedule-refresh` is on `dev`, built from
current code (SUCCESS 18:35), instrumented with Sentry, scheduled `0 9 * * *`, targets
`schedule-refresh` (1 SportsDataIO call/day, not the up-to-33-call combined refresh), and is
currently inert only because the gate is false.

Because the gate lives on `sports-intel-layer`, setting it requires that service to pick the value
up — so set it **without** `skipDeploys` (or push), and confirm a new SUCCESS deployment before
the 09:00 tick.

**What it buys:** canonical schedule maintenance becomes autonomous — the last layer still
requiring a human to spend a call — and the first enabled run auto-recovers GameKey `202610902`
(CIN @ ATL, Week 9), taking the season 271 → 272, since the venue alias fix shipped in `84c6892`.

**Recommended ordering:** do the ledger-rollover fix (§12) first or at the same time. Enabling more
autonomy on top of a guard that will silently trip permanently in three weeks is the wrong order.

---

## What was NOT done

- **Zero LLM calls. No intentional provider call.** (The weather cron's 14 WeatherAPI snapshots are
  its own resumed scheduled work on the tick HQ asked to verify — disclosed in §3, $0 free tier.)
- **No synthetic Sentry debug event fired**, per the directive.
- **No DSN value read or displayed** — supplied as `${{sports-intel-layer.SENTRY_DSN}}`, resolved
  server-side.
- **No odds cadence changed.** `windows.py` untouched; `cron-odds-worker` still `*/15`.
- **Budget exhaustion not induced live** — proven by test and config inspection.
- **`cron-master-refresh` not deleted** (retired/disabled only) and **not re-enabled**.
- **Ledger rollover not fixed** — reported in §12.
- **`cron-news-worker` not yet verified** — next natural tick 20:00 UTC (§4).
- No unrelated repairs: the 5 pre-existing test failures, Player Props Worker's missing attempt
  state, and `sports-intel-layer`'s pre-init startup window all remain reported, not fixed.
