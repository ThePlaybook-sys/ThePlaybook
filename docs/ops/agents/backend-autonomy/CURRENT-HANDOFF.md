# MANSA CURRENT HANDOFF

**Written 2026-09-19 ~02:00 UTC by Claude (Backend/Autonomy agent), under the MANSA "EMERGENCY CLAUDE → CODEX HANDOFF" directive, approaching a usage limit.**
This is the canonical handoff for this lane. No prior handoff document existed in this repository — this file is the first, and it should be **updated in place**, not duplicated.

---

## AGENT LANE

| | |
|---|---|
| Role | **Backend / Autonomy Agent** |
| Branch | `agent/backend-autonomy` |
| Current writer | **CLAUDE → HANDING OFF TO CODEX** |
| Integration branch | `dev` |
| May merge to dev | **NO** |
| Owner / final decision-maker | Mac |
| Product & architecture authority | MANSA HQ |

At the moment of writing: `agent/backend-autonomy` HEAD == `origin/dev` == `fcf96696643c323b8fbe693deef428950e1fe9c7`, 0 ahead / 0 behind, working tree clean apart from this handoff commit.

---

## CURRENT VERIFIED STATE

| Layer | Status | Basis |
|---|---|---|
| Schedule | **VERIFIED** | `cron-schedule-refresh` `0 9 * * *` live on dev; full-season refresh executed; `master_refresh_runs` rows on 2026-09-16/17/18 |
| Odds | **VERIFIED** | `cron-odds-worker` `*/15` live; natural cycles clean; credit ledger intact |
| Recommendation eligibility | **VERIFIED** | 7-day horizon + 36h first-paid-run gate + one-paid-cycle rule all enforced *in the PostgREST query*, not in Python |
| Bounded LLM execution | **PARTIAL** | Ceiling exists at the real adapter boundary but has **never been exercised by a live call**. `recommendation_agent_outputs` = 3 rows, all dated 2026-08-07 |
| Recomputation protection | **PARTIAL** | Shipped + unit-tested. `recommendations.cycle_completed_at IS NOT NULL` count = **0**, so nothing live has exercised it |
| Finalization | **VERIFIED** | First natural live cycle 2026-09-18 20:31 UTC finalized DET 31 @ BUF 41 with **exactly 1 provider request**; idempotency proven by the 21:00 tick doing 0 work / 0 requests |
| Grading | **PARTIAL** | Handoff proven (21:31 tick saw 17 games, up from 16, including the newly finalized one, `status: graded`). But `recommendation_legs` = 0 and `recommendation_leg_grade_events` = 0 — **no real MANSA leg has ever been graded** |
| Calibration | **BLOCKED** | See *Open Risks* — the blocker is **not** a missing prediction; it is that no calibration ledger exists in the schema at all |
| Monitoring | **VERIFIED** | Sentry wired on every cron; `paused`/`success` correctly non-reportable; nested-failure census inspects payloads before trusting a status label |

---

## LAST COMPLETED WORK

Three commits, all on `dev` and mirrored to `gateb-diag-tmp`, now also the content of `agent/backend-autonomy`:

| SHA | What |
|---|---|
| `7e105b5` | Persistent checkpoint foundation + BALLDONTLIE audit (classification A) + finalization implemented **inert** |
| `e5e851c` | Activation + first natural live finalization proof |
| `fcf9669` | Pre-verification of the 06:15 recommendation tick; corrected a game-name error in the record |

Earlier same-day: `9d79af7` (SportsDataIO postgame audit → STOP, classification **B — UNKNOWN**).

**Migration applied to dev:** `supabase/migrations/20260918190000_generic_postgame_checkpoint_foundation.sql` — purely additive.
1. Unlocked `game_postgame_ingestion_state.provider_name` from a single-vendor CHECK to a closed allow-list (`mysportsfeeds`, `sportsdataio`, `balldontlie`).
2. Added `checkpoints_done text[] not null default '{}'`.
3. Added trigger `trg_game_postgame_ingestion_state_monotonic` enforcing three invariants **in the database**: checkpoint set may only grow, `attempt_count` may only grow, `confirmed_complete` may never reopen.

All six DB invariants were proven live against dev inside a transaction that deliberately raised and rolled back: `grow_checkpoints=OK`, `shrink=BLOCKED`, `reset_attempts=BLOCKED`, `reopen=BLOCKED`, `ghost_provider=BLOCKED`, `sportsdataio_allowed=OK`. Nothing persisted.

**Config change:** `BALLDONTLIE_FINALIZATION_ENABLED=true` on `sports-intel-layer` dev (deployed, not `skipDeploys`).

**Deployments:** `sports-intel-layer` `762103d2` SUCCESS 2026-09-18 20:24:09 (carries the gate). New cron service `cron-balldontlie-finalization` created, deployment `0f93091b` SUCCESS.

**Tests run:** `sports-intel-layer` **1086 passed**, `workers` **101 passed**, both with the 5 pre-existing failures listed under *Known Debt*. 29 tests were added this pass (15 checkpoint foundation, 18 finalization worker, 11 adapter — the 15 includes 5 sub-cases).

**Runtime proofs obtained (all from natural cron ticks, none manually invoked):**
- 20:02 UTC — paused transport proof: `status: paused`, `provider_requests: 0`, HTTP 200 on the correct internal URL.
- 20:31 UTC — first live finalization: 1 game considered, 1 week requested, **1 provider request**, 16 games returned, 15 `scheduled` ignored, 1 final detected, DET 31 @ BUF 41 written.
- 21:00 UTC — idempotency: 0 considered, 0 requests.
- 21:31 UTC — grading saw 17 games including the new one.

---

## CURRENT LIVE SYSTEM STATE

- **Schedule** — daily full-season SportsDataIO Schedule refresh at 09:00 UTC, 1 call/day. Writes `games.status` but **never** `final_score`/`finalized_at` (those are not in its writable field set, by design).
- **Odds** — `*/15`, adaptive tiers. FAR tier polls every 86400s; freshness ceiling for eligibility is 86400s + `ORCHESTRATION_GRACE_SECONDS` 300s = **1445 minutes**.
- **Recommendation eligibility** — `status='scheduled'` AND `scheduled_start >= now` AND `< now + 7d` AND `<= now + 36h`, ordered `scheduled_start asc, id asc`. Games with a completed paid cycle are subtracted **before** the ceiling and throttle are applied.
- **Bounded LLM execution** — `CallBudget.consume()` runs **before** delegation at `ModelAdapter.complete()`, the single outbound chokepoint. A breach raises `LlmBudgetExceededError` → HTTP 429, and is deliberately **not** a provider error so the retry engine cannot turn a breach into more spend.
- **Recomputation** — game-scoped, keyed on `recommendations.game_id` + `cycle_completed_at`, **not** on `correlation_id` (which embeds the daily `master_refresh_run` id and therefore never fires across days). Enforced twice: in `apps/workers` and again in `ai-orchestrator`.
- **Finalization** — `cron-balldontlie-finalization` `*/30`. 17 games finalized total; Week 2 has 1 (DET @ BUF). 2 BALLDONTLIE evidence rows in `game_events`; 1 `game_postgame_ingestion_state` row for provider `balldontlie`, state `confirmed_complete`, `attempt_count=1`.
- **Grading** — `cron-postgame-grading` `*/30`, candidate lookback 14 days. Runs clean, produces nothing yet because no legs exist.
- **Calibration** — no ledger exists. See *Open Risks*.
- **Monitoring** — Sentry on all crons. `_NON_ERROR_STATUSES` includes `success, completed, paused, disabled, skipped, no_eligible_run, completed_limited`. `_nested_failure_census` inspects `games`/`legs`/`products`/`items` collections **before** trusting a top-level status.

---

## CURRENT PROVIDER STATE

| Provider | State | Cost / rate constraints |
|---|---|---|
| **MySportsFeeds** | **PAUSED** — `MSF_POSTGAME_ENABLED=false` on `sports-intel-layer` dev. Verified paused over 7 natural ticks. Credentials, mappings, ingestion state, raw captures and player history all intact | Paid. **Do not reactivate without explicit HQ authorization.** Note the inverted polarity: *unset or anything other than case-insensitive `"false"` means ENABLED* |
| **SportsDataIO** | Schedule refresh **ACTIVE** (1 call/day). Postgame worker **DISABLED** — no endpoint, no dispatcher target, not cron-wired | **Quota/billing UNKNOWN (classification B).** No budget variable exists; no ledger table exists; the system has never recorded a single call. Persisted records contradict each other (trial accounting says "11/12 used", run history shows ≥4 calls since). See `docs/ops/phase-8-postgame-finalization-sportsdataio-audit-2026-09-18.md` |
| **BALLDONTLIE** | **ACTIVE for finalization** — `BALLDONTLIE_FINALIZATION_ENABLED=true` | `nfl/v1/games` is **free tier**, **rate-only**: `x-ratelimit-limit: 5` per minute. No per-request charge, no quota header. Note the ALL-STAR-tier `player_injuries` endpoint 401s with the same key — tiers are **not** cumulative |
| **The Odds API** | **ACTIVE**, `*/15` | Credit-metered with a real ledger (`odds_api_credit_ledger`, `odds_api_daily_call_budget`) and four budget variables |
| **API-SPORTS** | Not in use for this lane | Plan-gated to seasons 2022–2024 — **cannot serve the current season.** (Historical note: this restriction was once misattributed to SportsDataIO; it is API-SPORTS) |

---

## CURRENT COST / SAFETY GUARDS

| Guard | Value | Where |
|---|---|---|
| LLM calls per game | **48** | `MAX_LLM_CALLS_PER_GAME` on ai-orchestrator; `DEFAULT_MAX_LLM_CALLS_PER_GAME` in `apps/ai-orchestrator/app/config.py` |
| Games per cycle (throttle) | **1** (activation proof) | `RECOMMENDATION_MAX_GAMES_PER_CYCLE` on worker-scheduled |
| Games per run (fail-closed ceiling) | **20** | `RECOMMENDATION_MAX_GAMES_PER_RUN`; `DEFAULT_MAX_GAMES_PER_RUN` |
| Recommendation horizon | **7 days** | `RECOMMENDATION_WINDOW_DAYS` |
| First paid run window | **36 hours, inclusive** | `FIRST_PAID_RUN_WINDOW_HOURS` |
| Identical-failure circuit breaker | **3** | `CONSECUTIVE_IDENTICAL_FAILURE_LIMIT` |
| Finalization lookback | **4 days** | `LOOKBACK_DAYS` |
| First finalization check | **kickoff + 3h** | `FIRST_CHECK_AFTER_KICKOFF_HOURS` |
| Finalization backoff | **20 min** | `RETRY_BACKOFF_MINUTES` |
| Finalization attempt budget | **6**, quarantines *before* the fetch | `MAX_ATTEMPTS` |
| Grading candidate lookback | **14 days** | `GRADING_CANDIDATE_LOOKBACK_DAYS` |
| Odds freshness ceiling | **1445 min** (86400s FAR + 300s grace) | odds worker / orchestration grace |

**Critical distinction, do not collapse these:** `_PER_RUN` is a **fail-closed ceiling** — if the slate exceeds it the run refuses *everything* and reports `failed`. `_PER_CYCLE` is an **explicit throttle** — the slate is correct and a prefix is worked on purpose, reported as `completed_limited` with the deferred count. A throttled pass must never read as a whole slate.

**Finalization cost, measured:** ~10 calls per NFL week realistically, ~6 on a Sunday; absolute ceiling 96/day (48 ticks × at most 2 distinct weeks in the lookback); **1.3%** of the 7,200/day rate capacity. One bulk request covers a whole week — **never convert this into one call per game.**

---

## ACTIVE CONFIGURATION

Variable **names** only; no values, no secrets.

**`sports-intel-layer` (dev):** `MASTER_REFRESH_ENABLED` (= true), `MSF_POSTGAME_ENABLED` (= false, paused), `BALLDONTLIE_FINALIZATION_ENABLED` (= true), `ODDS_API_MAX_CALLS_PER_DAY`, `ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`, `THE_ODDS_API_MONTHLY_CREDIT_BUDGET`, `THE_ODDS_API_MIN_REMAINING_CREDITS`, `SPORTSDATAIO_API_KEY`, `BALLDONTLIE_API_KEY`, `MYSPORTSFEEDS_API_KEY`, `THE_ODDS_API_KEY`, `WEATHERAPI_API_KEY`, `GNEWS_API_KEY`, `API_SPORTS_NFL_KEY`, `SENTRY_DSN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_SERVICE_TOKEN`, plus many one-shot `RUN_*` diagnostic flags (all should be `0`/off).

**`ai-orchestrator` (dev):** `REFERENCE_SPORTSBOOK_PREFERENCE` (= `draftkings,fanduel`), `MAX_LLM_CALLS_PER_GAME` (= 48), `ANTHROPIC_API_KEY`, `SENTRY_DSN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_SERVICE_TOKEN`.

**`worker-scheduled` (dev):** `RECOMMENDATION_MAX_GAMES_PER_CYCLE` (= 1), `RECOMMENDATION_MAX_GAMES_PER_RUN` (= 20), `AI_ORCHESTRATOR_URL`, `INTERNAL_SERVICE_TOKEN`, `SENTRY_DSN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.

**Each cron service:** `CRON_DISPATCH_TARGET`, `CRON_DISPATCH_BASE_URL`, `INTERNAL_SERVICE_TOKEN`, `SENTRY_DSN`.

### Two config traps that have already cost this project time

1. **`CRON_DISPATCH_BASE_URL` must carry its scheme and port** — `http://<service>.railway.internal:8080`. `cron_dispatch` does `f"{base_url}{path}"` and adds nothing. A bare domain had `cron-weather-worker` crashing every 15 minutes, unseen.
2. **Railway auto-injects `RAILWAY_SERVICE_<NAME>_URL` on every service, as a bare domain with no scheme, and an explicitly-set variable of the same name does NOT override it.** This was proven live. That is why `worker-scheduled` reads the application-owned `AI_ORCHESTRATOR_URL` instead. A stale `RAILWAY_SERVICE_AI_ORCHESTRATOR_URL` is still present and is deliberately left alone.

**Railway rule:** pass `skipDeploys: true` on every config/variable mutation **unless a deploy is the explicit point of the call** (see root `CLAUDE.md`). The 2026-08-07 production outage came from a routine `set-variables` silently redeploying 5 services from a stale snapshot.

---

## CURRENT NATURAL-RUN / RUNTIME EVENTS

| When (UTC) | Event | Must NOT be forced |
|---|---|---|
| **2026-09-19 06:15** | `cron-recommendation-worker` (`15 6 * * *`) — the first live paid cycle | **Do not manually invoke.** |
| **2026-09-19 06:45** | Check-in routine `trig_01FqRmeKeNC2VDHaLUStdkFP` fires into the Claude session | — |
| **2026-09-20 17:00** | Sunday kickoffs | — |
| **2026-09-20 ~20:30+** | `cron-balldontlie-finalization` settles them naturally | **Do not manually invoke.** |
| **2026-09-20 21:30** | Check-in routine `trig_011pixzhFkSV81UZ4BPSQ5bo` for settlement + final verdict | — |

**Pre-verified for the 06:15 tick (zero cost, 2026-09-18 21:41 UTC):** 8 games eligible (all eight Sunday 17:00 kickoffs, 34h45m out), all with 0 completed paid cycles. Deterministic order selects `0f659b0a-c6f7-4bec-afe2-43720f7618a0` = **CLE @ TB** (Cleveland at Tampa Bay, home team TB), kickoff 2026-09-20 17:00 UTC. Its DraftKings/FanDuel odds will be **809 minutes old** at the tick against the **1445-minute** ceiling — inside, with no overnight refresh needed.

*(An earlier record called this game "TB @ CLE" with the teams reversed. CLE @ TB is correct.)*

**After the 06:15 tick, verify:** exactly 1 game reached the LLM; actual outbound calls ≤ 48; reference sportsbook resolved; prediction timestamp < kickoff; probability/EV/risk persisted; a recommendation **or a legitimate No Bet** (both are successes); no other game reached the LLM; no unexpected Sentry error.

---

## AUTHORIZED NEXT WORK

### AUTHORIZED NOW
- Nothing implementation-shaped. This lane is between authorized tasks.
- Read-only audit, verification and reporting is always in scope.

### WAITING ON NATURAL EVENT
1. Observe the 06:15 UTC recommendation tick and verify the list above.
2. If it passes → live Recomputation V1 proof (same game must not re-run on a new `master_refresh_run`).
3. If that passes → the already-authorized **3-game expansion**: set `RECOMMENDATION_MAX_GAMES_PER_CYCLE=3` on `worker-scheduled` dev, keep `_PER_RUN=20`, observe **one** natural cycle, ceiling ≤ 3×48 = 144. Expect **fewer than 3** games if CLE @ TB is already completed — that is correct, not a failure.
4. Sunday settlement: finalization → grading → grade event.

### REQUIRES MAC / HQ AUTHORIZATION
- Any expansion beyond 3 games toward the full slate.
- Building a calibration ledger (see *Open Risks* — this is an architecture decision).
- SportsDataIO postgame activation — blocked on plan/tier, allowance, 2026 entitlement for `TeamGameStats` + `PlayerGameStatsByWeek`, **overage behaviour (billed vs refused)**, and current usage. None of it is knowable from inside this repo.
- Reactivating MySportsFeeds.
- Repairing or deleting `cron-master-refresh` (stale branch, CRASHED, reported repeatedly, never authorized).
- Any production or staging change.

---

## EXPLICITLY UNAUTHORIZED

- Merging to `dev`, or opening a PR, without explicit authorization.
- Any production environment change.
- Adding a new paid provider, or increasing any paid provider's cadence.
- Billing changes of any kind.
- Architecture expansion beyond the authorized task.
- Raising any cost ceiling because a run wants more — that is a **finding to report**, never a fix.
- Reactivating a paused provider (MSF) unless separately authorized.
- Manually forcing any proof designated as natural (the 06:15 tick, the Sunday settlement).
- Weakening a safety gate — freshness, eligibility, ceiling, throttle — to make a proof pass.
- Changing scoring / probability / EV semantics.
- Unrelated scope, however tempting the adjacent defect.

---

## KNOWN DEBT / NON-BLOCKERS

**Do not mistake these for regressions Codex introduced.**

1. **5 pre-existing test failures**, all in `apps/sports-intel-layer/tests/test_odds_cadence_persistence.py` — wall-clock rot, present for many passes, never in scope: `test_first_ever_invocation_treats_the_game_as_due`, `test_immediate_second_stateless_invocation_is_not_due`, `test_failed_provider_fetch_does_not_advance_cadence_state`, `test_unresolved_event_does_not_advance_cadence_state`, `test_all_games_recently_captured_means_zero_provider_calls_end_to_end`.
2. **`cron-master-refresh`** — stale branch `claude/new-session-fqsad5`, CRASHED since 2026-09-16, no cron schedule. Reported, never authorized for repair.
3. **`apps/sports-intel-layer/app/workers/postgame_worker.py`** (SportsDataIO) still holds checkpoint state in a process-local dict. HQ said do not enable it. The persistence foundation it would need now exists, but the worker was not rewired.
4. **`update_final_score`** is unguarded and re-copies on every checkpoint (idempotent in value, costly in calls). Only matters if the SportsDataIO path is ever enabled.
5. **Finalization evidence envelope does not capture response headers**, so there is no live `x-ratelimit-remaining` per call. The 5/min figure comes from the 2026-09-11 capture that did record them.
6. **`checkpoints_done` is `[]` on the BALLDONTLIE state row** — correct, not a miss. That path is single-shot and never enters the 6-checkpoint corrections schedule.
7. **Player Props / Pregame workers** remain unwired (Phase 3E debt, recorded in `PROGRESS.md`).
8. **`finalized_at` is stamped from our clock at detection**, i.e. "when we noticed", not "when the game ended".

---

## OPEN RISKS / QUESTIONS

1. **No calibration ledger exists — this is the real calibration blocker.** Audited all 84 tables and every column in dev: there is **no calibration ledger table**, and **`calibration_exclusion_reason`, `modeled_probability` and `predicted_at` do not exist as columns anywhere**. The nearest real equivalents are `recommendations.created_at` (a sound proxy for predicted_at — the row is created at cycle start), `recommendations.confidence_score`/`expected_value`, and `recommendation_legs.final_aggregate_confidence`/`ev_per_dollar`. What *is* genuinely frozen: `recommendation_legs` holds `candidate_key`, `market_type`, `selection`, `sportsbook`, `american_odds`, `decimal_odds`, `point`, `consensus_snapshot_id`; and `recommendation_leg_grade_events` holds `outcome` + `authoritative_result`, so **WIN/LOSS/PUSH/VOID is satisfiable today**. **Consequence: the Sunday settlement can prove the chain as far as the grade event and no further.** This looks like a planned-but-unbuilt Volume 4 component rather than a defect — but it is HQ's call and must not be improvised.
2. **SportsDataIO quota/billing remains UNKNOWN.** The single most important unanswered question is whether overage is **billed or refused** — that is the difference between a bounded mistake and an invoice.
3. **Deployment isolation of agent branches is by absence, not by rule.** No service watches `agent/*` today, and `ci-cd.yml` is gated twice (`on.push.branches: [dev, main]`, plus `if: github.ref == 'refs/heads/dev'`). But nothing structurally prevents a service being pointed at an agent branch later — and `cron-master-refresh` proves drift onto a non-`dev` branch has already happened here once.
4. **The scheduled check-in routines store no MCP connectors.** Both are self-bound to the Claude session that holds them, so it is expected to be moot — unproven until the 06:45 firing. If a fired session lands without connector tools, recreate the routine from the claude.ai routines UI.

---

## FILES / MODULES MOST RELEVANT TO NEXT TASK

**Recommendation path**
- `apps/workers/app/recommendation_worker.py` — throttle, ceiling, failure signature, result statuses
- `apps/workers/app/persistence/games.py` — eligibility query, `RECOMMENDATION_WINDOW_DAYS`, `FIRST_PAID_RUN_WINDOW_HOURS`
- `apps/workers/app/persistence/recommendations.py` — completed-paid-cycle read
- `apps/workers/app/cron_dispatch.py` — `_TARGET_PATHS`, `_NON_ERROR_STATUSES`, `_nested_failure_census`
- `apps/ai-orchestrator/app/orchestration/recommendation_worker.py` — pre-LLM eligibility gate ordering
- `apps/ai-orchestrator/app/models/budget.py` — `CallBudget`, `BudgetedModelAdapter`, `LlmBudgetExceededError`
- `apps/ai-orchestrator/app/config.py` — `max_llm_calls_per_game()`
- `apps/ai-orchestrator/app/persistence/recommendations.py` — `read_completed_paid_cycle_for_game`

**Finalization path**
- `apps/sports-intel-layer/app/workers/balldontlie_finalization_worker.py`
- `apps/sports-intel-layer/app/adapters/providers/balldontlie.py` — `BallDontLieFinalScoreAdapter`
- `apps/sports-intel-layer/app/adapters/models.py` — `FinalScoreLine`
- `apps/sports-intel-layer/app/persistence/game_postgame_ingestion_state.py` — generic checkpoint/claim layer
- `apps/sports-intel-layer/app/persistence/games.py` — `finalize_game` (atomic + idempotent)
- `apps/sports-intel-layer/app/persistence/game_events.py` — `write_raw_game_events`
- `supabase/migrations/20260918190000_generic_postgame_checkpoint_foundation.sql`

**Tests**
- `apps/sports-intel-layer/tests/test_persistent_checkpoint_foundation.py`
- `apps/sports-intel-layer/tests/test_balldontlie_finalization_worker.py`
- `apps/sports-intel-layer/tests/adapters/test_balldontlie_final_score_adapter.py`
- `apps/workers/tests/test_recomputation_v1.py`, `apps/workers/tests/conftest.py`
- `apps/ai-orchestrator/tests/test_pre_llm_eligibility_gate.py`

**Context**
- `PROGRESS.md` (append-only build log — the real running history)
- `docs/ops/phase-8-postgame-finalization-sportsdataio-audit-2026-09-18.md`
- `docs/ops/phase-8-persistent-checkpoint-foundation-and-balldontlie-finalization-2026-09-18.md` (incl. the live-proof addendum)
- `docs/blueprint/` volumes 1–5 + `engineering-roadmap-build-order.md`
- root `CLAUDE.md` — phase gating, testing discipline, Railway `skipDeploys` rule

---

## HOW TO VERIFY NEXT WORK

**Tests**
```bash
cd apps/sports-intel-layer && python -m pytest -q   # expect 1086 passed + the 5 known failures
cd apps/workers            && python -m pytest -q   # expect 101 passed
cd apps/ai-orchestrator    && python -m pytest -q   # expect ~1000 passed
```

**Queries** (dev Supabase project `nhwjtsdebgiwskshzqiq`)
- LLM ever called: `select count(*), max(created_at) from recommendation_agent_outputs;` — **3 / 2026-08-07** means still never.
- Paid cycles: `select count(*) from recommendations where cycle_completed_at is not null;`
- Legs & grades: `select count(*) from recommendation_legs;` / `recommendation_leg_grade_events`
- Finalization: `select id, final_score, finalized_at, status from games where finalized_at is not null order by finalized_at desc;`
- Week 1 must stay untouched: all 16 stamped `2026-09-15 20:16:13.594649+00`.
- Checkpoint state: `select * from game_postgame_ingestion_state where provider_name='balldontlie';`

**Logs** — Railway deploy logs per cron service. The line that matters is `cron_dispatch succeeded target=<t> result={...}`; read the result dict, not the status word. Railway tags Python INFO logs as `severity: error` — that is a stderr artifact on every cron in this repo, **not** a failure.

**Sentry** — a clean run must be silent. An event on a `success`/`completed`/`paused` status means `_nested_failure_census` found real per-item failures inside the payload; investigate rather than suppress.

**Success criteria for the next authorized task (3-game expansion):** ≤3 games reached the LLM; ≤144 real outbound requests; each game independently passed the deterministic pre-LLM gate; deferred games untouched and unmarked; skipped games cost 0; all predictions pre-kickoff; No Bet permitted; Sentry quiet; persistence isolated per game/candidate; and **CLE @ TB was not re-run**.

**STOP conditions** — stop and report immediately on: more games reaching the LLM than authorized; exceeding the ceiling; an unexpected `LlmBudgetExceededError`; a prediction timestamped after kickoff; stale or missing odds reaching the LLM; unresolved sportsbook identity reaching the LLM; an `in_progress` game treated as final; a duplicate finalization; a checkpoint regression or reopen; scores conflicting between authoritative sources; ambiguous identity; unbounded retries; provider usage multiplying unexpectedly; or any Sentry operational failure. **Never repair a STOP by weakening the gate that caught it.**

---

## CROSS-AGENT BOUNDARIES

| Branch | Lane |
|---|---|
| `agent/backend-autonomy` | **This agent.** Backend & autonomy: schedule, odds, recommendation orchestration, ai-orchestrator execution, provider safety gates, LLM ceilings, recomputation, finalization, grading transport, cron reliability, retry/backoff/idempotency, observability, runtime proof |
| `agent/modeling` | Modeling / Intelligence — probability methodology, research |
| `agent/ui-ux` | Product UI/UX |
| `agent/qa-ops` | QA / Operations — independent verification |

**This agent must only write its assigned branch: `agent/backend-autonomy`.** One coding agent writes a branch at a time; Claude and Codex must never write the same branch concurrently. GitHub commits and this document are the source-of-truth bridge between agents. QA/Ops should independently verify major builder work, and **this agent must not self-certify important runtime behaviour solely from its own implementation** — which is why every claim above rests on a natural cron tick or a database read, not on tests passing.

---

Codex must AUDIT this handoff against the repository before making changes.
If the repository contradicts this document, repository/runtime evidence wins.
Do not silently resolve strategic, architecture, billing, or product decisions.
STOP AND REPORT when owner/HQ authority is required.

---

# ADDENDUM — STEP 1 / STEP 2 OBSERVED (written 2026-09-20 ~20:20 UTC)

A scheduled check-in fired at 2026-09-19 06:45 UTC carrying the older "FINAL LIVE AUTONOMY PROOF" prompt. The session was then idle ~37 hours, so this addendum covers **two** natural recommendation ticks (09-19 and 09-20), observed after the fact.

**Two of that older prompt's instructions were deliberately NOT followed, because newer owner directives supersede them:**
- Its STEP 3 sets a Railway variable. That is implementation/config work, and the EMERGENCY HANDOFF directive authorizes documentation only. **Not done.**
- It says "commit to dev, mirror to gateb-diag-tmp". This lane may write **only** `agent/backend-autonomy` and may never merge to `dev`. **Not done.**

Everything below is read-only observation. No cron was forced, no endpoint invoked, no variable set, no code changed.

## STEP 1 — OUTCOME: **No Bet on both games**, with a provenance anomaly that is a STOP condition

| Tick | Game | Product | Type | Status |
|---|---|---|---|---|
| 2026-09-19 06:19 | **CLE @ TB** | `2026-00001` | `no_bet` (game scope) | active |
| 2026-09-19 06:19 | slate | `2026-00002` | `bankroll_preservation` | active |
| 2026-09-20 06:19 | **CIN @ HOU** | `2026-00003` | `no_bet` (game scope) | active |
| 2026-09-20 06:19 | slate | `2026-00004` | `bankroll_preservation` | active |

The **1-game throttle held on both days**, and the deterministic ordering advanced correctly.

### THE ANOMALY — a No Bet was produced with ZERO LLM calls

| Evidence | Value |
|---|---|
| `recommendation_agent_outputs` | **3 rows, all dated 2026-08-07** — unchanged |
| `recommendation_costs` | 3 rows, latest **2026-08-07** |
| `consensus_snapshots` | 1 row, **2026-08-07** |
| `recommendation_legs` | **0** |
| `recommendations` substance | `status`, `recommendation_type`, `confidence_score`, `expected_value`, `risk_level` **all NULL** on both rows |

`apps/ai-orchestrator/app/orchestration/recommendation_worker.py` places the 6-agent fan-out **before** candidate evaluation, and `mark_recommendation_cycle_completed` is reached **only after** it. So the committee *was* invoked — and left no agent output, no cost row and no consensus snapshot behind.

**Reading: the fan-out ran, every agent failed before reaching a provider, and the No Bet was then produced on empty evidence.** Same signature as the 2026-09-17 257-game incident. This is unconfirmed by logs — Railway log access required an approval this session could not obtain — so it is stated as the reading the persisted evidence supports, not as a proven root cause. **Confirming it from the ai-orchestrator logs for 2026-09-19 06:19 and 2026-09-20 06:19 UTC is the first thing the next writer should do.**

**Why this is a STOP condition rather than a success:** a No Bet reached *without any intelligence* is indistinguishable in the database from a reasoned one — same `recommendation_type`, same `active` status, same shape. And Recomputation V1 has now **permanently consumed both games**: `cycle_completed_at` is set, so neither will ever be paid for again. Two real fixtures were spent producing nothing.

### Secondary defect (code, unfixed)

`mark_recommendation_cycle_completed(..., completed_at_iso=now.isoformat())` passes the `now` captured at **cycle start**, not at completion. Hence `cycle_completed_at` = `06:19:40.500` sits **1.8 s earlier than** `created_at` = `06:19:42.295` on the CLE @ TB row. A column named "completed" holding the start instant is misleading provenance, and it will quietly distort any latency or ordering analysis built on it later. Small, real, and not mine to fix without authorization.

## STEP 2 — RECOMPUTATION V1: **PROVEN LIVE** (incidentally, and cleanly)

On 2026-09-20 the worker selected **CIN @ HOU, not CLE @ TB**, under a **different** `master_refresh_run_id` (`49e65ca9-36d6-4392-9d8b-c5008fd93a85` vs the previous day's `ac70e97f-8d73-414c-9169-7e5bbcd174b3`). A new daily refresh run did **not** reopen a game that had already completed a paid cycle, and CLE @ TB received no second recommendation row.

That is exactly the rule HQ specified, observed across two real days rather than asserted from tests. **Recomputation protection: PARTIAL → PROVEN.**

## FINALIZATION — still healthy, and working right now

Sunday's slate is settling naturally as observed at 20:16 UTC: **PIT 3 @ NE 20** and **NO 24 @ BAL 17** both finalized at `2026-09-20 20:00:50`. The other 17:00 kickoffs remain `scheduled` because BALLDONTLIE had not yet marked them terminal — the `not_final_yet` branch behaving correctly rather than guessing. **CLE @ TB was still unfinalized at 20:16**; the 21:30 settlement check-in should find it done.

## UPDATED MATRIX

| Layer | Status | Change |
|---|---|---|
| Schedule | VERIFIED | — |
| Odds | VERIFIED | — |
| Recommendation eligibility | VERIFIED | Throttle + ordering + 36h window all held over two live days |
| Bounded LLM execution | **BLOCKED** | Was PARTIAL. Two paid cycles completed with **zero** LLM calls and no agent provenance |
| Recomputation protection | **PROVEN** | Was PARTIAL. Live-proven across two days and two refresh runs |
| Finalization | VERIFIED | Still clean on the live Sunday slate |
| Grading | PARTIAL | `recommendation_legs` still 0 — a No Bet creates no leg, so there is still nothing to grade |
| Calibration | BLOCKED | Unchanged: no calibration ledger exists (see Open Risks) |
| Monitoring | **QUESTIONED** | Whether Sentry fired for the agent failures is **unverified** — log access was unavailable. If it did not, that is a second instrumentation gap of the same class as 2026-09-17 |

## WHAT THE NEXT WRITER SHOULD DO FIRST

1. **Read the ai-orchestrator logs** for 2026-09-19 06:19 and 2026-09-20 06:19 UTC. Confirm or refute "every agent failed before reaching a provider", and capture the actual exception.
2. **Check whether Sentry fired** for those two runs. A total committee failure wearing a `no_bet` product is precisely the silent-failure class the nested failure census was built to catch.
3. **Do NOT expand to 3 games** until the committee is proven to actually execute. Expanding now would consume three more fixtures per day the same way.
4. **Raise with HQ**: two fixtures have been permanently consumed by Recomputation V1 while producing no intelligence. Whether to clear `cycle_completed_at` on those two rows is an **owner decision**, not a repair to make quietly — it is the one lever that would let those games be re-evaluated, and it deliberately weakens a safety rule.

---

# ADDENDUM 2 — SUNDAY RECOVERY / CURRENT-STATE RECONCILIATION (2026-09-20 20:27 UTC)

Audit-only control-tower pass while Mac was away. Nothing forced, nothing configured, no provider or LLM call, no merge, no code changed.

## TWO CORRECTIONS TO THIS DOCUMENT'S EARLIER CLAIMS

1. **"Exact LLM calls: zero" was an over-claim.** There is **no persisted outbound-request counter anywhere**: `CallBudget` is in-memory only, and **nothing in production writes `recommendation_costs`**. The exact count is **UNKNOWN**, permanently, for any run. Only this is verifiable: no agent outputs, consensus snapshots or cost rows were persisted.
2. **"No calibration ledger exists / `calibration_exclusion_reason` does not exist anywhere" was too broad.** True of the *database*; false of the *system*. `apps/ai-orchestrator/app/features/calibration.py` (`SettledPrediction`, Brier, log-loss, bucketing) and `app/persistence/calibration_reads.py::read_settled_predictions` both exist and are tested, with `calibration_exclusion_reason` as a dataclass field. **`read_settled_predictions` has zero production callers** — real code, not a live capability.

## SATURDAY + SUNDAY RUNS

| Fact | Finding |
|---|---|
| 09-19 06:19:42 cron ran, selected CLE @ TB (`0f659b0a…`) | VERIFIED |
| Passed horizon / 36h / freshness / sportsbook / candidates | INFERRED (strong) — empty candidates create no row at all |
| Result | **Legitimate No Bet**, product `2026-00001` active + slate `2026-00002` |
| Real LLM call | **UNKNOWN** — no persisted counter |
| 48-ceiling | INFERRED intact — a breach raises and fails the cycle |
| Legs / probability / EV frozen | **NO** — 0 legs, all substantive fields NULL |
| predicted_at < kickoff | VERIFIED |
| Sentry | **UNKNOWN** — Railway log access unavailable this pass |
| 09-20 06:18 selected CIN @ HOU under run `49e65ca9…` vs CLE @ TB's `ac70e97f…` | **Recomputation V1 VERIFIED LIVE** |
| Post-kickoff rows | **NONE** — no contamination to quarantine |

## LIVE STATE AT AUDIT TIME

- **Odds — healthy/autonomous**: 2,107 snapshots since Sat, latest 20:16:01, poll state 17 games / **0 consecutive failures**. Ledger `2026-09`: **351 used, 137 provider-reported remaining** (floor 50, not tripped). Daily 09-20: **14** against ceiling 20 with a 6-call ramp reserve — at the reserve boundary.
- **Finalization — healthy**: today finalized exactly 2, **PIT 3 @ NE 20** and **NO 24 @ BAL 17**, both `confirmed_complete` at 20:00:50. **Six** other 17:00 games correctly held at `eligible_for_postgame_check` (provider not terminal). 20:05/20:25 games not yet candidates. **Duplicates: 0.**
- **Schedule**: 16 Week-2 games, no duplicates, identity correct. Six in-progress games still read `status='scheduled'` — stale, since status only advances at the daily 09:00 refresh or at finalization. **Not rewritten.**
- **Grading — 72h rule VERIFIED** at `postgame_grading.py:66`. Eligibility: DET @ BUF **09-21 20:31**, PIT @ NE and NO @ BAL **09-23 20:00:50**. Nothing due; **0 real grade events**.
- **Calibration**: valid frozen forward predictions **0**, eligible **0**, excluded **0**. No performance claim possible.
- **Monitoring**: only CRASHED dev deployment remains the known stale-branch `cron-master-refresh` (since 09-16). Sentry state UNKNOWN.

## CROSS-LANE (read from remote refs; nothing merged)

All four lanes are **documentation-only** ahead of `dev` (`fcf9669`): backend-autonomy `8b97926` (+2), ui-ux `d1369b8` (+1), modeling `9ffa9e4` (+1), qa-ops `abe87c7` (+1). **No unmerged code anywhere.** Two lane findings matter operationally:

- **QA/Ops: CI has failed on 59 consecutive pushes to `dev` since 2026-09-14** (last green run #384) while Railway autodeploy is live on `branch: dev` — **recent deploys bypassed the test gate.** Corroborated here: no new CRASHED deployments.
- **Modeling: the calibration module exists but is unwired** — independently confirmed above.

## THE DEADLINE THAT MATTERS

The **06:15 UTC tick on 2026-09-21** will select **NYG @ LAR** (kickoff 09-22 00:15, inside the 36h window). **If the committee defect is not understood by then, that tick consumes NYG @ LAR the same empty way**, permanently, under Recomputation V1.

## CASE B — LEGITIMATE PRE-KICKOFF OPPORTUNITIES (NOT ACTED ON)

| Game | Mins to kickoff | Odds age | Ref books | Cycles | Legitimate? | Max exposure |
|---|---|---|---|---|---|---|
| WAS @ DAL, SEA @ ARI, MIA @ SF | **2** | 7 min | DK+FD | 0 | **No** — not reachable | — |
| **IND @ KC** | **237** | 202 min | DK+FD | 0 | **Yes** | ≤48 requests |
| **NYG @ LAR** | **1672** | 202 min | DK+FD | 0 | **Yes** | ≤48 requests |

Odds ceiling is 1445 min, so both are comfortably fresh. **Recommendation: authorize neither yet** — both prior attempts produced empty No Bets, so a recovery run most likely burns another fixture for nothing. Fix the committee first.

---

# ADDENDUM 3 — EMPTY NO-BET ROOT CAUSE (2026-09-20 20:35 UTC)

Code trace complete. **No fix implemented** — the correction requires a product-semantics decision (see below). DB and Railway access were lost partway through this pass (tool calls began requiring approval), so runtime-only transitions are marked UNKNOWN rather than guessed.

## THE CAUSAL CHAIN (verified from code + previously-read persisted state)

1. `_evaluate_one_candidate` builds `strategy_input` **only** when `shared_chain.ev is not None and shared_chain.ev.ev_per_dollar is not None` — `apps/ai-orchestrator/app/orchestration/recommendation_worker.py:245`. The shared chain is the LLM-driven probability → EV → risk sequence.
2. **If the probability agent produced nothing, `shared_chain.ev` is None → `strategy_input` stays None.** Critically, the function still returns `CandidateRunResult(status="evaluated", ...)` — **not** `"failed"`.
3. `apps/workers/app/recommendation_worker.py:362` relays `[c["strategy_input"] for c in g.response["candidates"] if c.get("strategy_input")]` — every candidate without a `strategy_input` is **silently filtered out**, leaving an **empty candidates list** for a game that dispatched HTTP 200.
4. `compute_strategy_decision` (`apps/ai-orchestrator/app/features/strategy.py:243`) does `if not qualifying: → outcome="no_bet"`. With an empty candidate list the loop body never runs, so `qualifying` **and** `gate_rejected` are both empty — **identical to "evaluated, nothing qualified."**
5. `persist_strategy_products` writes one `no_bet` product per such game, **status `active`**.
6. `mark_recommendation_cycle_completed` is then called **unconditionally** as the last step (`recommendation_worker.py:467`), stamping `cycle_completed_at` — which Recomputation V1 treats as "this game is permanently done."

**Net: a total committee failure becomes an ACTIVE No Bet and permanently consumes the fixture.** That is the hypothesis in the directive, and it is confirmed.

## THE DEEPER PROBLEM — THREE STATES, TWO LABELS

The system has three distinct candidate outcomes but only two labels:

| Real state | Reported as | Distinguishable? |
|---|---|---|
| Evaluated, usable output | `status="evaluated"`, `strategy_input` set | yes |
| **Evaluated, no usable output** (chain produced no EV) | **`status="evaluated"`, `strategy_input=None`** | **NO** |
| Raised an exception | `status="failed"` | yes |

The middle row is the one that bit us, and it reports **success**. This means the known nested-census gap (`_NESTED_RESULT_KEYS = ("games","legs","products","items")` — `"candidates"` absent, `cron_dispatch.py:164`) would **not** have caught it even if `"candidates"` were added, because the status string says `evaluated`.

`apps/workers` already states the correct rule in its own comment — *"A game that failed to dispatch is OMITTED here, never represented as no_bet — it was never evaluated at all, which is a different fact from 'evaluated, nothing qualified.'"* — and simply does not apply it to a game that dispatched but yielded zero usable candidates.

## WHY NO FIX WAS IMPLEMENTED

Both minimal corrections touch documented product semantics, so PART 2/PART 6's "STOP before changing architecture/product semantics" applies:

- **Option A — omit at the relay.** Extend the workers' existing omission rule to games with zero usable candidates. Smallest diff, preserves strategy semantics exactly. **But it breaks Decision AA** (the per-game `no_bet` guarantee: every analyzed game gets a `no_bet` product).
- **Option B — a distinct failed state.** Add a third `GameDecision.outcome` (e.g. `analysis_incomplete`) and refuse the completion marker for it. Semantically correct. **But it ripples** into product persistence, explainability, activation snapshots, grading and Recomputation V1.

A third, narrower piece is safe and independent of both: **`_evaluate_one_candidate` should not report `status="evaluated"` when it produced no usable output.** That alone would make the state visible to monitoring without changing any product guarantee — but it does not by itself stop the false No Bet.

## REFERENCE_SPORTSBOOK — HISTORICAL NOISE, NOT THIS INCIDENT

`_run_one_game` returns `skipped_ineligible` **and creates no `recommendations` row at all** when candidate generation yields nothing, which is what an unresolved reference sportsbook produces. **Rows exist for both cycles**, so candidate generation succeeded and the sportsbook resolved. The historical `ConfigError REFERENCE_SPORTSBOOK…` volume in Sentry **predates the fix and is not this incident's cause.** (Live variable *value* unverifiable — OAuth returns names only.)

## WHAT REMAINS UNKNOWN

- **Why the agents produced nothing** — runtime-only. Needs `ai-orchestrator` logs for 2026-09-19 06:19 and 2026-09-20 06:19 UTC.
- Whether Sentry fired at all for those cycles.
- Whether `model_registry` (2 rows) covers every model referenced by `model_routing_rules` (12 rows) — a plausible static cause I could not check before losing DB access. **Worth checking first.**
- Exact outbound LLM request count — unknowable; `CallBudget` is in-memory and nothing writes `recommendation_costs`.

## MINIMUM FUTURE INSTRUMENTATION (not built)

To make this class provable rather than inferable: persist the `CallBudget` consumed-count per cycle, and record `fan_out_status` on the `recommendations` row. Both are small; neither is authorized here.
