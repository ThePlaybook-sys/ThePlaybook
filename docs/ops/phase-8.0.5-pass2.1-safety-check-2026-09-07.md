# Phase 8.0.5 — Pass 2.1 Safety Check (2026-09-07)

**Status: diagnostic + protective pass, no new feature scope.** HQ directive: "Diagnose/protect what is now running." Zero SportsDataIO calls (11/12 used, final call untouched). Zero Supabase mutations of any kind (audit was strictly read-only `SELECT`/`execute_sql`). Phase 7 observation window, Phase 4, Milestone 5.6, Phase 7.2/7.3, Phase 8.1, and staging/production all untouched. One real, immediately-reversible protective action taken (§1); no code changes made this pass — every fix below is a proposal awaiting HQ's explicit sign-off, matching the directive's own "propose... fix" phrasing rather than "apply."

---

## 1. GNews daily quota — real exposure, protective action taken

**Root cause, confirmed by re-reading the real call site.** `app/main.py`'s `internal_run_news_worker()` calls `run_news_worker(...)` without passing `last_polled_at` at all. `run_news_worker`'s own default (`last_polled_at: dict | None = None` → `last_polled_at = last_polled_at or {}`) means every team's `last_polled_at.get(team_id)` is always `None`, and `_should_poll` returns `True` whenever `last_polled_at is None`. **Every team is treated as never-polled on every single cron invocation, forever** — the existing per-team 15-minute gate (`_POLL_INTERVAL_SECONDS = 900`) never actually takes effect for this call site. This is a real, previously-unnoticed defect, distinct from Pass 2's pacing fix (which only spaces out calls *within* one invocation, not *across* invocations).

**A second, deeper wrinkle surfaced by this diagnostic, not previously known:** even a correctly-wired `last_polled_at` would not fully fix this today, because `_POLL_INTERVAL_SECONDS` (900s = 15 min) exactly equals `cron-news-worker`'s own tick interval (`*/15`). Every team would still read as "due" on every single tick, since 15 minutes will have always elapsed by the next tick. Fixing the missing parameter alone is necessary but not sufficient — the per-team interval itself also needs widening.

**Real exposure, quantified from actual deploy logs (not estimated):**
- **Per invocation (today's actual behavior):** 10/10 tracked teams always read as due → 10 real GNews calls per invocation.
- **Confirmed by the one real tick that fired** (`cron-news-worker`, build `942c5326`, 2026-09-07T20:30:11Z): `teams_due=10/10`, `teams_fetched=10`, all succeeded, zero failures — real, direct proof of the 10-calls-per-tick behavior, not a projection.
- **Per hour, if left running unfixed at `*/15`:** 4 ticks × 10 calls = 40 calls/hour.
- **Per 24 hours, if left running unfixed at `*/15`:** 96 ticks × 10 calls = **960 calls/day** — **~9.6x over GNews's free-tier 100 requests/day allowance.**
- **Worst case:** identical to steady-state here, since the per-team interval and the cron interval coincide exactly — there is no "burst then settle" pattern; every tick is a full 10-call burst indefinitely.

**Protective action already taken (not merely proposed):** `cron-news-worker` (Railway service `41754758-dd90-46ed-a77b-6a3c6a931554`) had its `cronSchedule` changed from `*/15 * * * *` to `0 0 1 1 *` (fires once yearly, Jan 1st) via `mcp__Railway__update-service`, confirmed applied (`updatedFields: ["cronSchedule"]`). This is a config-only, immediately reversible parking action — not a Supabase action, not a billing action, not a code change. It directly executes HQ's own explicit instruction ("STOP recurring News safely"), given priority over the "propose a fix" instruction that follows it in the same directive.

**Actual damage caused before this action:** exactly one real tick fired (20:30:11Z), making 10 real GNews calls, all successful, zero new `news_article_history` rows (all 10 teams' articles were already-seen from a manual proof pull 8 minutes earlier, so this tick was a pure duplicate no-op content-wise). The next scheduled tick (~20:45 UTC) was prevented by the schedule change, made before that time. **Total real GNews spend from this incident: 10 calls, well within the 100/day budget on its own** — the risk was in what would have happened on the following ticks, not in what already happened.

**Recommended fix (proposed, not applied — needs HQ sign-off before any of this is built):**

Two candidate approaches were evaluated; neither is a one-line change, and both touch code adjacent to a real financial-safety mechanism, so this pass stops at the diagnostic per the directive's own scope discipline ("Do not expand scope") rather than shipping either unilaterally:

- **Option A — reuse the existing `odds_api_credit_ledger` pattern.** That module is already generic (`provider_name`-keyed, `read_credit_ledger`/`record_call`, an env-var-gated budget/floor guard that fails OPEN when unconfigured and fails CLOSED once the budget is exhausted) — the exact shape Odds Worker already trusts for its own real financial-safety guard (Phase 7). Reusing it for GNews would mean: (1) a small `_check_provider_guard`-equivalent added to `news_worker.py`, checked before each team's fetch inside the per-team loop (not just once at the top, since a 10-team cycle could exhaust budget mid-cycle); (2) `record_call(..., provider_name=news_adapter.provider_name, credits=1)` after each real, non-cached team fetch; (3) two new env vars (e.g. `NEWS_PROVIDER_DAILY_REQUEST_BUDGET`, `NEWS_PROVIDER_MIN_REMAINING_REQUESTS`), fail-open when unset, matching Odds' own "never default to an invented number" discipline. **Real gap found while designing this:** the existing ledger module has no automatic period-rollover logic — Odds' own budget is a *monthly* figure, and nothing in `record_call`/`read_credit_ledger` ever resets `period_start`/`credits_used_this_period`. Reusing it as-is for GNews's *daily* quota would work for exactly one day, then permanently block News from day 2 onward. A day-aware reset would need to be added to the shared ledger module — real code, touching a shared, already-in-production financial-safety mechanism, not something to change without HQ's explicit approval.
- **Option B — widen `_POLL_INTERVAL_SECONDS`.** A pure one-line constant change (e.g. 900 → 14400, i.e. every 4 hours per team instead of 15 minutes), safe and reversible on its own with zero schema/persistence implications. **Not sufficient by itself**, though: without also fixing the missing `last_polled_at` wiring in `main.py`, the interval value is irrelevant (every team still reads as "never polled" every tick regardless of how wide the interval is). Combined with the `last_polled_at` fix, 10 teams at a 4-hour interval would produce a steady-state ceiling of 10 × (24/4) = **60 calls/day**, safely under the 100/day budget with real margin — but this still requires deriving a real, trustworthy `last_polled_at` per team, and `news_article_history` (insert-once-per-new-article) turns out NOT to be a reliable source for that: a team whose fetch succeeds with zero *new* articles writes no history row at all, so "last row's `ingested_at`" cannot distinguish "team was just polled and had nothing new" from "team was never polled." A genuine per-team last-poll timestamp would need its own small new persisted state, which is a schema question, not a pure application-layer fix.

**Recommendation:** keep `cron-news-worker` parked (see below) until HQ picks a direction — most likely Option A (reusing the proven ledger pattern, once its day-rollover gap is closed) given it also gives a hard backstop independent of whether per-team cadence logic is ever perfectly correct, matching the directive's own point that "pacing and daily quota are separate concerns."

**Is `cron-news-worker` safely enabled right now? No — and it should not be described that way.** It is currently **parked** (`0 0 1 1 *`, effectively disabled), not "safely enabled at `*/15`." Re-enabling at `*/15` without one of the fixes above would reproduce the exact 960-calls/day exposure this pass just diagnosed.

---

## 2. BALLDONTLIE injuries — corrected diagnostic

**Pass 2's tier-based conclusion is retracted, per HQ's explicit correction.** Pass 2 concluded `player_injuries` was ALL-STAR-tier only, a different tier from the account's GOAT subscription. HQ has direct, current BALLDONTLIE documentation stating GOAT ($39.99/mo) **does** include Player Injuries, and that a trial→paid GOAT upgrade uses the same key/authentication with no integration change. **That conclusion is wrong and is withdrawn.**

**Narrow diagnostic performed this pass (no new live call spent, respecting "do not repeatedly hit the endpoint"):** a static, header-by-header comparison of our adapter's real outbound request against the official `balldontlie` PyPI package's own client code (`balldontlie/client.py`, extracted locally from unrestricted PyPI egress — the same provenance tier already used for `TheOddsApiOddsAdapter`).

| | Official `balldontlie` SDK (`_get_headers()`) | Our `BallDontLieInjuryAdapter.fetch_injuries` |
|---|---|---|
| Base URL | `https://api.balldontlie.io` | `https://api.balldontlie.io` (match) |
| Endpoint | `GET /nfl/v1/player_injuries` | `GET /nfl/v1/player_injuries` (match) |
| `Authorization` | raw key, no `Bearer` prefix | raw key, no `Bearer` prefix (match) |
| `Content-Type` | `application/json` | **absent** |
| `Accept` | `application/json` | **absent** |
| `x-bdl-client` | `python` | **absent** |

**Real finding: our adapter sends only `Authorization`, omitting 3 headers the official client always sends.** This is a genuine, previously-unnoticed discrepancy, worth closing. It is not, however, applied as a fix this pass — HQ's instruction for this item is explicitly diagnostic-only ("Perform a narrow diagnostic only"), and a header change can't be verified without a live call, which HQ separately prohibited repeating.

**Classification, per HQ's own instructed fallback logic:** the one header that actually gates authentication — `Authorization`, in the exact documented format (raw key, no `Bearer`) — already matches the official client precisely. `Content-Type`/`Accept` govern content negotiation, not authentication, and `x-bdl-client` is a client-identification tag; none of the three missing headers are a plausible cause of a 401 specifically (a 401 is an auth-layer rejection, and the auth-layer header is correct). Combined with HQ's correction that the account's actual GOAT tier does include this feature, our request substantially matches current documentation. **Per HQ's own explicit fallback rule: this is classified as a likely BALLDONTLIE account/provisioning/support-side issue** (e.g., the account's key not yet fully re-provisioned after a tier change, a trial-to-paid propagation delay, or an account-state issue on BALLDONTLIE's side) — **not a code defect** — while still flagging the 3 missing headers as a real, low-cost, low-risk-but-unverified adapter gap worth closing in a future pass once a live check is authorized.

**Is code or account/provider provisioning the likely 401 cause? Account/provider provisioning**, per the reasoning above — not this codebase's request construction.

---

## 3. Supabase safety audit

**Zero mutations of any kind this pass** — every action was a read-only `SELECT`/`execute_sql`/`list_*` call. No project, environment, or billing state was changed, paused, downgraded, deleted, moved, or recreated.

**Organization/billing topology:** org `ywghsgpylgeajjgmuuow` ("ThePlaybook-sys's Org"), plan **"pro"** — **one single org-level subscription covers all four projects below.** An org-level billing failure could plausibly affect all four environments simultaneously; there is no per-project billing isolation to rely on.

**The four projects, confirmed via `list_projects`:**
| Project ID | Name | Role | Status |
|---|---|---|---|
| `nhwjtsdebgiwskshzqiq` | ThePlaybook-sys's Project | **DEV — holds ALL real Phase 7/8 data** | ACTIVE_HEALTHY |
| `jhpjdjtvzzmhxvprsfaq` | theplaybook-staging | staging, unused by this session's work | ACTIVE_HEALTHY |
| `dronhltumzkngwwktesf` | theplaybook-production | production, unused by this session's work | ACTIVE_HEALTHY |
| `tbxzecbopoxcexggesmk` | theplaybook-demo | demo, unused by this session's work | ACTIVE_HEALTHY |

All four report Postgres 17.6.1.155.

**What's git-protected vs. what isn't, in the DEV project specifically:**
- **Schema: fully git-protected.** `list_migrations` returned 40 migrations, from `20260807210017_core_user_account_tables` through this session's own `20260907200909_venues_rls` — cross-checked and confirmed matching the local `supabase/migrations/` directory exactly. If DEV were lost, every table/column/constraint/trigger/RLS policy would come back byte-for-byte via `supabase db push`/migration replay.
- **Real DATA: NOT git-protected.** The real Phase 7/8 identity rows, captured odds lines, and news history were all inserted via raw `execute_sql`, never via `apply_migration` — no migration file recreates them. If DEV were lost, schema would return intact but this real captured data would not, unless separately backed up.

**Real-data row counts, confirmed via one read-only `execute_sql` UNION ALL query, then re-verified by counting each locally-exported file (see below) — every count matches exactly:**

| Table | Rows |
|---|---|
| `games` (manual_seed=true) | 8 |
| `game_provider_ids` | 17 |
| `team_provider_ids` | 59 |
| `venues` | 5 |
| `odds_snapshots` | 138 |
| `news_article_history` | 97 |
| `odds_api_credit_ledger` | 1 |
| `injury_reports` | 1 (fixture, not real) |

**No backup/PITR mechanism could be confirmed via available tooling this pass.** No MCP tool in this session's toolset exposes Supabase's Database → Backups/PITR configuration — that would require the Supabase dashboard UI directly, which this session cannot reach. **This is a real, open gap, not resolved by this pass** — recommend HQ check the dashboard's Backups section directly to confirm whether Point-in-Time Recovery or scheduled backups are active on the DEV project.

**Recovery checkpoint built this pass (the concrete, non-destructive action requested):** all 8 real-data tables above were exported via read-only `SELECT`/`execute_sql` calls into local JSON files, saved to this session's scratchpad (not committed to the repository, since this is real captured production-adjacent data, not source code):

```
supabase-recovery-checkpoint-2026-09-07/
  games.json                 (8 rows)
  game_provider_ids.json     (17 rows)
  team_provider_ids.json     (59 rows)
  venues.json                (5 rows)
  odds_snapshots.json        (138 rows)
  news_article_history.json  (97 rows)
  odds_api_credit_ledger.json (1 row)
  injury_reports.json        (1 row)
```

Every row count was independently re-verified against the original sizing query after export — all 8 files match exactly. This is a manual, one-time checkpoint, not a recurring/automated backup — it captures DEV's real data as of 2026-09-07 ~20:50 UTC and should be treated as a snapshot to restore *from* if needed, not a substitute for a real recurring backup mechanism.

---

## 4. Weather

**No work performed this pass, as instructed.** Weather remains blocked only on `WEATHERAPI_API_KEY` provisioning (free tier, $0/mo, already confirmed sufficient) — a human needs to create the account and generate the key; nothing else blocks it.

---

## STOP AND REPORT — the 7 items requested

1. **Actual GNews 24h request exposure:** 960 calls/day if left running unfixed at `*/15` (10 teams × 96 ticks/day, every team unconditionally due every tick) — confirmed via real deploy logs showing exactly 10/10 teams due on the one real tick that fired, not a projection. Actual damage so far: 10 real calls total, from that single tick.
2. **Whether `cron-news-worker` remains safely enabled:** **No.** It is currently parked at `0 0 1 1 *` (effectively disabled) as an immediate protective action. It should not be re-enabled at `*/15` until HQ picks and this session builds one of the two fix options in §1.
3. **Exact BALLDONTLIE injury diagnostic result:** our request's URL/method/`Authorization` format all match the official SDK exactly; 3 secondary headers (`Content-Type`, `Accept`, `x-bdl-client`) are missing but are not plausible causes of a 401 specifically.
4. **Whether code or account/provider provisioning is the likely 401 cause:** **account/provider provisioning**, not code — per HQ's own instructed fallback classification, given the auth-relevant header matches and the corrected GOAT-tier fact.
5. **Supabase environment/data-risk map:** 4 projects under 1 org, 1 shared billing plan; DEV holds 100% of this project's real Phase 7/8 data; schema is fully git-protected (40 migrations, verified matching); real captured DATA (8 tables, 326 total rows) is NOT git-protected; no backup/PITR mechanism could be confirmed via available tooling.
6. **Recommended recovery checkpoint:** built this pass — all 326 real rows across 8 tables exported to local JSON, row-counts independently re-verified. Recommend HQ additionally confirm Supabase's own Backups/PITR dashboard setting directly, since no tool in this session can check that.
7. **Immediate action HQ/user must take:** (a) decide between News quota-fix Option A (ledger reuse + new day-rollover logic) or Option B (interval widening + real per-team last-poll persistence) before `cron-news-worker` is re-enabled; (b) check the Supabase dashboard's Backups/PITR setting for the DEV project directly; (c) BALLDONTLIE: check the account's actual current plan/key state on BALLDONTLIE's own dashboard/support channel, since the likely cause is provisioning-side, not something this session can resolve further without spending the prohibited additional live call.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call untouched); zero Supabase mutations (audit strictly read-only); no billing/environment/project changes; no BALLDONTLIE endpoint re-hit; no code changes applied (News fix proposed, not built; BALLDONTLIE header fix proposed, not built); Phase 7 observation window, Phase 4, Milestone 5.6, Phase 7.2/7.3, Phase 8.1, staging/production all untouched. One real, disclosed, immediately-reversible protective action taken: `cron-news-worker`'s schedule parked to `0 0 1 1 *`.
