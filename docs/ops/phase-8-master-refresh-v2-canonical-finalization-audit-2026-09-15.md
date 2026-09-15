# Master Refresh V2 + Canonical Finalization — Audit & Design

**Date:** 2026-09-15
**Directive:** MANSA HQ — "MASTER REFRESH V2 + CANONICAL FINALIZATION AUDIT"
**Type:** AUDIT + DESIGN ONLY — zero provider calls, no cron re-enabled, no schedule rows written, no Week 1 rows mutated

---

## 0. URGENT — unrelated cost leak found during this audit

The leftover `phase8-context-experiment` service is **still live and still tracking
`gateb-diag-tmp`**. Every cherry-pick push to that branch has triggered a Railway
autodeploy, and because the service's `startCommand` *is* the experiment script, each
redeploy **re-ran the full 6-call Anthropic experiment**.

| Deployment | Time | Trigger | Anthropic calls |
|---|---|---|---|
| `768fbb92` | 15:20 | dev, old script path | 0 (crashed) |
| `2a3003c0` | 15:39 | path fix | **6 — the authorized run** |
| `235273bb` | 16:54 | closeout cherry-pick | 6 (inferred) |
| `24c9d03d` | 17:07 | calibration cherry-pick | 6 (inferred) |
| `7d5b3308` | 17:17 | eligibility cherry-pick | 6 (inferred) |
| `140968eb` | 17:51 | audit-doc cherry-pick | **6 — confirmed from its log** |

So roughly **30 real Anthropic requests have been spent, against 6 authorized**. The
in-script budget guard worked correctly every time — it capped each run at 6 and
refused the 7th — but the counter is **per-process**, so every redeploy starts a fresh
budget. The guard was never designed to survive re-invocation.

**Cause:** my own cherry-picks to `gateb-diag-tmp` while that service was still live,
compounded by the deletion being blocked at the approval prompt four times.

**Immediate mitigation taken:** this pass's commit goes to **`dev` only**. The standing
dual-branch discipline is deliberately suspended until the service is gone — pushing to
`gateb-diag-tmp` right now would spend another ~6 calls.

**Action needed from you:** delete `phase8-context-experiment` in the Railway
dashboard (dev environment). It is no longer merely operational debt; it is an active,
repeating cost leak.

---

## PART A — MASTER REFRESH V2

### 1. Current Master Refresh flow

`app.master_refresh.run.run_master_refresh`:

1. Resolve season string.
2. **Schedule fetch** — `CachingAdapter(SportsDataIOScheduleAdapter, ttl=86400)` →
   `GET /v3/nfl/scores/json/Schedules/{season}`. **1 provider call.**
3. **Discard everything outside a 7-day window** — `filter_slate_window(entries,
   today, window_days=WINDOW_DAYS)` with `WINDOW_DAYS = 7`, keeping only
   `[today, today+7)`.
4. **Persist** the survivors via `persist_schedule_entries` (blocking; a failure fails
   the batch).
5. **Roster fetch, per team in the slate** — `fetch_roster` for each of up to 32 teams.
   **Up to 32 provider calls.** Non-blocking per team.
6. Batched player-id resolution.
7–8. Per-game `daily_game_intelligence` assembly.

The fragility is in steps 3 and 5, not in persistence.

### 2. Does the provider response already contain the full season? — **Yes**

The adapter's own documentation records **"every one of the 304 captured Schedules
rows — fetched by requesting the `2026REG` season string"**. One call returns the
entire regular season. Step 3 then throws away ~288 of those 304 legitimate rows on
every run.

This is the single most important finding in Part A: **the data is already paid for and
already in hand.** Discarding it is a pure, self-inflicted coverage loss.

### 3. Recommended persistence horizon — **the full returned season**

Persist every legitimate entry the provider returns, for the season requested. Rationale:

- **Zero additional provider cost.** Same response, same call.
- It removes the entire class of "week N never got ingested" failures — including the
  one that produced the current Week 2 gap.
- It makes the schedule robust to missed runs. Today, one skipped day permanently
  loses whatever fell out of the window; with full-season persistence, any single
  successful run restores complete coverage.
- The Odds Worker is unaffected: it derives `due_games` from its own
  kickoff-proximity logic (`classify_window`), not from the schedule's persistence
  horizon. Persisting October games does not cause October odds polling.

**Explicitly: the 7-day window becomes a completeness ASSERTION, not a persistence
boundary.**

### 4. Rolling 7-day completeness rule

After each refresh, assert that canonical coverage exists for every day in
`[today, today + 7)` — a continuously rolling guarantee (Tuesday run → Tue–Mon,
Wednesday run → Wed–Tue). The assertion is a **post-persistence health check**, not a
filter:

- Compute, per day in the window, how many canonical games exist.
- Report the result on `MasterRefreshResult` (e.g. `coverage_days_asserted`,
  `coverage_gaps`).
- A gap is a **loud, reported condition** — never silently tolerated, and never
  "fixed" by inventing games. An NFL Tuesday/Wednesday legitimately has zero games, so
  the rule asserts *"the schedule was successfully reconciled across this window"*, not
  *"every day has ≥1 game"*.

### 5. Idempotent reconciliation — **already correct, needs one guard**

`persist_schedule_entries` is already idempotent by construction, and no redesign is
needed:

- Identity is the `(provider_name, game_external_id)` mapping in `game_provider_ids` —
  never fuzzy team/date matching.
- Found → `PATCH` mutable fields. Not found → `INSERT` + `link_provider_id`.
- It never deletes, never duplicates, never invents. Re-running it is safe.
- Rows it creates get `manual_seed` default `false`, correctly distinguishing them
  from today's 19 manually-seeded rows.

**One real risk to add a guard for:** the PATCH overwrites `status` from the schedule
provider on every run. Once Part B finalization lands, a Master Refresh run could
regress a game from `final` back to a stale schedule status. **Recommended rule:
`final` is terminal — never downgrade a game that has `finalized_at` set.** This is a
new, small condition in the update path, not a redesign.

### 6. Schedule ↔ roster decoupling

**There is no genuine dependency.** Schedule persistence (step 4) completes entirely
before any roster call (step 5); roster failures are already explicitly non-blocking
and never prevent a game from being created or reconciled. Rosters feed
`persist_roster` (players, provider ids, roster memberships, depth charts) and the
`players` section of `daily_game_intelligence` — neither of which is needed for
canonical game identity.

**Design: split into two independently-scheduled operations.**

| | Schedule Refresh | Roster Refresh |
|---|---|---|
| Purpose | canonical games + coverage assertion | players, depth charts, DGI player data |
| Provider cost | **1 call** | up to 32 calls |
| Suggested cadence | **daily** | weekly, or game-day-scoped for teams actually playing soon |
| Failure impact | blocking (schedule integrity) | isolated, non-blocking |

Smallest safe separation: extract steps 1–4 (+ the new coverage assertion) into a
`run_schedule_refresh`, leave steps 5–8 in a `run_roster_refresh`, and have the
existing `run_master_refresh` call both so no current caller breaks. Then give them
separate cron targets and budgets.

### 7. Explicit disabled / no-op cron design

Today's sentinel (`CRON_DISPATCH_TARGET="master-refresh-DISABLED-pending-authorization"`)
makes `dispatch` raise `CronDispatchError`, exit non-zero, and post a **CRASHED**
deployment every single day — a deliberate pause that is indistinguishable from
infrastructure failure.

**The codebase already has the right pattern**, built for the MSF pause
(`app.workers.msf_postgame_dispatcher`): `MSF_POSTGAME_ENABLED`, read first, before any
Supabase query or provider call — unset or anything other than a case-insensitive
`"false"` means enabled, so an accidentally-removed variable fails *safe* (keeps
running). When paused it makes literally zero calls, logs one clearly-labelled
warning, and returns `paused=True`.

**Mirror it exactly:** `MASTER_REFRESH_ENABLED=false` →
- checked as the first statement of the refresh entry point, before any provider or
  Supabase call,
- zero provider calls,
- one clearly-labelled "paused" log line,
- returns `MasterRefreshResult(status="paused", ...)`,
- **exits 0** — a clean no-op deployment, not a CRASHED one.

Then restore `CRON_DISPATCH_TARGET=master-refresh` so the target is valid again, and
let the enabled flag carry the pause semantics. Same lifecycle the MSF pattern already
documents: ACTIVE → PAUSED → RE-ENABLED, with no special resume path, because pausing
the entry point never creates a separate data state.

### 8. Stale cron branch findings

Four dev cron services are pinned to the stale branch `claude/new-session-fqsad5`
instead of `dev`:

| Service | Branch | Cron | Last deploy |
|---|---|---|---|
| `cron-master-refresh` | `claude/new-session-fqsad5` | `0 6 * * *` | 2026-09-15 (CRASHED) |
| `cron-recommendation-worker` | `claude/new-session-fqsad5` | `15 6 * * *` | 2026-08-27 |
| `cron-postgame-grading` | `claude/new-session-fqsad5` | `*/30 * * * *` | 2026-08-27 |
| `cron-adaptive-weighting` | `claude/new-session-fqsad5` | `0 8 * * *` | 2026-08-27 |

All other services track `dev` (or are image/no-branch). These four have been running
~3-week-old code and silently miss every `dev` fix. **Not changed in this pass**, per
instruction. `cron-postgame-grading` is on the calibration critical path, so its
staleness matters beyond hygiene.

---

## PART B — WEEK 1 CANONICAL FINALIZATION

### 9. Root cause

**MSF postgame ingestion succeeded completely; canonical finalization is wired to a
different, never-run provider path.**

Evidence:

- `game_postgame_ingestion_state`: **all 16 Week 1 games are `confirmed_complete`**
  (2026-09-13 → 2026-09-15). MSF did its job.
- Canonical rows nonetheless read `status = 'scheduled'`/`'live'`, `final_score = null`,
  `finalized_at = null`.
- `mark_game_finalized` and `update_final_score` (both in
  `app.persistence.games`) exist — and their **only** caller is
  `app.workers.postgame_worker`, the **SportsDataIO** postgame worker, whose own
  docstring states *"`final_score` is derived from `TeamGameStats`"* — a SportsDataIO
  endpoint.
- The MSF postgame path (`msf_postgame_dispatcher` → `mysportsfeeds_game_boxscore`)
  captures and stores boxscores but **never calls either finalization function**.

So the answer to the directive's own hypothesis is yes: **SportsDataIO finalization was
assumed, and MSF completion was never wired to canonical finalization.** There is no
finalization/reconciliation function that reads MSF state. This is a genuine missing
link, not a misconfiguration.

### 10. Can Week 1 be finalized from persisted data with zero provider calls? — **Yes**

The real final scores are already sitting in `game_events.raw_payload`:

- **18 boxscore rows covering all 16 distinct games**, every one carrying
  `body.scoring.homeScoreTotal` and `body.scoring.awayScoreTotal`.
- `body.game.playedStatus` reads `COMPLETED`.

Live samples (real persisted values, not reconstructed):

| Game | MSF score | `playedStatus` | canonical status today |
|---|---|---|---|
| NE @ SEA | 13–10 | COMPLETED | `scheduled` |
| SF @ LAR | 27–7 | COMPLETED | `live` |
| CLE @ JAX | 10–34 | COMPLETED | `scheduled` |
| ATL @ PIT | 13–20 | COMPLETED | `scheduled` |
| BUF @ HOU | 36–31 | COMPLETED | `scheduled` |

**A finalization pass needs no provider call at all** — only a reconciler that reads
already-persisted MSF boxscores and writes `status='final'`, `final_score`,
`finalized_at` through the existing `update_final_score` / `mark_game_finalized`
functions.

Two details for the implementation (not done here):

- **18 rows / 16 games means duplicates exist.** Deduplicate per game before writing —
  this codebase already has the canonical-observation pattern
  (`app.context_intelligence.observation_identity.resolve_canonical_observation`) for
  exactly this.
- Only finalize where `playedStatus == COMPLETED`; anything else stays untouched
  rather than guessed.

---

## PART C — COST / CALL PLAN

### Today (if Master Refresh were re-enabled unchanged)

| | Calls |
|---|---|
| Schedule | 1 |
| Rosters | up to 32 |
| **Daily total** | **up to 33** |

### After the V2 redesign

| Operation | Cadence | Provider calls |
|---|---|---|
| **Schedule Refresh** | daily | **1** |
| Roster Refresh | weekly (or game-day scoped) | up to 32, amortised |
| Week 1 finalization backfill | one-off | **0** |

**Daily schedule integrity costs exactly 1 SportsDataIO call**, and it delivers the
full season rather than a 7-day slice. The roster-call explosion disappears from the
daily path entirely — which is precisely the condition the directive set for
authorizing re-enablement.

---

## 12. Exact implementation sequence (nothing started)

Each step is separately authorizable.

1. **Delete `phase8-context-experiment`** — stop the active cost leak (§0). Blocking
   for resuming normal `gateb-diag-tmp` discipline.
2. **Week 1 canonical finalization backfill** — zero provider calls, pure
   already-persisted data. Unblocks grading, and therefore the entire calibration
   critical path. *Highest value per unit of risk; do this first of the code work.*
3. **`MASTER_REFRESH_ENABLED` pause flag** — mirror the MSF pattern, so a disabled
   Master Refresh exits 0 instead of CRASHING. No provider calls.
4. **Split Schedule Refresh from Roster Refresh** — the 1-call/32-call decoupling, plus
   full-season persistence and the `final`-is-terminal status guard. No provider calls
   to build; this is what makes re-enablement affordable.
5. **Rolling 7-day coverage assertion** reported on the result object.
6. **Then, and only then, authorize one real Schedule Refresh** — 1 SportsDataIO call,
   ingesting the full season including Week 2.
7. Odds → pre-kickoff recommendation cycle → wait for kickoff → grade → first
   legitimate calibration observation.

Steps 2–5 need no provider calls whatsoever. Step 6 is the first spend, and by then it
costs one call instead of thirty-three.
