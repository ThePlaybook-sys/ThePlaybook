# Dedicated Schedule Refresh Cron

**Date:** 2026-09-16
**Directive:** MANSA HQ — "DEDICATED SCHEDULE REFRESH CRON"
**Type:** INFRASTRUCTURE — **zero provider calls.** The authorized SportsDataIO Schedule call is still **unspent**.
**Gate:** `MASTER_REFRESH_ENABLED=false` on `sports-intel-layer` (dev) throughout.

---

## 1. Why this exists

The previous pass tried to run the schedule refresh by temporarily repointing `cron-msf-postgame`.
It failed twice, and neither failure was the provider's or the code's:

- `set-variables` with `skipDeploys: true` does **not** re-inject variables into an existing cron
  deployment — the 22:30 tick ran the old target from its cached snapshot.
- `set-variables` **without** `skipDeploys` created no new deployment for that cron service at all,
  so every later tick kept running the old snapshot.

The mechanism that worked earlier (the 20:16 finalization backfill) only worked because a **git
push** had autodeployed the service, and the fresh build picked up current variables. Borrowing a
cron is therefore not a reliable invocation path. This service removes the borrowing entirely.

---

## 2. What was created

**`cron-schedule-refresh`** — service `c126862d-7573-41af-a93d-56db9800b584`, **dev only**.

| Setting | Value |
|---|---|
| source repo | `ThePlaybook-sys/ThePlaybook` |
| **branch** | **`dev`** |
| root directory | `apps/workers` |
| start command | `python -m app.cron_dispatch` |
| cron schedule | **`0 9 * * *`** (daily, 09:00 UTC) |
| restart policy | `NEVER` |
| public domain | **none** |
| variables | `CRON_DISPATCH_TARGET=schedule-refresh`, `CRON_DISPATCH_BASE_URL=http://sports-intel-layer.railway.internal:8080`, `INTERNAL_SERVICE_TOKEN` |

It has exactly one responsibility: POST `/v1/internal/schedule-refresh/run`. Nothing else.

**No secret entered this session.** `INTERNAL_SERVICE_TOKEN` was set as the Railway variable
reference `${{sports-intel-layer.INTERNAL_SERVICE_TOKEN}}`, resolved server-side at runtime. The
value was never read, printed, or requested.

### Two setup gotchas worth recording

1. **`create-deployment` ignored the `branch: dev` argument** and built from `main` (commit
   `28d99f10`), which failed. Fixed with `connect-service-source` setting repo + branch explicitly.
   **Always verify the deployed branch after creating a Railway service from a repo** — do not trust
   the create argument.
2. The schedule was set to `*/15 * * * *` **temporarily**, purely so the disabled-gate proof tick
   would fire within minutes instead of waiting a day, then changed to the permanent `0 9 * * *`.
   Config verified as daily afterwards.

---

## 3. Verification — all nine checks, before any spend

| # | Check | Result |
|---|---|---|
| 1 | dedicated cron service exists | **`cron-schedule-refresh`**, dev, live |
| 2 | target is definitely `schedule-refresh` | variable set; and the runtime log line proves it |
| 3 | deployed runtime contains that target | it resolved the path and got **`200 OK`** — an unknown target would have raised `CronDispatchError` and exited non-zero |
| 4 | one disabled-gate tick executes successfully | deployment `c545c180` **SUCCESS**, exit 0, **not CRASHED** |
| 5 | disabled tick makes zero SportsDataIO calls | **`status: 'paused'`** |
| 6 | no roster calls | **0** |
| 7 | no Odds API / MSF / LLM calls | **0** |
| 8 | `cron-msf-postgame` restored and untouched | branch `dev`, root `apps/workers`, `*/15 * * * *`, target `msf-postgame-worker`, start command unchanged |
| 9 | `MASTER_REFRESH_ENABLED` false/unset | **`false`** — and the `paused` result is runtime proof, stronger than reading config |

The proof tick, verbatim:

```
cron_dispatch starting target=schedule-refresh
  base_url=http://sports-intel-layer.railway.internal:8080
POST .../v1/internal/schedule-refresh/run "HTTP/1.1 200 OK"
cron_dispatch succeeded target=schedule-refresh result={
  'status': 'paused', 'run_id': None, 'season_string': None,
  'games_in_slate': 0, 'schedule_entries_persisted': 0,
  'games_created': 0, 'games_updated': 0, 'coverage_days_asserted': 0,
  'coverage_complete': False, 'coverage_gaps': [], 'error': None}
```

`run_id: None` is itself meaningful: the gate is checked *before* `start_master_refresh_run`, so a
paused run does not even create a `master_refresh_runs` row for work it will never do. Live: still
**0 rows** in that table.

**This is the disabled-cron design working end to end.** The old `cron-master-refresh` expresses a
pause as a daily CRASHED deployment from an invalid sentinel target; this one exits 0 with a clear
`paused` status.

---

## 4. Database — unchanged

| Measure | Value | vs. baseline |
|---|---|---|
| canonical games | 23 | unchanged |
| `status='final'` | 17 | unchanged |
| `finalized_at` set | 16 | unchanged |
| Week 1 fingerprint (`id`+`final_score`+`finalized_at`) | `483f677b…` | **identical** |
| SportsDataIO game mappings | 0 | unchanged |
| Week 2 games | 0 | unchanged |
| `master_refresh_runs` | 0 | unchanged |
| `players` / `roster_memberships` | 1494 / 34 | unchanged |
| odds / game_events / weather rows written | 0 | none |

---

## 5. Not done, deliberately

- **The authorized SportsDataIO Schedule call is NOT spent.**
- `MASTER_REFRESH_ENABLED` not enabled.
- `cron-msf-postgame` not reused or modified beyond the restore already completed.
- `cron-master-refresh` not enabled or repaired — still on its stale branch with the invalid
  sentinel target, still CRASHing daily. Untouched per directive.
- No odds, recommendation, roster or grading work triggered.

## 6. Next pass

Enable `MASTER_REFRESH_ENABLED=true`, invoke the dedicated refresh once, disable the gate again,
then inspect reconciliation before anything downstream. The guard to apply on the result:
**`reconciled` ≈ 19 and `created` ≈ 285.** If `reconciled` is near zero, the ±15-minute kickoff
tolerance needs revisiting against the real payload rather than assumption.

Invocation note for that pass: this service is daily, so a one-off run needs either a temporary
schedule change or a forced redeploy — and, per §2, the variable/config change must be confirmed
live on a *new* deployment before relying on it.
