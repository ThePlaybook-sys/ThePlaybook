# MANSA CURRENT HANDOFF

Written 2026-09-19 ~02:10 UTC. Claude is approaching its usage limit and is
stopping to hand off cleanly rather than starting new work mid-task.

## AGENT LANE

- Role: Product UI/UX Agent
- Branch: `agent/ui-ux`
- Current writer: CLAUDE → HANDING OFF TO CODEX
- Integration branch: `dev`
- May merge to dev: NO

## CURRENT VERIFIED STATE

- `agent/ui-ux` HEAD SHA: `fcf96696643c323b8fbe693deef428950e1fe9c7` — **VERIFIED** (`git rev-parse HEAD`, this pass).
- `origin/dev` HEAD SHA: `fcf96696643c323b8fbe693deef428950e1fe9c7` — **VERIFIED**, identical to `agent/ui-ux`. `git rev-list --left-right --count origin/dev...HEAD` = `0 0` (neither ahead nor behind).
- Working tree: **VERIFIED** clean — `git status --short` returned nothing before this handoff was written.
- Frontend app: **VERIFIED** present at `apps/frontend` (Next.js 14.2.35 App Router, React 18.3.1, Tailwind, `@supabase/ssr`, Vitest). 34 test files exist; they were **not executed** this pass (`node_modules` not installed, and installing/running was out of scope for a zero-implementation qualification pass).
- Phase state per `PROGRESS.md`: **VERIFIED read**, not independently re-derived. Phase 6 (Product/UI/UX Frontend) is recorded **CLOSED 2026-09-02** (HQ final gate approval). Current active phase is **Phase 7 — Market Integrity & Anomaly Intelligence**, itself gated: Milestone 7.0B is BLOCKED on a missing credential, and Milestones 7.1+ are explicitly NOT authorized. Phase 8 backend/data-ops work (odds, schedule, postgame finalization, grading) is proceeding in parallel per the `docs/ops/phase-8-*.md` files, dated up to 2026-09-18.
- **No UI/UX implementation work is in progress or was started by Claude this session.** The only work performed on `agent/ui-ux` in this session was a read-only qualification/audit pass (branch verification, frontend discovery, role/authority/data-semantics review, deployment-isolation check) — zero files were changed prior to this handoff commit.

## LAST COMPLETED WORK

- **Exact work completed:** A UI/UX agent qualification pass — repo-native audit only. No frontend/backend code, tests, schema, or config were modified.
- **Commit SHAs:** No new commits prior to this handoff. `agent/ui-ux` and `origin/dev` sit at `fcf9669` from before this session started; this handoff commit will be the first commit this session adds.
- **Migrations/config changes:** None made by this agent/lane.
- **Deployments:** None triggered by this agent/lane.
- **Tests run:** None run by this agent/lane this session (see above — `node_modules` not installed).
- **Runtime proofs obtained:** None — this was a static repo audit, no dev server was started, no browser rendering was verified.

## CURRENT LIVE SYSTEM STATE

Everything in this section is **sourced from `PROGRESS.md`'s own entries** (most recent dated 2026-09-18 21:45 UTC) — the UI/UX lane did not independently re-verify live backend/provider state this pass. Treat as PARTIAL (documented, not freshly re-checked by this agent) unless noted otherwise.

- **Schedule:** `MASTER_REFRESH_ENABLED=true` on `sports-intel-layer` (dev), `cron-schedule-refresh` (`0 9 * * *`) is live and autonomous. Canonical season is 272 games; GameKey `202610902` (CIN @ ATL) recovered. — PARTIAL (per PROGRESS.md).
- **Odds:** `cron-odds-worker` (`*/15`, dev) live. The Odds API monthly allowance 500 credits, floor 50 (trips at 450), daily ceiling `ODDS_API_MAX_CALLS_PER_DAY=20`, ramp reserve `ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP=6`. UTC monthly rollover implemented; current period `2026-09` usage ~276/500 as of the last recorded reading. — PARTIAL.
- **Recommendation eligibility / bounded LLM execution:** **Zero LLM calls have ever been made in this environment.** `recommendation_agent_outputs` holds only 3 rows, all dated 2026-08-07 (pre-dates the current gating logic). A 36-hour pre-kickoff window, a 1-game-per-tick throttle, and `MAX_LLM_CALLS_PER_GAME` are live on `ai-orchestrator` (dev), deployment `8769ffad`/commit `ecd5665`. The next natural tick that is expected to make the **first real LLM call** is scheduled for **2026-09-19 06:15 UTC** (proof game pre-computed as `CLE @ TB`, canonical id `0f659b0a-c6f7-4bec-afe2-43720f7618a0`, kickoff 2026-09-20 17:00 UTC). **Current wall clock at handoff time is 2026-09-19 ~02:01 UTC — this tick has NOT fired yet.** — PARTIAL, time-sensitive.
- **Recomputation:** "Recomputation V1" is implemented (no schema change) and blocks re-running a game that already has completed paid cycles; all 8 Sunday-17:00 games currently have 0 completed paid cycles, so none are blocked. — PARTIAL.
- **Finalization:** MySportsFeeds (MSF) postgame path is **PAUSED** (verified live via 7 consecutive natural ticks per PROGRESS.md, `paused=True`, zero HTTP calls while paused). BALLDONTLIE finalization was newly activated 2026-09-18 (`BALLDONTLIE_FINALIZATION_ENABLED=true` on `sports-intel-layer` dev) and has already produced one real, natural, non-manual finalization (DET 31 @ BUF 41, 2026-09-18 20:31 UTC), plus a clean idempotency proof on the following tick. SportsDataIO postgame path exists in code but has **no cron wired** and is unclassified/not enabled. — PARTIAL.
- **Grading:** `cron-postgame-grading` is live; the natural tick after the BALLDONTLIE finalization above picked up the newly finalized game with no manual step (17 games seen, up from 16). Zero legs/grade events exist yet because no recommendation has ever run. — PARTIAL.
- **Calibration:** Blocked on grading volume, which is itself blocked on the recommendation pipeline having never made a real LLM call. No calibration activity to report. — PARTIAL/BLOCKED.
- **Monitoring:** Sentry instrumentation is referenced throughout PROGRESS.md's Phase 8 entries (e.g. "zero Sentry events" checks on each proof step) and appears to be the standing verification method for backend autonomy proofs. — PARTIAL, not independently checked this pass.

## CURRENT PROVIDER STATE

(Enable/disable state and constraints, per `PROGRESS.md`; no values/secrets included.)

- **MySportsFeeds (MSF):** Postgame path PAUSED (verified). Schedule/roster paths are separate and were not reported as paused. Re-enabling MSF for finalization was considered and explicitly NOT taken this pass — HQ's call.
- **SportsDataIO:** Used for the daily Schedule refresh (1 call/day, active, autonomous). Its *postgame* worker exists in code but is not wired to any cron target and its quota/plan state is recorded as classification **UNKNOWN** — persisted account records conflict (a stale "11/12 Free Trial calls used" note vs. multiple successful Schedule calls since). No SportsDataIO budget/quota table exists in the schema at all.
- **BALLDONTLIE:** Newly activated for postgame finalization only (`BALLDONTLIE_FINALIZATION_ENABLED=true`, dev, `sports-intel-layer`). Free-tier `/nfl/v1/games` bulk endpoint, rate-limited at 5 requests/min (rate-only, no per-request charge). Its own cron `cron-balldontlie-finalization` runs `*/30 * * * *`. Historically also used for injuries (`InjuryAdapter`) — that usage is unaffected by this pass.
- **The Odds API:** Active, `cron-odds-worker` `*/15`. 500 credits/month Starter plan, UTC calendar-month rollover implemented, daily ceiling 20 calls (60 credits) with a 6-call/18-credit reserve for the near-kickoff ramp tier.
- **News provider (GNews):** Referenced in PROGRESS.md around a diagnosed 120s HTTP read-timeout issue; cadence/quota gating exists (`news_provider_daily_quota` table) but the fix's live confirmation was still pending a tick that actually fetches, as of the last entry reviewed.

None of the above providers are touched, reconfigured, or reactivated by this UI/UX handoff. This section is informational context only, carried from `PROGRESS.md` so Codex has situational awareness without re-reading the entire file.

## CURRENT COST / SAFETY GUARDS

(As recorded in `PROGRESS.md`; not independently re-verified by this UI/UX pass.)

- LLM call ceiling: `MAX_LLM_CALLS_PER_GAME` (value not printed here per "no secrets/no guessing" — check the live variable on `ai-orchestrator` dev directly).
- Game throttle: 1 game per recommendation-worker tick, deterministic order `scheduled_start asc, id asc`.
- Pre-kickoff eligibility window: 36 hours before kickoff before a game is admitted to the first paid recommendation cycle.
- Odds API: monthly budget 500 credits, floor 50 (fails closed at 450 used), daily ceiling 20 calls / 60 credits, 6-call/18-credit ramp reserve, UTC calendar-month rollover.
- BALLDONTLIE finalization: rate limit 5 requests/min (provider-side), worker cadence `*/30 * * * *`, `MAX_ATTEMPTS=6` on the underlying checkpoint/attempt model, single-shot claim→fetch→finalize→confirmed_complete (never re-enters retry once confirmed).
- MSF postgame: paused — zero HTTP calls of any kind while paused, verified as the literal first branch of the dispatcher.
- Circuit breaker: `CONSECUTIVE_IDENTICAL_FAILURE_LIMIT=3` observed firing correctly on a prior recommendation-worker tick under an unset sportsbook preference.

## ACTIVE CONFIGURATION

Names and current *meanings* only — no values printed.

- `MASTER_REFRESH_ENABLED` (sports-intel-layer, dev) — gates the daily canonical schedule refresh cron. Currently enabled.
- `MSF_POSTGAME_ENABLED` (sports-intel-layer, dev) — inverted gate: absent/unset means *enabled*, not paused; only an explicit falsy value pauses it. Currently unset → MSF postgame is active in principle but reported paused via a separate mechanism per PROGRESS.md — see the Finalization note above for the actual observed behavior.
- `BALLDONTLIE_FINALIZATION_ENABLED` (sports-intel-layer, dev) — gates the BALLDONTLIE finalization worker. Currently `true` (activated 2026-09-18).
- `ODDS_API_MAX_CALLS_PER_DAY`, `ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP` (sports-intel-layer, dev) — daily call ceiling and near-kickoff reserve for The Odds API.
- `THE_ODDS_API_MONTHLY_CREDIT_BUDGET`, `THE_ODDS_API_MIN_REMAINING_CREDITS` (sports-intel-layer, dev) — monthly credit ledger budget and fail-closed floor.
- `REFERENCE_SPORTSBOOK_PREFERENCE`, `MAX_LLM_CALLS_PER_GAME` (ai-orchestrator, dev) — armed for the pending 06:15 UTC recommendation-worker tick.
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (apps/frontend) — used by `middleware.ts` for SSR session refresh; anon key is public-safe by design (confirmed by its own use in `phase2-e2e.yml`'s CI, unmasked).

## CURRENT NATURAL-RUN / RUNTIME EVENTS

- **2026-09-19 06:15 UTC** — recommendation-worker's next natural tick. Expected to select `CLE @ TB` (`0f659b0a-c6f7-4bec-afe2-43720f7618a0`) as the 1-game throttle pick and make this environment's **first-ever real LLM call**. Odds freshness was pre-checked and clears the FAR-tier staleness ceiling. **Must NOT be manually forced or simulated** — it is the designated natural-event proof.
- **2026-09-19 06:45 UTC** — a scheduled observation trigger (`trig_01FqRmeKeNC2VDHaLUStdkFP`, "Final live autonomy proof STEP 1-3") fires to verify the 06:15 tick's outcome. Self-bound to a specific persistent session; PROGRESS.md flags this as unproven until it actually fires (the create call warned the trigger stores no MCP connectors).
- **2026-09-20 17:00 UTC** — eight Sunday kickoffs, including the CLE @ TB proof game.
- **2026-09-20 21:30 UTC** — scheduled observation trigger (`trig_011pixzhFkSV81UZ4BPSQ5bo`, "Sunday settlement STEP 4-5") for the post-kickoff settlement chain (finalization → grading → calibration → the "final 9-layer verdict").
- **What must be verified afterward:** that the 06:15 tick actually invoked the LLM (not skipped/paused), that exactly one game was selected, that the odds/eligibility gates behaved as pre-computed, and later, that CLE @ TB's finalize→grade chain completes naturally after Sunday's kickoff.
- **What must NOT be manually forced:** the 06:15/06:45 UTC ticks, the Sunday kickoff-triggered finalization/grading chain, or any provider call that exists solely to "prove" one of these steps ahead of its natural schedule. These are explicitly designated natural-event proofs per multiple PROGRESS.md entries.

## AUTHORIZED NEXT WORK

**AUTHORIZED NOW (UI/UX lane specifically):**
- Nothing beyond continued audit/observation. Phase 6 (the frontend phase) is CLOSED and Phase 7/8 (current active phases) are backend/data-integrity scoped, not frontend scoped. Per `CLAUDE.md`'s phase-gating rule, starting new UI/UX implementation work right now would be working ahead of the currently open phase and requires Mac's explicit authorization to do so (see the qualification pass's own K section, delivered to Mac in the prior turn of this session, which flagged exactly this).
- Read-only continuation of the UI/UX audit (Part 7/8/11 items from the qualification pass) is authorized: deeper visual-debt inventory, accessibility pass, mobile-viewport testing via a dev server — all read-only, no commits beyond documentation.

**WAITING ON NATURAL EVENT:**
- The 06:15 UTC / 06:45 UTC / Sunday 17:00 UTC / 21:30 UTC events above. Not directly UI/UX's concern, but any UI work that assumes "real" recommendation/grading data exists should wait for these to resolve naturally, since today `recommendation_legs`, `recommendation_leg_grade_events`, and `recommendation_product_grade_events` are all empty (0 rows) — any UI currently renders through its honest empty/error states, never fabricated data.

**REQUIRES MAC/HQ AUTHORIZATION:**
- Any new UI/UX implementation pass (Part 11's proposed sequence: design-system cleanup, Today/dashboard polish, recommendation card/detail work, Time Machine visual pass, onboarding, mobile responsiveness, motion/depth, accessibility, test execution).
- Reopening or adding a new frontend milestone given Phase 6 is recorded CLOSED.
- Any Supabase schema change, Railway config mutation, or provider reactivation — none of these are UI/UX's to authorize regardless of phase.

## EXPLICITLY UNAUTHORIZED

- Merge to `dev`.
- Production changes of any kind.
- New paid providers.
- Billing changes.
- Architecture expansion beyond the frontend lane.
- Cost-ceiling increases (Odds API, LLM call limits, provider budgets, etc.).
- Provider reactivation unless already authorized (MSF postgame reactivation, SportsDataIO postgame wiring — both explicitly NOT done, HQ's call to make).
- Manual forcing of any proof designated as a natural event (the 06:15/06:45 UTC ticks, Sunday settlement chain).
- Any work outside the UI/UX lane's declared scope (see Part 3B of the prior qualification pass: no sports-data providers, odds ingestion, recommendation algorithms, probability models, EV calculations, confidence/grading/calibration logic, backend cron scheduling, unauthorized schema changes, Railway infrastructure, provider billing, investor claims, or pricing strategy).

## KNOWN DEBT / NON-BLOCKERS

- Frontend `node_modules` is not installed in this session's environment — the 34 existing Vitest test files were not run this pass. This is an environment-setup gap, not a code regression.
- Per PROGRESS.md, "sports-intel-layer 1086, workers 101" test suites pass with "same 5 pre-existing wall-clock failures" — these are known, pre-existing, and explicitly called out as not a regression to fix opportunistically.
- `api-types.ts` intentionally mixes camelCase (most M2/M3/M6 routes) and verbatim snake_case (the `/reconstruction` proxy route and the raw `/user/profile` passthrough) — this is a documented, deliberate contract-fidelity choice, not an inconsistency to "clean up."
- `--team-identity` CSS token exists as an unused neutral placeholder — team identity is explicitly not authorized yet per Volume 5 §14; do not build a team-color feature against it without authorization.
- Odds credit ledger's `period_start`/`credits_used_this_period` naming is a known misnomer (it accumulates lifetime since row creation, not per-period) — already flagged and being addressed on the backend side; not a UI/UX concern but noted here so it isn't mistaken for a new bug if it surfaces in any admin/ops UI later.

## OPEN RISKS / QUESTIONS

- **Real data may start flowing mid-session for whoever picks this up.** If the 06:15 UTC tick or the Sunday settlement chain completes while Codex is working, previously-guaranteed-empty tables (`recommendation_legs`, grade events, etc.) may suddenly have real rows. Any UI/UX work should keep treating "populated" and "empty" as both must-handle states rather than assuming the current empty state persists.
- **Phase-gating ambiguity for this lane specifically:** Phase 6 (frontend) is closed, but this agent-lane initialization task implies more UI/UX work is expected soon. It is not this agent's place to decide whether that means "Phase 6 is being reopened" or "a new frontend milestone is being authorized outside strict phase order" — that determination belongs to Mac/HQ per `CLAUDE.md`'s own override clause, and should be confirmed explicitly before Codex starts any implementation, not inferred from this handoff alone.
- **`SportsDataIO` account/quota state is genuinely unknown** (per PROGRESS.md's own audit) — not a UI/UX risk directly, but if any future UI surfaces provider health/freshness (e.g. `SourceFreshnessLabel.tsx` already exists in `components/dashboard/`), be aware the underlying SportsDataIO entitlement status is itself an open question upstream.

## FILES / MODULES MOST RELEVANT TO NEXT TASK

- `apps/frontend/` — the entire frontend app (Next.js App Router).
- `apps/frontend/components/ds/` — design-system primitives (`Container`, `Surface`, `Text`, `StateBadge`) that any new UI work must build on top of, never bypass.
- `apps/frontend/app/globals.css` and `apps/frontend/tailwind.config.ts` — the single source of truth for the "MANSA Imperial Cobalt" design tokens.
- `apps/frontend/app/lib/api-types.ts` — the full frontend/backend contract surface; read before touching any data-rendering component.
- `apps/frontend/components/dashboard/`, `components/recommendations/`, `components/history/`, `components/account/`, `components/onboarding/` — the domain component folders most likely to be the next implementation targets, each with a co-located `__tests__/`.
- `docs/blueprint/volume-5-frontend-ux.md` — the frontend spec of record; read the relevant section before any UI change.
- `PROGRESS.md` — the single source of truth for phase state; read the tail (most recent entries) before starting, since it is append-only and very large (2,446 lines at last count).
- `CLAUDE.md` — the supreme project law, including the phase-gating rule this handoff flags as a real constraint on new UI/UX work.

## HOW TO VERIFY NEXT WORK

- **Tests:** `cd apps/frontend && npm install && npm test` (Vitest) for any component change; `npm run build` to confirm the Next.js production build/type-check still passes; `npm run lint`.
- **Queries:** none needed for pure UI work; if a component's data assumptions are in doubt, cross-check against `app/lib/api-types.ts` and the live backend route it names, never against a guess.
- **Logs/Sentry:** not directly UI/UX's instrumentation surface today (no frontend Sentry integration was found in this audit) — confirm with Mac/HQ before assuming otherwise.
- **Runtime evidence:** for any visual/responsive change, actually run the dev server (`npm run dev`) and check the golden path plus mobile viewport width, per this repo's own engineering norms — do not claim a UI change works without having rendered it.
- **Success criteria:** all existing tests still pass, `npm run build` succeeds, the change matches the design tokens (no hardcoded literals bypassing `--token` variables), and the change stays inside the UI/UX lane's declared scope.
- **STOP conditions:** any test failure that isn't in the known-debt list above; any temptation to touch `api-types.ts`'s field shapes to "fix" a mismatch (that's a backend contract, not UI's to change); any temptation to fabricate recommendation/performance data to fill a visual gap — use clearly labeled mock data instead, per this lane's own data-semantics rules; any Phase-gating conflict — stop and report to Mac/HQ rather than resolving it unilaterally.

## CROSS-AGENT BOUNDARIES

- `agent/backend-autonomy` — Backend/Autonomy lane. Owns the Phase 7/8 provider, cron, and recommendation-pipeline work referenced throughout this handoff's "CURRENT LIVE SYSTEM STATE" section.
- `agent/modeling` — Modeling/Intelligence lane. Owns probability models, confidence methodology, calibration, agent weighting.
- `agent/ui-ux` — this lane. Owns customer-facing UI/UX implementation only.
- `agent/qa-ops` — QA/Operations lane. Independently verifies important frontend work; this agent does not self-certify its own UI work as production-ready.

This agent must only write its assigned branch (`agent/ui-ux`). It must never write to `agent/backend-autonomy`, `agent/modeling`, or `agent/qa-ops`, and must never merge any branch into `dev` itself.

## CODEX TAKEOVER INSTRUCTION

Codex must AUDIT this handoff against the repository before making changes.
If the repository contradicts this document, repository/runtime evidence wins.
Do not silently resolve strategic, architecture, billing, or product decisions.
STOP AND REPORT when owner/HQ authority is required.
