# MANSA CURRENT HANDOFF

Written: 2026-09-19, by Claude (modeling agent), on emergency handoff to Codex
ahead of a Claude usage-limit cutoff. This is the first handoff written for
this lane — no prior authoritative handoff document existed in the repo.

## AGENT LANE

- Role: Modeling / Intelligence Agent (probability methodology, calibration,
  evidence quality, EV/confidence/risk methodology audits, adaptive-weighting
  research, leakage/hindsight prevention). See full role definition in the
  MANSA modeling-agent initialization prompt (not filed separately in-repo;
  summarized accurately in this document).
- Branch: `agent/modeling`
- Current writer: **CLAUDE → HANDING OFF TO CODEX**
- Integration branch: `dev`
- May merge to dev: **NO**

## CURRENT VERIFIED STATE

- Branch alignment: **VERIFIED**. `agent/modeling` HEAD = `origin/dev` HEAD =
  `origin/agent/modeling` HEAD, all three at `fcf96696643c323b8fbe693deef428950e1fe9c7`.
  Zero divergent commits either direction. Working tree clean, no uncommitted
  changes (before this handoff's own doc-only commit).
- Deployment isolation of this branch: **VERIFIED SAFE**. `.github/workflows/ci-cd.yml`
  triggers only on push to `dev`/`main` (+ tags) with deploy jobs further gated
  by exact-ref `if:` checks. A push to `agent/modeling` matches none of those
  triggers and runs no workflow at all.
- Deterministic pipeline (candidate generation → EV → risk → qualification →
  ranking): **VERIFIED** as deterministic code with zero LLM numeric injection,
  by direct code trace, this session.
- Modeled probability generation: **VERIFIED** as a real, wired, live LLM call
  (Probability Modeling Agent) — but **UNKNOWN/BLOCKED** as to predictive
  quality; zero calibration evidence exists yet to judge it.
- Calibration module (`app.features.calibration`): **VERIFIED** correct and
  tested (Brier, log loss, 0.05 buckets, pre-kickoff eligibility gate,
  `conclusions_justified = n>=100` product rule) but **BLOCKED** — confirmed
  by repo-wide grep to be called from no production endpoint/worker/route.
  It is real code, not yet a live capability.
- Adaptive weighting: **VERIFIED PROPOSE-ONLY-SAFE**. No code path anywhere
  writes `agents.current_weight`/`applied_weight` autonomously; the
  promotion/apply mechanism does not exist at all (not gated — unbuilt).
  Confirmed by dedicated HTTP-call-level tests.
- Real forward calibration dataset: **BLOCKED**. Does not exist in volume yet
  (see CURRENT LIVE SYSTEM STATE below).
- Historical backtest/replay tooling: **BLOCKED/absent**. Explicitly and
  repeatedly self-disclosed as nonexistent in code comments; only a Blueprint
  plan exists.
- Leakage protections: **PARTIAL**. Frozen-row append-only enforcement and the
  `predicted_at < scheduled_start` gate are real and DB-enforced. One live,
  disclosed gap remains open: cross-game "comparable pool" market/weather
  reads (`read_all_odds_snapshots`/`read_all_weather_snapshots`) have no
  point-in-time filter — safe today only because no backtest/replay path
  exists to exploit it. Must be closed before any historical evaluation work
  is authorized.

## LAST COMPLETED WORK

**This modeling-agent session (Claude, this pass):**
- A full read-only qualification/audit pass of the intelligence architecture
  (evidence pipeline, candidate generation, probability/EV/confidence/risk
  math, agent/committee architecture, calibration mechanics, leakage
  safeguards, adaptive-weighting safety, deployment isolation). Result:
  **PASS**. Zero file changes made. No commits from that pass — this handoff
  document is the first and only write this session makes.
- No provider calls, no paid LLM calls, no DB writes were made. Three
  read-only SQL `SELECT` queries were run against the **dev** Supabase
  project (`nhwjtsdebgiwskshzqiq`) to inventory row counts for the data
  section below — no INSERT/UPDATE/DDL of any kind.

**Most recent shared repo history relevant to this lane** (already on both
`dev` and `agent/modeling` since they are the same commit — not this
session's work, but the current factual state Codex will inherit):
- `fcf9669` "Check tomorrow's run before it happens, and fix a name I had
  backwards" (2026-09-18) — pre-verified the 2026-09-19 06:15 UTC
  recommendation-worker tick eligibility (8 games eligible, throttle selects
  `0f659b0a` = CLE @ TB) and corrected a home/away naming error in prior
  records. No code/config changes.
- `e5e851c` "Turn it on, and let the first real game settle itself" — set
  `BALLDONTLIE_FINALIZATION_ENABLED=true` on `sports-intel-layer` dev
  (deployment `762103d2`, SUCCESS); first natural (non-manual) live
  finalization at 2026-09-18 20:31 UTC finalized `DET 31 @ BUF 41` via a
  single BallDontLie API call; confirmed finalization→grading handoff worked
  with no manual step (game visible to grading by 21:31 UTC same day).
- `7e105b5` "Write down the foundation, the classification, and the numbers"
  — wrote up the BallDontLie classification decision and cost numbers before
  activation.
- `654fa99` "Make checkpoint state outlive the process, then finalize from
  the free feed" — migration `20260918190000_generic_postgame_checkpoint_foundation`
  (applied to dev, additive only), new `BallDontLieFinalScoreAdapter`, new
  `balldontlie_finalization_worker.py`, new cron service
  `cron-balldontlie-finalization` (dev, `*/30 * * * *`, deployment `0f93091b`
  SUCCESS). 29 new tests passing (18 worker + 11 adapter).
- `9d79af7` "Audit the postgame path, and stop twice before spending
  anything" — SportsDataIO postgame finalization audit; concluded
  SportsDataIO's 2026-season entitlement/overage-billing status is unknown
  locally; recommended not calling it yet.
- `ecd5665` "Pause the provider, bound the spend, and stop where the evidence
  runs out" — paused MySportsFeeds; armed the live recommendation proof on
  `ai-orchestrator` dev via `REFERENCE_SPORTSBOOK_PREFERENCE` and
  `MAX_LLM_CALLS_PER_GAME` env vars (deployment `8769ffad`, commit `ecd5665`,
  SUCCESS 15:47 UTC), carrying the 36h pre-kickoff eligibility gate, 1-game-
  per-tick throttle, pre-LLM eligibility reorder, and Recomputation V1.

Tests: no test suite was run by this session (audit-only, no code touched).
Per the last code-touching commits above (per PROGRESS.md, not independently
re-run this session): sports-intel-layer 1086 passing, workers 101 passing,
same 5 pre-existing wall-clock test failures as before (see KNOWN DEBT).

Runtime proofs obtained (natural, not manually forced): BallDontLie
finalization proof (single game, single API call, idempotent on re-tick,
handed off to grading with no manual step) — completed 2026-09-18.

## CURRENT LIVE SYSTEM STATE

- **Schedule**: full-season NFL schedule refresh is live (permanent master
  refresh enabled per PROGRESS.md). Dev DB currently holds 276 `games` rows;
  272 of these have a **null `season_id`** — a pre-existing data-quality gap,
  not something this session caused or fixed. Flag to Codex, do not silently
  "fix" without checking whether product/schema intends it.
- **Odds**: live via The Odds API (`odds_worker`), ~2,581 `odds_snapshots`
  rows in dev as of this audit; daily call budget tracked in
  `odds_api_daily_call_budget` / `odds_api_credit_ledger`.
- **Recommendation eligibility**: the recommendation worker is armed with a
  36-hour pre-kickoff eligibility window, a 1-game-per-tick throttle, and
  Recomputation V1 (blocks re-running a game that already had a completed
  paid cycle). As of the last natural tick check (2026-09-18 21:45 UTC
  pre-verification), **8 games are eligible for the 2026-09-19 06:15 UTC
  tick**, throttle will select exactly `CLE @ TB` (row `0f659b0a...`, kickoff
  2026-09-20 17:00 UTC), and its odds freshness already clears the FAR-tier
  staleness ceiling.
- **Bounded LLM execution**: `MAX_LLM_CALLS_PER_GAME` env var is set on
  `ai-orchestrator` dev (armed, not yet exercised by a real cycle). Circuit
  breaker `CONSECUTIVE_IDENTICAL_FAILURE_LIMIT=3` observed firing correctly
  in a prior tick (halted after 3 identical failures against 256 candidate
  rows on 2026-09-17, before the sportsbook preference was set).
- **Recomputation**: Recomputation V1 deployed and live (blocks duplicate
  paid cycles per game); not yet exercised against a real completed cycle
  because no recommendation cycle has made an LLM call yet (see below).
- **Finalization**: BallDontLie finalization worker is **ACTIVE**
  (`BALLDONTLIE_FINALIZATION_ENABLED=true`, `*/30 * * * *` cron, dev). One
  real game finalized naturally (`DET @ BUF`, 2026-09-18 20:31 UTC), byte-
  identical score copy, zero conflicts.
- **Grading**: `postgame_grading` cron confirmed live and correctly picking
  up newly-finalized games with no manual step (17 games visible as of
  2026-09-18 21:31 UTC tick, up from 16). Grading logic itself (deterministic
  `grade_leg`) is code-verified correct this session, but **zero legs have
  been graded yet** (`recommendation_leg_grade_events` = 0,
  `recommendation_product_grade_events` = 0) because no recommendation with
  a leg has completed a cycle yet.
- **Calibration**: module is correct and tested but **unwired** — no
  production caller exists. Real sample size is effectively 0
  (`recommendation_legs` = 0). `recommendation_agent_outputs` = 3 rows, **all
  dated 2026-08-07** — no recommendation cycle has ever actually made an LLM
  call as of this handoff.
- **Monitoring**: Sentry coverage confirmed present on cron/backend paths per
  `docs/ops/phase-8-backend-sentry-coverage-and-alerting-audit-2026-09-16.md`
  (not re-read in full this session — cite, don't assume beyond this).

## CURRENT PROVIDER STATE

- **MySportsFeeds (MSF)**: **PAUSED**. Deliberately, backlog-safe. Not
  re-enabled or touched by this session or the last several commits.
- **SportsDataIO**: postgame finalization worker **NOT enabled**. Its
  2026-season stats entitlement and overage-billing behavior is **UNKNOWN**
  (locally unknowable without querying the vendor directly) — this is a real
  open risk, not a solved item. Do not enable without resolving that unknown
  first.
- **BALLDONTLIE**: **ACTIVE** for postgame finalization only (`InjuryAdapter`
  role also exists separately). Free tier, rate-limited 5 req/min, **no
  per-request monetary cost**, no quota header on this endpoint. Current
  utilization is trivial (~1 request per week-finalization tick, `*/30`
  cron, realistic ceiling ~96 requests/day, ~1.3% of rate capacity).
- **The Odds API**: active for odds ingestion; budget/credit tracked in
  `odds_api_daily_call_budget` and `odds_api_credit_ledger` (monthly period
  rollover implemented per migration `20260916190000_odds_api_credit_ledger_monthly_periods.sql`).
- **NewsAPI / GNews**: active for news ingestion; quota tracked in
  `news_provider_daily_quota`.
- **OpenAI / Anthropic (LLM providers)**: both wired via hand-rolled REST
  adapters, routed by `model_registry.provider`. **Zero real LLM calls have
  been made by any recommendation cycle to date** (see above) — the
  recommendation proof is armed but has not yet fired through a real
  candidate.

## CURRENT COST / SAFETY GUARDS

- `MAX_LLM_CALLS_PER_GAME` — env var, set on `ai-orchestrator` dev (exact
  current numeric value not re-printed here per this doc's no-secrets-or-
  precise-live-values-without-verification discipline; verify current value
  via Railway `list-variables` before relying on it — do not assume the
  historical default of 48 still holds without checking).
- `CONSECUTIVE_IDENTICAL_FAILURE_LIMIT = 3` — recommendation-worker circuit
  breaker, code constant.
- 36-hour pre-kickoff eligibility window for first paid recommendation cycle
  per game (recommendation worker gate).
- 1-game-per-tick throttle on the recommendation worker.
- Recomputation V1 — blocks a second paid cycle for a game that already has
  one completed.
- `ADAPTIVE_WEIGHT_MIN_SAMPLE_SIZE = 200` (classifiable graded-leg
  observations per agent, code constant, `app.features.adaptive_weighting`).
- `ADAPTIVE_WEIGHT_MIN_WINDOW_DAYS = 90` — aborts the entire committee
  evaluation with zero reads if the window is shorter.
- `ADAPTIVE_WEIGHT_MAX_CHANGE_FRACTION = 0.10` — ±10% clamp on any proposed
  weight change, independent of the sample-size gate.
- `ADAPTIVE_WEIGHT_LEARNING_RATE = 0.25` — product-policy default per
  PROGRESS.md (Milestone 5.5).
- `MIN_SAMPLE_FOR_CALIBRATION_CONCLUSIONS = 100` — code constant in
  `app.features.calibration`, explicitly documented as a product rule, not a
  statistical proof.
- `BUCKET_WIDTH = 0.05` — calibration bucket width, code constant.
- `RECONCILIATION_WINDOW_HOURS = 72` — grading eligibility: a `final` game
  is not graded until `now >= finalized_at + 72h`.
- BallDontLie finalization: rate-limited by the provider (5 req/min),
  polling bound to `*/30 * * * *`, "claim first, fetch second" design so an
  unclaimable slate issues zero requests.
- No paid-provider call may be made by this lane without explicit
  authorization (standing rule, this initialization pass).

## ACTIVE CONFIGURATION

Names and current *meaning* only — no values printed for anything not
already stated numerically above, and no secrets of any kind:

- `REFERENCE_SPORTSBOOK_PREFERENCE` (`ai-orchestrator`) — ordered preference
  list used by `select_reference_sportsbook` to pick the one book a game's
  candidates are generated from.
- `MAX_LLM_CALLS_PER_GAME` (`ai-orchestrator`) — spend ceiling per game per
  cycle.
- `BALLDONTLIE_FINALIZATION_ENABLED` (`sports-intel-layer`) — feature flag;
  currently `true` on dev. When unset/false, the worker returns
  `status="paused"` and makes zero provider calls.
- `ADAPTIVE_WEIGHT_LEARNING_RATE` — weighting-engine tuning constant (see
  above).
- Railway environments in play: **dev** only, per this lane's authorization.
  Staging and production Supabase/Railway environments exist but were not
  touched or queried by this session beyond an initial read-only
  `list_projects` call to identify them.

## CURRENT NATURAL-RUN / RUNTIME EVENTS

- **Next expected event: 2026-09-19 06:15 UTC** — recommendation-worker cron
  tick. Expected to select exactly one game (`CLE @ TB`, row `0f659b0a...`)
  out of 8 eligible, and — for the first time ever — actually invoke the
  Probability Modeling Agent (a real, non-zero LLM call) if nothing
  upstream blocks it.
- **2026-09-19 06:45 UTC** — a scheduled Claude-side check-in trigger
  (`trig_01FqRmeKeNC2VDHaLUStdkFP`, "Final live autonomy proof STEP 1-3")
  fires to verify the 06:15 tick's outcome. This trigger belongs to a
  Claude session/routine, not to Codex — Codex should verify the same facts
  independently via DB/logs rather than relying on that trigger firing.
- **2026-09-20 ~17:00 UTC** — CLE @ TB kickoff (the game the above tick is
  expected to have generated a recommendation for, if the cycle succeeded).
- **2026-09-20 21:30 UTC** — a second scheduled Claude-side trigger
  (`trig_011pixzhFkSV81UZ4BPSQ5bo`, "Sunday settlement STEP 4-5") fires for
  the settlement chain (finalization → grading) and a final verdict on the
  end-to-end proof, ~4.5h after the Sunday 17:00 kickoffs.
- **What must be verified after 06:15 UTC**: did a real LLM call actually
  happen (check `recommendation_agent_outputs.created_at` for a row newer
  than 2026-08-07); did it produce a qualifying recommendation or a correct
  No Bet; did the circuit breaker or any guardrail fire; were there any
  Sentry events.
- **What must NOT be manually forced**: do not manually invoke the
  recommendation-worker endpoint to "test" this — the entire point of the
  armed proof is that it fires naturally on its own cron tick. Do not
  manually finalize or grade the CLE @ TB game ahead of its natural
  schedule. Do not pre-empt the 2026-09-20 21:30 UTC settlement check by
  forcing finalization/grading early.

## AUTHORIZED NEXT WORK

**AUTHORIZED NOW:**
- Continue read-only observation/verification of the natural events above
  (DB reads, log reads, Sentry checks) — no mutation.
- Close the disclosed leakage gap: add a point-in-time filter to
  `read_all_odds_snapshots`/`read_all_weather_snapshots` (or explicitly
  block their use from any future historical/replay context) — this is
  hardening existing correct-for-live code, not new architecture.
- Wire the existing, correct `app.features.calibration` module into a
  real (even read-only/internal) reporting path, once there is any real
  sample to report on.
- Any further offline modeling research (feature inventory, evidence-
  quality review of the 6 built vs. 11 unbuilt fan-out agents) that does not
  touch production code, weights, or thresholds.

**WAITING ON NATURAL EVENT:**
- Confirming the recommendation proof actually produced a real LLM call and
  a real qualifying/No-Bet decision — waits on the 2026-09-19 06:15 UTC tick.
- Confirming the full grading/calibration-eligible chain for a real
  recommendation — waits on the 2026-09-20 kickoff and its finalization/
  grading settlement.
- Any adaptive-weighting proposal work beyond code review — waits on
  `recommendation_leg_grade_events` actually accumulating graded legs (200
  per agent minimum before a proposal is even generated).

**REQUIRES MAC/HQ AUTHORIZATION:**
- Enabling SportsDataIO's postgame worker (entitlement/billing unknown).
- Any change to qualification thresholds (`confidence >= 0.55`, `EV > 0`),
  the 36h eligibility window, the 1-game throttle, or any adaptive-weighting
  guardrail constant.
- Wiring the calibration module into anything user-facing.
- Any historical backtest/replay implementation (blocked until the leakage
  gap above is closed AND authorized).
- Anything touching production or staging environments.

## EXPLICITLY UNAUTHORIZED

- Merge to `dev`.
- Any production changes.
- New paid providers.
- Billing changes.
- Architecture expansion beyond what is described above as authorized.
- Any increase to cost ceilings (`MAX_LLM_CALLS_PER_GAME`, adaptive-weighting
  sample/window/clamp constants, provider rate/budget limits).
- Reactivating MySportsFeeds or enabling SportsDataIO's postgame worker.
- Manually forcing any proof designated above as natural (recommendation
  tick, finalization, grading, or the two scheduled Claude check-in
  triggers).
- Unrelated scope (UI/UX, Railway infra config beyond what's already set,
  cron scheduling changes, auth/entitlements).

## KNOWN DEBT / NON-BLOCKERS

- 5 pre-existing wall-clock-dependent test failures in the sports-intel-layer/
  workers suites, present before this session and before the last several
  commits — not a regression, do not chase these as new bugs.
- 272 of 276 `games` rows in dev have a null `season_id` — pre-existing data
  quality gap, not caused this session.
- `historical_bet_type_variance` in `app.features.risk` is permanently
  `None` — the Blueprint's named primary risk input doesn't exist in the
  schema yet. Known gap, not a regression.
- The point-in-time resolver (`resolve_point_in_time`) is fully implemented
  and tested but wired into nothing — dead code today, low risk only because
  the dimensions it would protect (injury/lineup) are separately blocked
  from probability modeling for an unrelated reason.
- `adaptive_weight_proposals` has 30 rows in dev but
  `adaptive_weight_proposal_observations` has 0 — likely reflects that no
  live `evaluate_committee` run has actually executed against real graded
  data yet (sample-size gate blocks it); not independently root-caused this
  session, flag as an open question below rather than a confirmed bug.

## OPEN RISKS / QUESTIONS

- SportsDataIO's 2026-season stats entitlement and overage-billing behavior
  is genuinely unknown and cannot be resolved by reading the repo — needs a
  vendor-side answer before that provider is touched again.
- The `adaptive_weight_proposals` (30) vs. `_observations` (0) row-count
  mismatch in dev is unexplained — worth a quick, read-only look before
  assuming it's benign.
- The two Claude-side scheduled triggers (`trig_01FqRmeKeNC2VDHaLUStdkFP`,
  `trig_011pixzhFkSV81UZ4BPSQ5bo`) are self-bound to a specific Claude
  session/routine and were flagged at creation as possibly not carrying MCP
  connector access when they fire. Codex has no dependency on them firing
  correctly, but should not assume they will act as a safety net — verify
  the same facts independently.
- Whether the cross-game comparable-pool leakage gap (§ "LEAKAGE" above)
  needs fixing before or can wait until historical evaluation work is
  actually authorized is a judgment call for whoever picks up that work —
  flagged, not resolved, here.

## FILES / MODULES MOST RELEVANT TO NEXT TASK

- `apps/ai-orchestrator/app/features/calibration.py` — calibration ledger
  (correct, unwired).
- `apps/ai-orchestrator/app/persistence/calibration_reads.py` — read path
  for the above.
- `apps/ai-orchestrator/app/persistence/context_intelligence_reads.py` —
  `read_all_odds_snapshots`/`read_all_weather_snapshots`, the disclosed
  leakage gap.
- `apps/ai-orchestrator/app/agents/probability_modeling.py` — where the one
  real LLM-produced number (`modeled_probability`) is generated; also
  documents the leakage caveat.
- `apps/ai-orchestrator/app/features/strategy.py` — deterministic
  qualification (`qualifies`) and ranking (`rank_key`).
- `apps/ai-orchestrator/app/features/adaptive_weighting.py` and
  `apps/ai-orchestrator/app/orchestration/adaptive_weighting.py` —
  propose-only weighting engine.
- `apps/ai-orchestrator/app/orchestration/recommendation_worker.py` and
  `apps/workers/app/recommendation_worker.py` — the armed live proof this
  handoff is tracking.
- `apps/sports-intel-layer/app/workers/balldontlie_finalization_worker.py`
  — active finalization path.
- `PROGRESS.md` (repo root) — authoritative running log; read the tail for
  the most current narrative state before doing anything.

## HOW TO VERIFY NEXT WORK

- **Tests**: run the affected service's suite (`apps/ai-orchestrator`,
  `apps/sports-intel-layer`, or `apps/workers`) via `python -m pytest -q`
  from that service's directory before any push. Expect the 5 known
  wall-clock failures (see KNOWN DEBT); anything beyond that is a real
  regression.
- **Queries**: read-only `SELECT` against the **dev** Supabase project only
  (`nhwjtsdebgiwskshzqiq`) — check `recommendation_agent_outputs.created_at`
  for anything newer than 2026-08-07 (proof the recommendation cycle fired),
  `recommendation_legs`/`recommendation_leg_grade_events` row counts, and
  `game_postgame_ingestion_state`/finalization state for CLE @ TB.
- **Logs / Sentry**: check for new events on `ai-orchestrator`,
  `sports-intel-layer`, and `workers` dev services after 2026-09-19 06:15
  UTC and after the 2026-09-20 kickoffs.
- **Success criteria**: a real LLM call recorded with a timestamp after this
  handoff; a qualifying recommendation or a correctly-reasoned No Bet; no
  circuit-breaker trip on legitimate data; no Sentry errors; no duplicate
  writes on re-tick.
- **STOP conditions**: any sign of a write to `agents.current_weight`; any
  qualification/ranking threshold silently changed; any provider call beyond
  the ones named above as active; any deploy to `main`/production; any
  attempt to manually force a natural event listed above.

## CROSS-AGENT BOUNDARIES

- `agent/backend-autonomy` — backend/infra/provider/worker operations lane
  (owns the finalization/BallDontLie/MSF/SportsDataIO work referenced above
  as shared history).
- `agent/modeling` — this lane (Claude → Codex handoff).
- `agent/ui-ux` — frontend/product UI lane.
- `agent/qa-ops` — independent QA/verification lane.

This agent must only write its assigned branch, `agent/modeling`. It must
not push to, merge, or modify any other agent's branch, and must not merge
`agent/modeling` into `dev` itself.

## CODEX TAKEOVER INSTRUCTION

Codex must AUDIT this handoff against the repository before making changes.
If the repository contradicts this document, repository/runtime evidence wins.
Do not silently resolve strategic, architecture, billing, or product decisions.
STOP AND REPORT when owner/HQ authority is required.
