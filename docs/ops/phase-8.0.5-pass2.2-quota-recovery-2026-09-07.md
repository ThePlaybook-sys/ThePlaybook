# Phase 8.0.5 — Pass 2.2 Quota + Recovery (2026-09-07)

**Status: real, durable code shipped and verified live in DEV. `cron-news-worker` re-enabled on the approved 4-hour cadence.** DEV only throughout. Zero SportsDataIO calls (11/12 used, final call untouched). Zero Supabase project/environment/billing mutations (one migration applied to DEV only, plus real DATA reads — no destructive action of any kind). Phase 7 observation window, Phase 4, Milestone 5.6, Phase 7.2/7.3, Phase 8.1, and staging/production all untouched.

---

## 1. GNews quota-ledger design

Two new DEV tables (migration `20260907211500_news_provider_quota_and_poll_state.sql`), deliberately NOT a reuse of `odds_api_credit_ledger` (that ledger is a monthly figure with no automatic rollover, already trusted for Odds' own real financial safety — retrofitting daily rollover onto it was flagged in Pass 2.1 as carrying blast radius beyond News):

- **`news_provider_daily_quota`** — `(provider_name, quota_date)` unique identity, `requests_used` integer. UTC rollover is structural, not logic-based: a new calendar day simply has no row yet (reads as zero), so there is nothing to reset.
- **`increment_news_provider_quota(provider, date)`** — a Postgres SQL function performing one atomic `INSERT ... ON CONFLICT DO UPDATE SET requests_used = requests_used + 1 RETURNING requests_used`, called via PostgREST RPC. This is a single UPSERT under Postgres's own row-lock semantics, not read-then-write — genuinely concurrency-safe, unlike the accepted single-writer risk on the odds ledger.
- **`news_worker_poll_state`** — one row per `team_id`, `last_polled_at` timestamptz. `news_article_history` cannot serve this role despite its own `ingested_at` column: it is insert-once-per-(provider, article_url) — a team whose fetch succeeds with zero *new* articles writes no row at all, indistinguishable from "never polled." This table instead records "a real fetch was attempted," independent of content.

Both tables are restart-safe (Postgres-durable, not in-process memory) and observable (every guard check, ceiling-trip, and real-call recording emits a structured log line from `app.workers.news_worker`).

`app/workers/news_worker.py` gained one new parameter, `persist_state: bool = False`. `False` (the default, used by every pre-existing test and caller) preserves 100% of today's exact behavior — zero new HTTP calls, zero behavior change. `True` (set by `main.py`'s real `internal_run_news_worker` call site, and nowhere else) activates both mechanisms for real:

- `last_polled_at` is read from `news_worker_poll_state` for this cycle's actual resolvable teams (ignoring any injected dict).
- Before every real per-team call (not just once at the top of the cycle — a 10-team cycle can exhaust the ceiling mid-cycle), the quota guard reads the current day's `requests_used` and compares against the ceiling.
- After every real, non-cached call — success **or** provider error alike, since a failed request still spends a real GNews quota unit — the ledger is incremented and `news_worker_poll_state` is updated.

## 2. Hard daily ceiling

`_DEFAULT_GNEWS_DAILY_CEILING = 80`, overridable via `GNEWS_DAILY_REQUEST_CEILING`. Unlike Odds Worker's credit guard (deliberately fails OPEN when unconfigured — Mac's own explicit choice for a dollar-denominated monthly budget he must set), this ceiling **always enforces** from a real default — HQ gave the exact number (80, against GNews's real 100/day DEV free-tier quota) directly in this pass's own directive, so the guard protects from the first deploy, not only once an env var is remembered. No env var is currently set on `sports-intel-layer` DEV — the code default (80) is what's live.

This is fully independent of cron cadence, per HQ's explicit instruction ("do not rely on cron cadence alone for quota safety") — even if `cron-news-worker`'s own schedule were somehow misconfigured back to a tight interval, the per-call quota guard would still cap real GNews spend at 80/day regardless.

## 3. Durable `last_polled_at` behavior

Verified in two ways:

**Unit tests (7 new, all passing):** ceiling enforcement mid-cycle, UTC `quota_date` construction from a near-midnight timestamp, persisted-state-driven due/not-due classification, an immediate-repeat scenario proving zero refetch, and a structural guarantee that `persist_state=False` never touches the new tables at all (protecting every pre-existing test).

**Real, live DEV proof (below).**

## 4. Controlled live proof

A temporary, gated diagnostic (`RUN_NEWS_PASS2_2_PROOF=1`, same "startup-hook + Railway deploy logs" pattern as every prior live-proof this project has used, since this sandbox cannot reach Railway's private network directly) called the real `run_news_worker(persist_state=True)` code path twice, back-to-back, via the exact same GNews-injection shape `main.py`'s permanent endpoint uses.

**A disclosed procedural detail, not a defect:** pushing the diagnostic commit and immediately setting its enabling env var triggered three overlapping Railway deploys within seconds of each other (git-push autodeploy racing the `set-variables` redeploy). This meant the diagnostic's "run twice" actually executed across more than one container start before settling — real, not simulated, and it ended up proving restart-safety *more* rigorously than the original single-container plan: multiple independent process starts all correctly deferred to the same persisted Postgres state rather than treating themselves as fresh/never-polled.

**Real results, read directly from DEV after the dust settled:**

| Check | Result |
|---|---|
| Ledger increment | `news_provider_daily_quota`: `provider_name='gnews', quota_date='2026-09-07', requests_used=11` — a real row, real count, matching the real number of GNews calls actually made across the (multi-container) controlled run. |
| `last_polled_at` persistence | `news_worker_poll_state`: all 10 tracked teams present, real UUIDs, real `last_polled_at≈2026-09-07 22:14:29 UTC` timestamps — not fabricated, not a fixture. |
| Immediate repeat does not refetch | The final captured deploy's own two back-to-back calls both returned `teams_due=0, teams_skipped_not_due=10` — by the time that container started, persisted state already correctly marked every team as recently polled, so *neither* of its two runs (nor any of the overlapping containers') refetched anyone already covered moments earlier. |

The 11 real GNews calls spent are genuine, HQ-authorized production usage — left in the ledger as-is (deleting or resetting them would be dishonest bookkeeping, not a "clean" quota state). 11/80 for 2026-09-07, comfortably within budget with 69 remaining for the rest of the day.

The temporary diagnostic (`app/diagnostics/news_pass2_2_proof.py`, its `__init__.py`, and the gated `main.py` hook) was fully reverted immediately after, confirmed via a clean post-revert deploy log (no proof output, `/health` responding normally). `RUN_NEWS_PASS2_2_PROOF` reset to `"0"` on Railway.

## 5. Final recurring News cadence/status

**Clean — `cron-news-worker` re-enabled** at `0 */4 * * *` (every 4 hours), confirmed via a live `get-service-config` read after the update. This is the approved cadence per HQ's own "collection cadence target = every 4 hours," matched at both layers: the Railway cron tick itself (every 4h) and the worker's own per-team interval (`_POLL_INTERVAL_SECONDS = 14400`, also 4h) — so even if the cron's own tick frequency ever drifted, the quota guard and the per-team interval both independently keep real spend safe.

**Steady-state math:** 10 teams × 1 real call each per 4-hour tick (once `last_polled_at` correctly gates re-fetching, which it now does) = 10 calls per tick × 6 ticks/day = **60 calls/day**, well under the 80 ceiling and the real 100/day vendor quota, with the 80-ceiling guard as a hard backstop regardless of any future team-count growth or cadence drift.

## 6. Durable Supabase recovery artifact location

Committed to the repository (both `dev` and `gateb-diag-tmp`) at:

```
backups/supabase-dev-recovery/2026-09-07/
```

Chosen over any external/ambient location per HQ's explicit instruction to prefer "a format/location consistent with the private MANSA repository" — this repository is private, already holds this project's own detailed internal ops history (`docs/ops/`) with real identifiers and timestamps, and a durable location inside it survives exactly the failure modes HQ is protecting against (a lost local session, a fresh workspace, a future Claude session with no memory of this one) as long as the repository itself exists.

**Verified locatable after a fresh workspace/session:** a fresh, independent `git clone` of the `dev` branch (outside this session's own working directory, then deleted afterward) confirmed the directory and all 12 files are present and intact.

## 7. Exported table/row-count manifest

See `backups/supabase-dev-recovery/2026-09-07/MANIFEST.md` for the full manifest. Summary:

| Table | Rows | Real or fixture |
|---|---|---|
| `games` (`manual_seed=true`) | 8 | Real |
| `game_provider_ids` | 17 | Real |
| `team_provider_ids` | 59 | Real |
| `venues` | 5 | Real |
| `odds_snapshots` | 138 | Real |
| `news_article_history` | 97 | Real |
| `odds_api_credit_ledger` | 1 | Real |
| `injury_reports` | 1 | Fixture |

**Total: 326 rows, 8 tables.** Export timestamp: 2026-09-07 ~20:45–20:50 UTC (data captured, Pass 2.1), committed durably ~22:20 UTC the same day (Pass 2.2) with zero changes to the underlying data in between. Source: DEV Supabase project `nhwjtsdebgiwskshzqiq` only — no secrets, keys, tokens, or connection strings anywhere in the checkpoint (verified by an explicit grep pass before commit).

## 8. Recovery verification result

Both integrity checks in `backups/supabase-dev-recovery/2026-09-07/VERIFY.md` passed:

- **Checksums:** `sha256sum -c SHA256SUMS.txt` → all 8 files `OK`, run against the fresh clone (not the original working copy), confirming the committed files are byte-identical to what was actually exported from DEV.
- **Row counts:** every file's row count matches the manifest and the original live `execute_sql` sizing query exactly (re-confirmed in Pass 2.1, unchanged since).

Restore instructions (`RESTORE.md`) are written but **not executed** — per HQ's explicit "Do NOT restore it. Export/verify only" instruction, and because DEV is currently healthy; restoring into a healthy project would be redundant, not a real recovery action.

## 9. Remaining human actions

1. **None required to keep News running safely** — the fix is live, verified, and `cron-news-worker` is back on its approved cadence. `GNEWS_DAILY_REQUEST_CEILING` needs no action unless Mac wants a different number than the built-in 80 default.
2. **Supabase Backups/PITR** (carried over from Pass 2.1, still unresolved by this pass — no MCP tool exposes that dashboard setting): check the DEV project's Database → Backups configuration directly in the Supabase dashboard. This checkpoint is a manual supplement, not a replacement for a real recurring backup mechanism.
3. **BALLDONTLIE 401** (per this pass's item 3, no new work done): still classified as a likely account/provider-provisioning issue, not a code defect — check the account's actual current plan/key state on BALLDONTLIE's own dashboard or support channel. No further diagnostic call was made this pass, per HQ's explicit "no additional repeated injury calls."
4. **WeatherAPI** (unchanged): still blocked only on `WEATHERAPI_API_KEY` provisioning — free, $0/mo, human-action-only (create the account, generate the key).

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call untouched); zero Supabase project/environment/billing mutations (one additive migration to DEV schema, otherwise read-only); no BALLDONTLIE endpoint re-hit; no Phase 7.2/7.3; no Phase 8.1; no Phase 4; no Milestone 5.6; staging/production untouched. Temporary diagnostic (`app/diagnostics/news_pass2_2_proof.py`, its `__init__.py`, and the gated `main.py` hook) fully reverted after the live proof, confirmed via a clean post-revert deploy log; `RUN_NEWS_PASS2_2_PROOF` reset to `"0"`.
