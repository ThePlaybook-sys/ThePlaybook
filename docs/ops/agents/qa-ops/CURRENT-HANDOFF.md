# MANSA CURRENT HANDOFF

Written: 2026-09-19, Claude (QA/Ops lane), end of session — approaching usage limit, handing off to Codex mid-lane with no implementation work started this pass.

## AGENT LANE
- Role: QA / Operations (independent verification lane)
- Branch: `agent/qa-ops`
- Current writer: CLAUDE → HANDING OFF TO CODEX
- Integration branch: `dev`
- May merge to dev: NO

## CURRENT VERIFIED STATE

- Branch alignment: **VERIFIED**. `agent/qa-ops` HEAD `fcf9669` == `origin/dev` HEAD `fcf9669`, 0 ahead / 0 behind, working tree clean.
- QA/Ops role qualification pass (independence test, authority test, status-semantics, autonomy-matrix audit, deployment isolation audit, environment contract audit, test inventory, failure-injection coverage): **VERIFIED COMPLETE**, zero file changes made during that pass, zero code/config/Railway mutations.
- CI/deploy-gate integrity: **VERIFIED BROKEN** — see "CI/Deploy-Gate Integrity" under Open Risks below. This is the single most important finding from this session and is NOT yet resolved.
- No new implementation work was authorized or started this session beyond the audit pass and this handoff document.

## LAST COMPLETED WORK

- **QA/Ops initialization/qualification audit** (read-only, this session): independently inspected branch state, GitHub Actions CI history/logs, Railway live service configs and deployment history, Sentry coverage docs, recomputation/idempotency code and tests, bounded-LLM cost-ceiling code, test inventory across all 5 apps, and cross-referenced blueprint docs (Volume 2 §9, CHANGELOG v4.1, CLAUDE.md) against live system state.
- No commits, no migrations, no config changes, no deployments were made by this agent prior to this handoff commit.
- Commit SHAs: none authored this session prior to the handoff commit below. Current HEAD `fcf96696643c323b8fbe693deef428950e1fe9c7` ("Check tomorrow's run before it happens, and fix a name I had backwards") is prior work from a different session, already on both `dev` and `agent/qa-ops`.
- Tests run: none executed directly by this agent. Test results below are read from CI job logs (GitHub Actions API, run #443, job `test-python-services (sports-intel-layer)`) and from PROGRESS.md — i.e., re-verified from primary sources, not taken on the builder's word.
- Runtime proofs obtained this session: confirmed via live Railway API that `sports-intel-layer` deploy `762103d2` (SUCCESS, 2026-09-18T20:23:50Z) matches the commit claiming the first natural BALLDONTLIE finalization (DET 31 @ BUF 41); confirmed CI has failed on 59 consecutive pushes to `dev` since 2026-09-14T13:09:28Z (last green: run #384, commit `1cde0c68`); confirmed Railway native autodeploy is live and scoped to `branch: "dev"` on 6 sampled dev services (`sports-intel-layer`, `ai-orchestrator`, `api-gateway`, `worker-scheduled`, `cron-odds-worker`, `cron-balldontlie-finalization`); confirmed `frontend` (dev) service's Railway source config has no `branch` field at all — unresolved.

## CURRENT LIVE SYSTEM STATE

| Component | Status | Note |
|---|---|---|
| Schedule | VERIFIED | Reconciliation logic + tests confirmed; 16/16 Week 1 games, no duplicate-identity failures found in code review. |
| Odds | VERIFIED | Cadence-tiered freshness confirmed (CLE@TB: 809 min old vs. 1445-min FAR-tier ceiling, checked 2026-09-18 pre-tick). Credit-guard code confirmed present in `odds_worker.py`, but **fails OPEN if its budget env vars are unset** — disclosed gap, unresolved. |
| Recommendation eligibility | VERIFIED | Pre-LLM eligibility gate tests pass; 8-game eligible-set/throttle math checked against worker logic and matches. |
| Bounded LLM execution | PARTIAL | Hard ceiling (`CallBudget`, `MAX_LLM_CALLS_PER_GAME`, default 48) is real, code-enforced, tested, fails closed. **No real paid LLM cycle has completed yet** — `recommendation_agent_outputs` still 3 rows, all dated 2026-08-07 as of last PROGRESS.md entry. Next natural attempt: 2026-09-19 06:15 UTC tick (see Natural-Run Events below). |
| Recomputation protection | PARTIAL | `test_recomputation_v1.py` (12 tests) + game-scoped (not run-scoped) eligibility keying is real and tested. Not yet proven against a live completed paid cycle. |
| Finalization | VERIFIED (with caveat) | BALLDONTLIE natural finalization of DET@BUF independently confirmed live in Railway (see above). **Caveat: this deploy bypassed the CI test gate — see Open Risks.** |
| Grading | PARTIAL | Finalization→grading handoff observed (17 games visible where 16 were before, ~1hr later, no manual step). Zero legs/grade events yet — nothing scoreable has settled. |
| Calibration | PARTIAL / BLOCKED on data | `app/features/calibration.py` (Brier, log-loss, bucketed calibration, post-event-row exclusion) exists and is tested. Explicitly disclosed by its own author commit as having zero settled predictions to compute over. |
| Monitoring | PARTIAL — downgraded from a prior PROVEN claim | FastAPI services have HTTP-unhandled-exception Sentry coverage only. Cron entry points were blind until a 2026-09-16 fix instrumented `cron_dispatch.py` (real, tested, 23 tests). Monitoring did **not** catch the CI/deploy-gate drift below — it was never designed to; that gap is real and unmonitored. |

## CURRENT PROVIDER STATE

- **MySportsFeeds (MSF):** PAUSED as of the most recent PROGRESS.md entries (`MASTER_REFRESH_ENABLED` unset → fails closed, deliberately opt-in). `MSF_POSTGAME_ENABLED` defaults to enabled when unset (deliberately inverted fail-open, documented in `run.py` docstring) — confirm current live value before assuming either state; do not flip either flag without HQ authorization.
- **SportsDataIO:** Postgame path has **no cron target wired**, **no budget/ledger variable or table at all** (confirmed gap — persisted trial-accounting records contradict each other, "11 of 12 used" vs. run history showing calls on 3 later days; neither describes current state). Treat as **unknown remaining quota** — do not make any SportsDataIO call without HQ sign-off on quota first.
- **BALLDONTLIE:** Finalization path ACTIVE (`BALLDONTLIE_FINALIZATION_ENABLED=true` on `sports-intel-layer` dev, confirmed via last builder session, deployed `762103d2`). One request per ~30-min tick, ~1 request/week for schedule-scoped weekly fetch, well inside free-tier rate limits (5/min documented from 2026-09-11 capture; no live rate-limit headers captured since — evidence gap, not a control gap).
- **The Odds API:** Active, budget-guarded via `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` / `THE_ODDS_API_MIN_REMAINING_CREDITS` env vars (confirmed present on `sports-intel-layer` dev). Guard fails CLOSED once budget − used ≤ floor, but **fails OPEN if either var is unset** — verify both are actually set before relying on this guard.
- **Anthropic (LLM):** `ANTHROPIC_API_KEY` confirmed present on `ai-orchestrator` dev. Zero real paid LLM calls made to date this season (3 rows, all 2026-08-07, predate current live-proof effort).

## CURRENT COST / SAFETY GUARDS

- `MAX_LLM_CALLS_PER_GAME` (ai-orchestrator): default 48, hard ceiling, enforced at the single outbound adapter boundary (`CallBudget.consume()`), counts spend **before** the request is sent (so a retry storm can't bypass it), refuses rather than truncates on breach.
- `RECOMMENDATION_MAX_GAMES_PER_RUN` / `RECOMMENDATION_MAX_GAMES_PER_CYCLE` (worker-scheduled): throttle confirmed present as env vars; exact current values not re-read this pass — verify live value before relying on a specific number (PROGRESS.md's most recent entry referenced 20 as the derived/recommended value, pending HQ confirmation, not yet confirmed authoritative).
- Recomputation V1: 36-hour first-paid-run window before kickoff, one completed paid cycle per canonical `game_id` (not per `run_id`/`correlation_id`), enforced twice (worker pre-check + orchestrator-side spend gate).
- Retry policy (ai-orchestrator): `max_attempts_per_model=2`, `max_total_elapsed_seconds=30.0` per request. `CircuitBreaker` is a Protocol seam with only a `NoopCircuitBreaker` implemented — deliberate, not yet needed at current traffic.
- Odds API credit guard: `THE_ODDS_API_MONTHLY_CREDIT_BUDGET` / `THE_ODDS_API_MIN_REMAINING_CREDITS`, fails closed when set, fails open when unset (verify both are set).
- SportsDataIO: **no ceiling exists at all** — no budget var, no ledger. Do not authorize any SportsDataIO call path without building this first or getting an explicit HQ waiver.

## ACTIVE CONFIGURATION

(Names and current meaning only — no secret values below, per instruction.)

- `MASTER_REFRESH_ENABLED` — opt-in, fails closed on unset/anything-but-"true" (guards paid SportsDataIO calls).
- `MSF_POSTGAME_ENABLED` — opt-out, fails OPEN (enabled) on unset — deliberately inverted from the above.
- `BALLDONTLIE_FINALIZATION_ENABLED` — opt-in gate for the BALLDONTLIE finalization worker; currently `true` on `sports-intel-layer` dev per last confirmed deploy.
- `REFERENCE_SPORTSBOOK_PREFERENCE` (ai-orchestrator) — required, raises `ConfigError` if unset (no silent guess of a sportsbook). Last recommended value in PROGRESS.md: `"draftkings,fanduel"` — confirm it was actually set before relying on candidate generation working.
- `AI_ORCHESTRATOR_URL` (workers, api-gateway) — application-owned variable name, deliberately renamed away from Railway's auto-injected `RAILWAY_SERVICE_AI_ORCHESTRATOR_URL` (bare-domain, no scheme) after that collision caused a live incident. Both names still appear in `worker-scheduled`'s variable list — confirm the code path actually reads the renamed one, not the Railway-injected one, before trusting internal HTTP calls.
- `CRON_DISPATCH_BASE_URL` / `CRON_DISPATCH_TARGET` — per-cron-service Railway variables selecting which worker endpoint a given cron job's generic dispatcher hits. `cron-weather-worker`'s value was documented missing its `https://` scheme, causing ~96 crashed deployments/day — reported, not confirmed fixed this pass.
- `SENTRY_DSN` — present on all always-on FastAPI services and now on cron services too (post 2026-09-16 fix). Verify presence, don't assume.
- `INTERNAL_SERVICE_TOKEN` — shared internal-auth token between services; present on all services checked.

## CURRENT NATURAL-RUN / RUNTIME EVENTS

- **Next event: 2026-09-19 06:15 UTC** — first natural recommendation-worker tick against the 8 Sunday-kickoff games in the 36-hour eligibility window. Deterministic ordering selects `0f659b0a` (CLE @ TB, Cleveland at Tampa Bay — home team TB, previously mis-recorded reversed in some ops notes, corrected 2026-09-18). Odds pre-checked fresh enough to clear the FAR-tier ceiling with ~636 min headroom at tick time.
- **After that:** watch for the first real LLM spend, first real `recommendation_agent_outputs` row dated after 2026-08-07, and confirm the hard ceiling (48/game) is not exceeded.
- **2026-09-20 ~21:30 UTC** (~4.5h after Sunday 17:00 UTC kickoffs): expected settlement window — finalization of Sunday games, grading handoff, and the first real calibration-eligible row (frozen pre-kickoff prediction + settled scoreable outcome) if the 06:15 recommendation tick produced a scoreable bet.
- **Two claude.ai routine triggers were armed by a prior session** for these check-ins (names/IDs referenced in PROGRESS.md's 2026-09-18 21:45 UTC entry) — **unverified this pass whether they actually fired or whether they retained their MCP connector access**; that session flagged this as a known open risk at creation time.
- **Do NOT manually force:** the 06:15 recommendation tick, the Sunday settlement chain, any cron job, or any "proof" event described above. All of these are designed to be observed naturally, not triggered.

## AUTHORIZED NEXT WORK

**AUTHORIZED NOW:**
- Read-only verification of the above natural-run events once their scheduled time has passed (query DB state, read Sentry, read Railway deploy/cron logs, read CI status).
- Resolving the `frontend` dev-service Railway branch-pinning unknown (a read-only `get-service-config` / `describe-service` check plus a check of whatever field Railway actually uses to gate autodeploy for that service type).
- Building/updating QA-only tooling, test harnesses, or reports on `agent/qa-ops`, per the standing role definition.
- Continued independent verification of the CI/deploy-gate finding below (e.g., confirming whether Railway's native autodeploy scoping matches this document's belief for the remaining ~11 services not yet sampled).

**WAITING ON NATURAL EVENT:**
- Verifying the 06:15 UTC recommendation-worker tick's actual outcome (exact game processed, exact LLM call count, ceiling not exceeded, persisted recommendation or legitimate No Bet).
- Verifying recomputation-under-live-data (does the same game re-enter paid execution on a later run).
- Verifying the Sunday settlement chain (finalization → grading → calibration) once those games complete.

**REQUIRES MAC/HQ AUTHORIZATION:**
- Any decision on the CI/deploy-gate contradiction below (re-enable Actions-gated-only deploys? accept native autodeploy as the real architecture and update the blueprint? something else?).
- Fixing or `xfail`-marking the 5 known `test_odds_cadence_persistence.py` failures.
- Building a SportsDataIO budget/ledger mechanism (currently has zero cost ceiling).
- Confirming/setting `REFERENCE_SPORTSBOOK_PREFERENCE` and `RECOMMENDATION_MAX_GAMES_PER_RUN` as authoritative live values if not already confirmed.
- Fixing `cron-weather-worker`'s missing URL scheme (reported since 2026-09-16, not confirmed fixed).

## EXPLICITLY UNAUTHORIZED

- Merge to `dev`.
- Production changes of any kind.
- New paid providers.
- Billing changes.
- Architecture expansion.
- Cost-ceiling increases.
- Provider reactivation unless already authorized (MSF master-refresh path stays paused; SportsDataIO postgame stays unwired).
- Manual forcing of any proof designated above as natural-run-only.
- Unrelated scope (product strategy, UI redesign, recommendation methodology, model-weight changes, pricing, investor claims).

## KNOWN DEBT / NON-BLOCKERS

- **5 pre-existing, unrelated failures in `apps/sports-intel-layer/tests/test_odds_cadence_persistence.py`** ("wall-clock rot"): `test_first_ever_invocation_treats_the_game_as_due`, `test_immediate_second_stateless_invocation_is_not_due`, `test_failed_provider_fetch_does_not_advance_cadence_state`, `test_unresolved_event_does_not_advance_cadence_state`, `test_all_games_recently_captured_means_zero_provider_calls_end_to_end`. Confirmed byte-identical across many passes back to 2026-09-14, and independently re-confirmed by me this session by reading the live CI job log for the current HEAD commit (`1086 passed / 5 failed`, same 5 names). **Do not treat these as new regressions.** They ARE, however, currently the reason CI shows red on every push — see Open Risks; this is a status change from "harmless disclosed debt" to "actively defeating the CI gate," even though the test failures themselves are unchanged.
- Frontend test count discrepancy: CHANGELOG references 96–114+ frontend tests passing, but only 2 files exist under `apps/frontend/__tests__/`. Not a regression — the rest almost certainly live as co-located `*.test.tsx` files elsewhere under `apps/frontend/`, not searched this pass.
- `CircuitBreaker` in ai-orchestrator is a Protocol with only a no-op implementation — deliberate placeholder, not a defect, per its own docstring (per-request retry budget already bounds damage at current traffic).

## OPEN RISKS / QUESTIONS

1. **CI/Deploy-gate integrity — the most important open item.** `docs/blueprint/volume-2-system-architecture.md` §9 and `CHANGELOG.md`'s v4.1 entry (2026-08-07) state Railway's native git-autodeploy is disabled on all three environments and the Actions-gated `railway up` step is the only deploy path. **This is currently false in practice.** Verified this session: `dev`-branch CI has failed on 59 consecutive pushes since 2026-09-14T13:09:28Z (last green: run #384, `1cde0c68`), causing `deploy-dev` to be skipped every time — yet Railway's own native git integration (confirmed live, scoped to `source.branch: "dev"`) has deployed every one of those same commits successfully and automatically, with no CI gate in the loop at all. `CLAUDE.md`'s own (more recent) wording already reflects this reality ("autodeploy is live" on dev/staging) and directly contradicts Volume 2/CHANGELOG. **This needs an HQ decision**, not a unilateral fix, per the project's own "blueprint vs. reality" escalation rule.
2. `frontend` (dev) Railway service's source config has no `branch` field returned at all, unlike every other service sampled — unconfirmed whether it's actually pinned to `dev` or defaulting to something else.
3. SportsDataIO has no cost ceiling of any kind (no budget var, no ledger table) — a real, currently-live gap, not yet a blocker only because the postgame path there is also unwired.
4. Two claude.ai routine check-in triggers armed by a prior session for the 06:15 and Sunday-settlement events — unverified whether they actually retained MCP connector access as intended.
5. `cron-weather-worker`'s missing URL scheme (reported 2026-09-16) — status unconfirmed this pass, may still be crashing on every tick.
6. Odds-API and general env-var validation is entirely reactive (httpx runtime errors), not proactive — no scheme/port validator exists anywhere in the codebase, so the same failure class (bare-domain/malformed URL) remains structurally possible for any future variable.

## FILES / MODULES MOST RELEVANT TO NEXT TASK

- `.github/workflows/ci-cd.yml` — CI gate definition; central to Open Risk #1.
- `apps/sports-intel-layer/tests/test_odds_cadence_persistence.py` — the 5 failing tests.
- `docs/blueprint/volume-2-system-architecture.md` §9 — the deploy-path architecture claim that needs reconciling with reality.
- `CHANGELOG.md` (v4.1 entry, ~2026-08-07) — the decision record that also needs reconciling.
- `CLAUDE.md` — "Railway Config Mutations" section, whose wording currently matches live reality better than Volume 2/CHANGELOG.
- `apps/workers/app/cron_dispatch.py` — generic cron dispatcher, Sentry-instrumented as of 2026-09-16.
- `apps/sports-intel-layer/app/workers/canonical_finalization.py` and `apps/sports-intel-layer/app/persistence/game_postgame_ingestion_state.py` — finalization idempotency.
- `apps/ai-orchestrator/app/models/budget.py`, `apps/ai-orchestrator/app/config.py` — bounded LLM generation.
- `apps/workers/app/persistence/games.py`, `apps/workers/app/persistence/recommendations.py`, `apps/workers/app/recommendation_worker.py` — Recomputation V1.
- `apps/ai-orchestrator/app/features/calibration.py`, `apps/sports-intel-layer/app/persistence/calibration_reads.py` — calibration ledger.
- `docs/ops/phase-8-backend-sentry-coverage-and-alerting-audit-2026-09-16.md`, `docs/ops/phase-8-recommendation-worker-autonomy-safety-gate-2026-09-17.md`, `docs/ops/phase-8-persistent-checkpoint-foundation-and-balldontlie-finalization-2026-09-18.md`, `docs/ops/phase-8-odds-worker-zero-call-audit-2026-09-16.md` — primary ops evidence trail for claims above.
- `PROGRESS.md` (tail, most recent ~150 lines as of 2026-09-18 21:45 UTC) — most recent narrative state, cross-check against runtime evidence rather than trusting at face value.

## HOW TO VERIFY NEXT WORK

- **Tests:** `python -m pytest -q` per service under `apps/{api-gateway,ai-orchestrator,sports-intel-layer,workers}`. Expect `sports-intel-layer` to show exactly the 5 known failures above — anything else is a real regression.
- **CI:** Check GitHub Actions run status for the exact commit via `mcp__github__actions_list` (`list_workflow_runs`, `list_workflow_jobs`) — do not assume from a builder's commit message; pull the job log directly (`mcp__github__get_job_logs`).
- **Deploy state:** Check Railway directly via `mcp__Railway__list-deployments` / `get-service-config` — compare the deployed commit hash against the branch HEAD, and compare against CI conclusion for that same SHA. A SUCCESS deploy does not mean CI passed; confirm both independently.
- **Queries:** `recommendation_agent_outputs` (row count/dates — expect movement past the 3 rows dated 2026-08-07 once the 06:15 tick fires), `game_postgame_ingestion_state` (finalization backlog), `odds_worker_poll_state` (freshness), calibration ledger reads via `calibration_reads.py`'s join.
- **Logs/Sentry:** Check `sports-intel-layer` and `ai-orchestrator` Sentry projects for new issues after the 06:15 tick; check cron-dispatcher-captured failures for any of the 12 known cron targets.
- **Runtime evidence:** always prefer a live Railway/Supabase/GitHub read over a PROGRESS.md narrative claim when the two could conflict — this session found a real, current conflict (Open Risk #1) by doing exactly that.
- **Success criteria for the next recommendation-tick verification:** exactly 1 canonical game processed (CLE @ TB, `0f659b0a`), LLM call count ≤ 48, no other game reached paid execution, a persisted recommendation or legitimate No Bet row exists, `predicted_at < scheduled_start`, zero unexpected Sentry events.
- **STOP conditions:** any provider call made outside a natural cron tick; any LLM call made outside the natural 06:15 tick; the 48-call ceiling exceeded; a second canonical game entering paid execution same-run; any manual forcing of a designated-natural event; any attempt to silently fix Open Risk #1 rather than escalate it.

## CROSS-AGENT BOUNDARIES

- `agent/backend-autonomy` — backend/autonomy writes.
- `agent/modeling` — modeling/intelligence writes.
- `agent/ui-ux` — product UI/UX writes.
- `agent/qa-ops` — QA/Operations writes (this lane).

This agent must only write its assigned branch (`agent/qa-ops`). QA/Ops may inspect all branches but must not modify another agent's branch. If verification requires a QA artifact, test harness, or report after authorization, it is written only on `agent/qa-ops`.

## CODEX TAKEOVER INSTRUCTION

Codex must AUDIT this handoff against the repository before making changes.
If the repository contradicts this document, repository/runtime evidence wins.
Do not silently resolve strategic, architecture, billing, or product decisions.
STOP AND REPORT when owner/HQ authority is required.
