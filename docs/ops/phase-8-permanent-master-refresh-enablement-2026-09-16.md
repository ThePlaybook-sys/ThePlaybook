# Permanent Master Refresh Enablement (2026-09-16)

**Directive:** MANSA HQ — "PERMANENT MASTER REFRESH ENABLEMENT." Authorize permanent DEV schedule
autonomy; `cron-schedule-refresh` becomes the canonical schedule-maintenance path.

**Compliance:** zero LLM calls. No provider call made by this session. Odds cadence untouched, no
recommendations run, `cron-master-refresh` neither used nor reactivated, the Schedule endpoint not
manually triggered.

---

## Status: enabled and verified. The first enabled run has NOT yet happened.

Steps 1–3 are complete and verified live. **Steps 5–7 require the next natural 09:00 UTC
execution**, which is **2026-09-17 09:00 UTC — about 11.7 hours after this pass closed at
21:16 UTC.** Per step 4 the endpoint was deliberately **not** manually triggered: there is no
deployment or configuration problem to recover from, so the natural run is the correct one.

Everything needed to verify that run the moment it lands is frozen below.

---

## 1. `MASTER_REFRESH_ENABLED` live state

**Set to `true` on `sports-intel-layer` dev, without `skipDeploys`.**

```
set-variables → { variableNames: ["MASTER_REFRESH_ENABLED"], skippedDeploys: false }
```

`skippedDeploys: false` confirms a redeploy was triggered rather than suppressed, which is exactly
what the directive required.

**One honest limit on verification.** Railway returns variable **names only** to this session
(`valuesRedacted: true`), so I cannot read the value back to prove it says `"true"`. What I *can*
prove, and did, is the chain the directive actually asked for: the variable was set with a `"true"`
payload, the call reported it applied live (not staged), and a **new deployment created after that
call reached SUCCESS** (§2). The value is not assumed live because it was staged — it is live
because a fresh deployment carrying it succeeded.

The gate's own semantics make this safe either way: `master_refresh_enabled()` is
**explicit-opt-in** — only a case-insensitive `"true"` runs the refresh, and both unset and
`"false"` pause. So the only failure mode is a run that does nothing and reports
`status="paused"`, never an unintended spend.

## 2. Deployment result

| | |
|---|---|
| Deployment | **`3518db50-f572-4a77-909f-2ea76a6dbf0e`** |
| Created | 2026-09-16 **21:15:37** UTC — *after* the variable was set |
| Status | **SUCCESS** at 21:15:57 UTC |
| Commit | `e9cf697` (dev head) |

Verified by reading the deployment back, not inferred from the set-variables response.

## 3. `cron-schedule-refresh` configuration

| Required | Live value | |
|---|---|---|
| branch | `dev` | ✅ |
| target | `CRON_DISPATCH_TARGET` present | ✅ (see note) |
| schedule | `0 9 * * *` | ✅ |
| restart policy | `NEVER` | ✅ |

Also: root `apps/workers`, start `python -m app.cron_dispatch`, `SENTRY_DSN` present (by
reference), watch patterns `apps/workers/**`, active deployment `ebfc24a9` **SUCCESS**.

**Note on the target.** The variable is present and was not touched by this pass, but the current
deployment has not ticked yet, so there is no fresh log line reading `target=schedule-refresh` on
*this* build. Its value was runtime-verified in the prior session (a disabled-gate tick returned
`status="paused"` with exit 0, which also proved the deployed runtime genuinely contains that
target — an unknown target raises and exits non-zero), and the real 12:45 full-season refresh ran
through this exact service. The first line of the 09:00 log will confirm it again.

**One observed inconsistency, checked and benign.** This service's config reports
`builder: RAILPACK` with no `dockerfilePath`, while its siblings report `DOCKERFILE`. The build
logs for the active deployment settle it: `FROM python:3.11-slim` → `WORKDIR /app` →
`COPY requirements.txt .` → `RUN pip install -r requirements.txt` → `COPY app ./app`. That is
`apps/workers/Dockerfile`, which Railway prefers whenever one exists in the root directory,
whatever the builder label says. The image is the right one and the label is cosmetic. Recorded
rather than "fixed", since changing it would risk the very build that must run at 09:00.

---

## 4–7. Frozen pre-run baseline

Captured **2026-09-16 21:15:20 UTC**, before the variable was set, so every post-run check has a
real "before".

| Metric | Baseline | Expected after the first enabled run |
|---|---|---|
| Regular-season games | **271** | **272** |
| Games total (incl. 4 legacy preseason fixtures) | 275 | 276 |
| SportsDataIO game mappings | 271 | 272 |
| **GameKey `202610902`** (CIN @ ATL, Wk 9) | **absent (0)** | **present (1)** |
| Week 1 final games | 16 | 16, unchanged |
| Week 1 score/finalized fingerprint | `9141a4ec48c77571c54ce4b43510e026` | **identical** |
| Week 2 games | 16 | 16, unchanged |
| Week 2 with `the_odds_api` mapping | 16 | 16, unchanged |
| `players` / `roster_memberships` / `depth_chart_snapshots` | 1494 / 34 / 4 | **unchanged** (proves 0 roster calls) |
| `master_refresh_runs` rows | 1 | 2 |
| Credits used, period `2026-09` | 276 | unchanged by the schedule run (SportsDataIO ≠ Odds API) |
| `odds_snapshots` | 1686 | unchanged by the schedule run |
| `odds_worker_poll_state` rows | 0 | — |
| `odds_api_daily_call_budget` rows | 0 | — |

The fingerprint above is computed as `md5(agg(final_score || finalized_at order by id))` over Week
1 — **defined here for this comparison**, and deliberately not compared against the differently
computed `483f677b…` figure quoted in earlier passes. Compare post-run against `9141a4ec…`.

**Why the roster counts are the proof of "0 roster requests":** the `schedule-refresh` target calls
`run_schedule_refresh`, which is the 1-call path; `run_master_refresh` (up to 33 calls, including
up to 32 roster calls) is a different target and is not wired to any live cron. If
`players`/`roster_memberships`/`depth_chart_snapshots` are unchanged after the run, no roster call
was made.

### The verification query to run after the 09:00 tick

```sql
select
  (select count(*) from games where sport='nfl' and season_type='regular')            as season_games,
  (select count(*) from game_provider_ids where provider_name='sportsdataio')         as sdio_maps,
  (select count(*) from game_provider_ids where provider_name='sportsdataio'
      and provider_game_id='202610902')                                               as gamekey_202610902,
  (select count(*) from games where week=1 and season_type='regular' and status='final') as wk1_final,
  (select md5(string_agg(coalesce(final_score::text,'')||coalesce(finalized_at::text,''),'|' order by id))
     from games where week=1 and season_type='regular')                               as wk1_fingerprint,
  (select count(*) from games where week=2 and season_type='regular')                 as wk2_games,
  (select count(*) from players)                                                      as players,
  (select count(*) from roster_memberships)                                           as roster_memberships,
  (select count(*) from depth_chart_snapshots)                                        as depth_charts,
  (select count(*) from master_refresh_runs)                                          as runs;
```

Plus the run row itself (`schedule_entries_persisted`, `games_created`, `games_updated`,
`coverage_complete`, `coverage_gaps`, `error`) and a duplicate/conflict sweep:

```sql
-- must all be zero
select
  (select count(*) from (select provider_game_id from game_provider_ids
     where provider_name='sportsdataio' group by provider_game_id having count(*)>1) d) as gamekeys_mapped_twice,
  (select count(*) from (select game_id from game_provider_ids
     where provider_name='sportsdataio' group by game_id having count(*)>1) d)          as games_with_two_gamekeys,
  (select count(*) from (select home_team, away_team, scheduled_start::date, count(*)
     from games where sport='nfl' and season_type='regular'
     group by 1,2,3 having count(*)>1) d)                                               as same_matchup_same_day_dupes;
```

### What "success" looks like on the run itself

- `status="success"` (not `"paused"` — `"paused"` would mean the gate did not take effect)
- exactly **one** `master_refresh_runs` row added
- `schedule_entries_persisted` ≈ **272** (up from 271 — the venue alias fix in `84c6892` admits the
  previously refused `"Retractable Dome"` row)
- `games_created` = **1**, `games_updated` ≈ 271
- `coverage_complete = true`, `coverage_gaps = []`
- exit **SUCCESS**, and — per step 6 — **no Sentry event**, because `success` is on
  `cron_dispatch`'s non-reportable list shipped earlier today

---

## 8. Cost controls — all preserved, none touched

| Control | State |
|---|---|
| Monthly allowance | **500** (`THE_ODDS_API_MONTHLY_CREDIT_BUDGET`) |
| Floor | **50** (`THE_ODDS_API_MIN_REMAINING_CREDITS`) → trips at 450 used |
| Daily max calls | **20** (`ODDS_API_MAX_CALLS_PER_DAY`) |
| Ramp reserve | **6** (`ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`) |
| Failure backoff | 15m → 6h, unchanged |
| Period rollover + header reconciliation | live, period `2026-09` |
| Odds cadence | **untouched** — `cron-odds-worker` still `*/15` |

Worth stating plainly: **the schedule refresh spends SportsDataIO, not The Odds API.** It cannot
consume odds credits. The coupling is indirect — new canonical games become odds-polling
candidates — and that is now bounded by the daily ceiling and, since the rollover work, self-clears
each month.

---

## What was NOT done

- **No manual trigger of the Schedule endpoint** (step 4) — no deployment or configuration problem
  exists, so the natural 09:00 run is the right one.
- **`cron-master-refresh` neither used nor reactivated** — still retired: no cron schedule,
  `isCronJob: false`, restart `NEVER`, stale branch that receives no pushes.
- **No odds cadence change. No recommendations run. No LLM calls. No provider call by this session.**
- **The `RAILPACK` label left alone** — changing the build config of the service that must run at
  09:00 would risk the run it is meant to protect.

---

# ADDENDUM — the first enabled run, observed (2026-09-17 09:15 UTC)

Read-only. Nothing triggered, nothing forced, no LLM call, no provider call by this session.
Steps 5–7 are now closed, and the pass surfaced **two live findings that were not part of it**.

## 5. The 09:00 run — every frozen prediction held

`cron-schedule-refresh`, deployment `de59e2f2`, fired **09:01:34 UTC**:

```
09:01:34 INFO cron_dispatch starting target=schedule-refresh base_url=http://sports-intel-layer.railway.internal:8080
09:02:15 INFO HTTP Request: POST .../v1/internal/schedule-refresh/run "HTTP/1.1 200 OK"
09:02:15 INFO cron_dispatch succeeded target=schedule-refresh result={
    'status': 'success', 'run_id': '7ded24eb-feb1-4dbd-b058-a9f25dc6d72a',
    'season_string': '2026REG', 'games_in_slate': 16,
    'schedule_entries_persisted': 272, 'games_created': 1, 'games_updated': 271,
    'coverage_days_asserted': 7, 'coverage_expected_games': 16, 'coverage_canonical_games': 16,
    'coverage_complete': True, 'coverage_gaps': [], 'error': None}
```

Against the baseline frozen at 2026-09-16 21:15:20 UTC, **before** the gate was set:

| Metric | Baseline | Predicted | **Observed** | |
|---|---|---|---|---|
| Regular-season games | 271 | 272 | **272** | ✅ |
| Games total | 275 | 276 | **276** | ✅ |
| SportsDataIO maps | 271 | 272 | **272** | ✅ |
| GameKey `202610902` | absent (0) | present (1) | **present (1)** | ✅ |
| Week 1 final | 16 | 16 | **16** | ✅ |
| Week 1 fingerprint | `9141a4ec…026` | identical | **`9141a4ec48c77571c54ce4b43510e026`** | ✅ |
| Week 2 games | 16 | 16 | **16** | ✅ |
| players / rosters / depth charts | 1494 / 34 / 4 | unchanged | **1494 / 34 / 4** | ✅ |
| `master_refresh_runs` | 1 | 2 | **2** | ✅ |
| `schedule_entries_persisted` | — | ~272 | **272** | ✅ |
| `games_created` | — | 1 | **1** | ✅ |
| `coverage_complete` / gaps | — | true / [] | **true / []** | ✅ |
| Status | — | `success` **not** `paused` | **`success`** | ✅ |

Run row `7ded24eb-feb1-4dbd-b058-a9f25dc6d72a`, `status=success`, 09:01:35, `2026REG`, 16 in slate —
**exactly one** new row.

**`status="success"` rather than `"paused"` is the proof `MASTER_REFRESH_ENABLED=true` genuinely
took effect** — which is the one thing Railway's redacted variable list could not tell us yesterday.

**0 roster calls, proven structurally**: `players`/`roster_memberships`/`depth_chart_snapshots` are
byte-identical at 1494/34/4. Exactly **1 SportsDataIO Schedule request**.

Duplicate/conflict sweep — **all three zero**, as required:

```
gamekeys_mapped_twice: 0 | games_with_two_gamekeys: 0 | same_matchup_same_day_dupes: 0
```

## 6. No Sentry event — correct

`cron_dispatch **succeeded**` with `status="success"`, which is on the non-reportable list. The
venue alias fix in `84c6892` did what it was predicted to do: `schedule_entries_persisted` rose
271 → 272 and admitted the previously-refused `"Retractable Dome"` row, recovering CIN @ ATL Week 9.

## 7. Next natural odds cycle — clean, and it cost nothing

09:46:21 UTC, not forced:

```
{'status': 'success', 'games_considered': 16, 'games_due': 0, 'games_skipped_not_due': 16,
 'games_skipped_backoff': 0, 'lines_persisted': 0, 'newly_linked': 0,
 'unresolved_events': [], 'failures': [], 'error': None, 'daily_calls_used': None}
```

- **No identity loop** — `unresolved_events: []`; the 15-row mapping repair still holds.
- **No backoff anomaly** — `games_skipped_backoff: 0`; `odds_worker_poll_state` still has **0 rows**,
  meaning no attempt has been needed at all since the hardening shipped.
- **No budget consumption** — `daily_calls_used: None`, `odds_api_daily_call_budget` has **no rows**,
  ledger unchanged at `2026-09 used=276`, `odds_snapshots` unchanged at 1686.
- All 16 Week 2 games sit in the FAR cadence tier; the new Week 9 game is far outside the window.

**Confirmed as predicted: the schedule refresh spends SportsDataIO and cannot touch odds credits.**

---

# Two findings this pass surfaced that were NOT part of it

## FINDING A — the Recommendation Worker is now reachable, and is blocked on one unset config value

The 06:15 `cron-recommendation-worker` tick was the **first ever to reach `ai-orchestrator`** — the
`AI_ORCHESTRATOR_URL` fix shipped at 00:40 repaired its transport too. It ran for six minutes across
**257 games** and **every single one returned HTTP 500**:

```
app.config.ConfigError: REFERENCE_SPORTSBOOK_PREFERENCE is not set or empty
  -- cannot generate candidates without a configured reference sportsbook preference
```

**This is the codebase refusing to guess, exactly as designed.** `app/config.py` raises rather than
defaulting to an arbitrary book, because which book's line every recommendation is priced against is
a product decision, not an inference. **It is not set on `ai-orchestrator` dev, and this session did
not set it.**

**Cost: zero.** Proven, not assumed — candidate generation is the *first* step, so it fails before
the committee is ever constructed. `recommendation_agent_outputs` still holds **3 rows, newest
2026-08-07**; `consensus_snapshots` still **1**. **No agent ran. No LLM call. No provider call.**

**One real side effect**: the run created **256 `recommendations` rows** (06:19:42–06:25:35), each
the crash-safe pre-compute idempotency marker Milestone 4.9 writes *before* computing. All 256 have
`status = NULL` and `cycle_completed_at IS NULL` — open, incomplete, not user-visible, and correctly
eligible for retry. They are harmless but they **accumulate**: tomorrow's 06:15 tick will use the new
`master_refresh_run` as its `run_id`, producing 256 fresh correlation IDs and 256 more rows.

**The decision HQ needs to make** — `REFERENCE_SPORTSBOOK_PREFERENCE` on `ai-orchestrator` dev, an
ordered comma-separated list (`"draftkings,fanduel"` is the shape used throughout the tests). Live
odds coverage in dev, so the choice is informed rather than blind:

| Book | Snapshots | Games |
|---|---|---|
| `draftkings` | 189 | 21 |
| `fanduel` | 189 | 21 |
| `betonlineag`, `betrivers`, `lowvig` | 189 | 21 |
| `betmgm` | 188 | 21 |
| `bovada` | 186 | 20 |
| `betus` | 186 | 21 |
| `mybookieag` | 177 | 21 |

Minor, noted not fixed: 4 legacy 2026-08-06 seed rows use `DraftKings`/`FanDuel` **capitalised**,
while every real provider row is lowercase. If the match is exact-string, the config value must be
lowercase.

## FINDING B — the cron Sentry instrumentation missed this, and that is a defect in my own work

**257 of 257 games failed and Sentry stayed silent.** The dispatcher logged
`cron_dispatch **succeeded**`.

The cause is precise. `result_failure_summary` checks `status == "failed"` first, then returns `None`
for anything in `_NON_ERROR_STATUSES`. The Recommendation Worker returned **`status: "completed"`**
— a member of that set — so the function returned `None` before reaching the `failures` check. And
even that check would not have fired: this worker reports per-game errors inside **`games[].error`**,
not a top-level `failures` list, which is the only shape the function knows how to read.

This is exactly the silent-failure class the instrumentation was built for, on its second real test.
It caught the postgame-grading transport failure because that worker surfaces `status="failed"`; it
missed this one because a total failure can also arrive wearing `"completed"`.

**Proposed fix, not applied — this pass was authorised read-only:** treat a result as reportable when
any per-item collection it carries (`games`, `legs`, `products`) contains entries with a non-null
`error` or a `"failed"` status, regardless of the top-level status; report at `error` when every item
failed, `warning` when some did. That covers both worker shapes without weakening the deliberate
silence on genuinely healthy cycles.

**Cost of waiting**: the next 06:15 tick fails identically and silently, and adds 256 more open rows.
That is ~21 hours away, so there is time for HQ to decide rather than for me to assume.

---

## One correction to this document's own verification instructions

Section 4–7 above told the verifier to read `schedule_entries_persisted`, `games_created`,
`games_updated`, `coverage_complete`, `coverage_gaps` and `error` **from the `master_refresh_runs`
row**. That was wrong. `master_refresh_runs` carries only `id`, `started_at`, `completed_at`,
`status`, `season_string`, `games_in_slate` and `created_at`; those six richer fields are part of the
endpoint's in-memory result object and are persisted nowhere — they live only in the
`cron_dispatch succeeded ... result={...}` log line.

No conclusion above changes: every one of those values was read from that log line, quoted verbatim
in §5, and all of them matched. Recorded so the next verifier does not waste a pass querying columns
that do not exist.
