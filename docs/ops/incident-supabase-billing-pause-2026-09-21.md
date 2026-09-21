# Incident — Supabase organization paused for an overdue invoice

**Date opened:** 2026-09-21
**Classification:** EXTERNAL BILLING / INFRASTRUCTURE PAUSE
**Not:** application regression, migration failure, database corruption, auth
defect, or deployment defect
**Invoice as reported by Mac:** $36.72
**Status:** audit complete, recovery NOT attempted, awaiting payment confirmation

Per HQ this pass is **audit only**. No migration, no schema change, no reseed,
no project delete/recreate, no credential rotation, no URL change, no Supabase
config change, no persistence workaround, no recommendation run.

---

## Confirmation that this is the platform, not us

`list_projects` returns **all four projects `INACTIVE`**:

| Project | ref | status now | status 2026-09-20 23:30 |
|---|---|---|---|
| ThePlaybook-sys's Project (**dev**) | `nhwjtsdebgiwskshzqiq` | **INACTIVE** | `ACTIVE_HEALTHY` |
| theplaybook-staging | `jhpjdjtvzzmhxvprsfaq` | **INACTIVE** | `ACTIVE_HEALTHY` |
| theplaybook-production | `dronhltumzkngwwktesf` | **INACTIVE** | `ACTIVE_HEALTHY` |
| theplaybook-demo | `tbxzecbopoxcexggesmk` | **INACTIVE** | `ACTIVE_HEALTHY` |

All four at once, across three environments that share nothing but a billing
account. No deploy went out in that window — every dev service still carries
the same deployment id it had on 2026-09-18.

**The runtime error settles it.** From `sports-intel-layer`, dev,
2026-09-21 18:04:00 UTC:

```
File "/app/app/workers/balldontlie_finalization_worker.py", line 180, in _read_candidates
    response = await client.get(
...
httpx.ConnectError: [Errno -2] Name or service not known
```

`Name or service not known` is **DNS resolution failure** — the Supabase
hostname no longer resolves. That is categorically different from every
failure mode we could have caused:

| If it were… | we would see |
|---|---|
| bad credentials / rotated key | HTTP 401 / 403 |
| missing table, bad migration | PostgREST `42P01`, HTTP 404 |
| RLS defect | HTTP 403 with a policy message |
| DB up but refusing | `ConnectError: Connection refused` |
| **host removed from DNS** | **`[Errno -2] Name or service not known`** ← this |

Only the platform can withdraw a hostname from DNS. Nothing in our code,
schema, or deployment can produce this.

---

## 1. DEV services that depend on Supabase

**All 16 — six directly, ten transitively.**

**Direct** (hold `SUPABASE_URL` + a key, and talk to it themselves):

| Service | Supabase variables |
|---|---|
| `sports-intel-layer` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| `ai-orchestrator` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| `api-gateway` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| `worker-scheduled` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| `worker-market-monitor` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| `frontend` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |

**Transitive** — the ten `cron-*` services hold **no Supabase credentials at
all**. Each is a thin dispatcher (`python -m app.cron_dispatch`) carrying only
`CRON_DISPATCH_BASE_URL`, `CRON_DISPATCH_TARGET`, `INTERNAL_SERVICE_TOKEN`,
`SENTRY_DSN`. They fail only because the endpoint they POST to cannot reach the
database: `cron-odds-worker`, `cron-weather-worker`, `cron-msf-postgame`,
`cron-postgame-grading`, `cron-balldontlie-finalization`, `cron-news-worker`,
`cron-adaptive-weighting`, `cron-schedule-refresh`, `cron-master-refresh`,
`cron-recommendation-worker` (already paused, so it is not even attempting).

---

## 2. What is BLOCKED specifically by the pause

- Every runtime data path: schedule refresh, odds capture, weather, news,
  BALLDONTLIE finalization, postgame grading, adaptive weighting.
- Any verification that reads the database — row counts, data-integrity checks,
  the post-deployment health checks in HQ's step 6.
- Re-verifying the option C routing change in the live database. **The change
  itself is already applied and independently verified through the real
  `ModelRouter` (12/12 resolve); only re-reading the rows is blocked.**
- The post-merge deployment verification, which reads live state.

**Explicitly NOT blocked:** the merge gate work. GitHub Actions never touches
Supabase, so CI is unaffected.

---

## 3. Errors that started only after the suspension

Start time is **bracketed, not precisely known** — the filtered log query needed
an approval that did not land, so rather than guess:

- **Last confirmed healthy write:** `2026-09-20 23:32:22 UTC` — a BALLDONTLIE
  finalization tick wrote a `game_events` row and finalized 4 games.
- **Last confirmed healthy read:** `2026-09-20 ~23:52 UTC` — my own routing-rule
  verification queries returned normally.
- **First confirmed failure:** `2026-09-21 18:04:00 UTC`, the traceback above.

So the pause fell between **2026-09-20 23:52** and **2026-09-21 18:04 UTC**.

**Every error observed is the same single cause** — `httpx.ConnectError` on the
first Supabase call of whatever cycle is running. No other error class appeared.

**One genuinely good consequence: the outage costs zero provider credits.** The
finalization worker's "claim first, fetch second" design means the candidate
weeks are derived from games claimed *in the database*. The traceback shows it
dying in `_read_candidates` — its very first read — so it never reaches
BALLDONTLIE. The same holds for the odds worker, whose due-game set also comes
from the database. **No paid provider request is being burned by the retries.**

---

## 4. Work already complete that does NOT depend on Supabase

Proven, not asserted — the full suite was run with Supabase unreachable:

| Suite | Result (2026-09-21, Supabase INACTIVE) |
|---|---|
| sports-intel-layer | **1091 passed** |
| ai-orchestrator | **1006 passed** |
| workers | **110 passed** |
| api-gateway | **187 passed** |
| **Total** | **2394 passed, 0 failed** |

295 test files drive `respx`, which intercepts HTTP at the transport layer, so
the suites never open a real socket. This means the following are all intact
and verifiable right now:

1. The **empty-No-Bet safety fix** (`073c27e`) and its 15 regression tests.
2. The **CI wall-clock repair** (`990a422`) — and note it passes today, a
   *different calendar day* from when it was written. That is the de-rot
   working exactly as intended.
3. The **fallback option C verification** — a pure function test over
   `ModelRouter.route()` with the live config values inlined. Re-runnable
   offline; 12/12 resolve.
4. All ops documentation and the deployment-gate audit.

**The merge path is therefore not blocked by Supabase.** Only the
post-deployment runtime verification is.

---

## 5. Repository state — nothing at risk

Everything is committed and pushed. There is no uncommitted local work.

| | |
|---|---|
| Branch | `agent/backend-autonomy` |
| Local HEAD | `df5b6b3` |
| `origin/agent/backend-autonomy` | `df5b6b3` — **in sync** |
| `origin/dev` | `fcf9669` — unchanged, nothing merged |
| Working tree | clean |
| Commits ahead of dev | 10 |

## Configuration state to preserve across the outage

- `cron-recommendation-worker` = `0 0 29 2 *` (**PAUSED**). Restore value:
  **`15 6 * * *`**.
- Option C is **applied in the dev database**: ten routing rules have
  `fallback_model = NULL`. This survives the pause — Supabase states data was
  backed up before pausing. **To re-verify after restoration** (read-only):
  expect 10 rows NULL, and `consensus_reconciliation` /
  `probability_modeling_analysis` still `claude-sonnet-5`.
- `checkSuites` is still `false` on every GitHub-sourced dev service. The gate
  work is unaffected by this outage and still waiting on the dashboard toggles.

---

## Recovery verification plan — to run ONLY after Mac confirms payment

Read-only, in this order, with **zero provider/model calls**:

1. `list_projects` → dev `nhwjtsdebgiwskshzqiq` is `ACTIVE_HEALTHY`.
2. A trivial `select 1` to confirm connectivity.
3. Table inventory — confirm the expected tables still exist, especially
   `games`, `recommendations`, `recommendation_products`,
   `recommendation_legs`, `game_events`, `model_routing_rules`,
   `model_registry`, `game_postgame_ingestion_state`.
4. Row counts against the last known values recorded below.
5. `supabase_migrations` history — confirm nothing ran during the outage and
   nothing is partially applied.
6. Service-role connectivity via a Railway service log, not a credential change.
7. Railway services reconnect on their own next tick — no redeploy needed,
   because nothing about the services changed.
8. Confirm cron workers recover without manual data repair.
9. Confirm `cron-recommendation-worker` is **still `0 0 29 2 *`**.
10. Confirm option C is still applied (10 NULL fallbacks).

### Last known good row counts — recorded 2026-09-20/21, pre-pause

| Table | Count |
|---|---|
| `games` with `finalized_at` not null | **29** |
| `game_events` (provider `balldontlie`) | **14** |
| `recommendations` | **265** |
| `recommendation_products` | **4** |
| `recommendation_legs` | **0** |
| `recommendation_product_grade_events` | **4** |
| `recommendation_leg_grade_events` | **0** |
| `recommendation_agent_outputs` | **3** (all 2026-08-07 seed) |
| `recommendation_costs` | **3** (all 2026-08-07 seed) |
| `model_registry` (active) | **2** |
| `model_routing_rules` (active) | **12**, of which 10 now `fallback_model IS NULL` |

Anchor rows that must survive intact: CLE @ TB
`0f659b0a-c6f7-4bec-afe2-43720f7618a0`, `final_score {"away":23,"home":19}`,
`finalized_at 2026-09-20 22:31:53.329469+00`; and Week 1's 16 games still
stamped `2026-09-15 20:16:13.594649+00`.

A count *lower* than the table above would be the only genuine data-loss
signal. Counts *higher* for `games`/`game_events` are expected and fine if
finalization ticks resume before verification.
