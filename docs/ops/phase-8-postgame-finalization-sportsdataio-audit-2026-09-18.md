# Phase 8 — Postgame Finalization Autonomy: SportsDataIO Audit → STOP (Classification B)

**Date:** 2026-09-18
**Directive:** MANSA — POSTGAME FINALIZATION AUTONOMY: SPORTSDATAIO AUDIT → CONDITIONAL IMPLEMENTATION
**Environment:** dev only
**Provider calls made this pass:** **ZERO.** No SportsDataIO, no MySportsFeeds, no BALLDONTLIE, no API-SPORTS, no The Odds API, no LLM. Every finding below comes from repository source, checked-in fixtures, persisted ops documentation, the dev Supabase database (read-only SQL), and Railway configuration metadata (variable **names** only — no values read, no secret exposed).

**Outcome: STOP.** PART 2 classifies SportsDataIO as **B — UNKNOWN**. Per the directive's own instruction, the postgame implementation (PARTs 3–5) is not begun. A second, independent STOP condition was also found during PART 1 and is reported below, because it would block PART 3 even if quota were later classified A.

---

## PART 1 — AUDIT OF THE EXISTING SPORTSDATAIO POSTGAME PATH

### 1. Module / worker / function

`apps/sports-intel-layer/app/workers/postgame_worker.py` → `run_postgame_worker(...)`.

Supporting modules it calls, none of which are duplicated or redesigned here:

| Concern | Module |
|---|---|
| Checkpoint schedule | `app/workers/reconciliation.py` (`due_checkpoints`, `is_reconciliation_complete`) |
| Provider I/O | `app/adapters/providers/sportsdataio.py` (`SportsDataIOScheduleAdapter`, `SportsDataIOTeamStatsAdapter`, `SportsDataIOPlayerStatsAdapter`) |
| Canonical writes | `app/persistence/games.py` (`mark_game_finalized`, `update_final_score`), `app/persistence/team_stats.py`, `app/persistence/player_stats.py`, `app/persistence/schedule.py` |

### 2–3. Exact provider endpoints

| Purpose | Endpoint | Shape |
|---|---|---|
| Detect newly-final games | `GET /v3/nfl/scores/json/Schedules/{season}` | **bulk**, whole season, 1 call/cycle |
| Team stats (source of `final_score`) | `GET /v3/nfl/scores/json/TeamGameStats/{season}/{week}` | per (season, week), filtered client-side to one `GameKey` |
| Player stats | `GET /v3/nfl/stats/json/PlayerGameStatsByWeek/{season}/{week}` | per (season, week), filtered client-side to one `GameKey` |

It **does** use `TeamGameStats`. `final_score` is derived in `_ingest_final_stats_for_game` by reading the `Score` field off the `HomeOrAway == "HOME"` and `HomeOrAway == "AWAY"` team-stat lines — a **copy from provider evidence**, never an inference from play-by-play or a computed total. This satisfies the directive's "COPIED, never inferred" rule as written.

### 4–5. Calls required per completed game

- **Detection: 1 bulk call per cycle**, not per game. It reuses Master Refresh's own `SportsDataIOScheduleAdapter`, scoped to a window of `_RECONCILIATION_LOOKBACK_DAYS = 4` days back and `_FUTURE_BUFFER_DAYS = 1` forward.
- **Ingestion: 2 calls per game per due checkpoint** (`fetch_team_stats` + `fetch_player_stats`).
- `CHECKPOINT_OFFSETS` has **6** entries — `initial`, `+10m`, `+30m`, `+2h`, `+24h`, `+72h` — so the designed ceiling is **12 calls per completed game**, spread over 72 hours, plus 1 bulk Schedule call per cycle.

Both stats endpoints are week-scoped bulk payloads that the adapter filters down to a single `GameKey` in Python. Two games in the same week therefore cost 4 calls, not 2 — the bulk shape is **not** currently exploited for batching. Noted as an observation, not changed.

### 6. Existing retry behaviour

**This is the finding that matters most, and it is a STOP condition.**

`run_postgame_worker` takes `reconciliation_state: dict[str, ReconciliationGameState] | None` as a **caller-supplied, in-process parameter**, mutated in place. Its own docstring states the reason plainly: *"mirroring every other worker's `last_polled_at` convention — no worker-run-history persistence layer exists yet."*

There is no persistence for `checks_done`. Consequences for a cron-driven caller, where every tick is a fresh process:

- `checks_done` is **empty on every invocation**.
- `is_reconciliation_complete(frozenset())` is therefore always `False` — the `+72h` label can never be present.
- `due_checkpoints(...)` returns every checkpoint whose offset has already elapsed and is not in `checks_done` — i.e. **at least one, always**, for any game that has been finalized at all.
- So `_ingest_final_stats_for_game` runs on **every tick** for **every finalized game inside the 4-day lookback window**, at 2 calls each.

Worked example, at the `*/15` cadence the existing postgame crons use: 96 ticks/day × 16 Week 2 games × 2 calls = **3,072 SportsDataIO calls per day**, plus 96 bulk Schedule calls, sustained for the 4 days each game remains in the lookback window — on the order of **12,000 stats calls for one NFL week**. The designed figure is 192.

There is also **no backoff, no attempt ceiling, and no permanent-failure classification** in this path. A failing game appends to `failures` and `continue`s, and because `state.checks_done` is only updated *after* a success, a permanently failing game is retried on every tick indefinitely. The MSF path solved exactly this problem with a persisted `game_postgame_ingestion_state` row carrying `attempt_count` / `next_eligible_attempt_at` / `error_classification`; the SportsDataIO path has no equivalent.

This directly trips two of the directive's STOP conditions — *"polling could become unbounded"* and *"new architecture beyond the existing postgame design is required"* — independently of quota.

### 7. Existing persistence

| Artifact | Written? | By what |
|---|---|---|
| Raw capture | **No** | The SportsDataIO path persists *normalized* rows only. `game_postgame_ingestion_state.raw_capture_id` exists but is written by the **MSF** path, not this one. |
| `games.final_score` | Yes | `update_final_score`, copied from `TeamGameStats.Score` |
| `games.finalized_at` | Yes | `mark_game_finalized`, stamped with the worker's `now` when a game is seen `final` with a null `finalized_at` |
| `games.status` | Yes | indirectly, via `persist_schedule_entries` inside `_detect_newly_final_games` |
| `team_stats` / `player_stats` | Yes | `persist_team_stats` / `persist_player_stats` (append-only correction semantics preserved) |

Note on `finalized_at` provenance: it is stamped from **our clock at detection time**, not from a provider timestamp. That is the existing, approved Phase 3E-8 behaviour and is not changed here, but it is worth HQ knowing that `finalized_at` is "when we noticed", not "when the game ended".

### 8. Canonical identity

Safe. `_reverse_resolve_sportsdataio_ids` reads `game_provider_ids` for `provider_name='sportsdataio'` and builds a `game_id → provider_game_id` map. A game with **no** SportsDataIO mapping is simply absent from the map and is skipped before any provider call — **missing mapping costs 0 provider calls**, as PART 4 requires. Dev currently has SportsDataIO mappings for all 272 regular-season games, so this branch is not exercised in practice today.

### 9. Can it overwrite an already-finalized game?

**`finalized_at`: no.** It is only stamped when `game.get("finalized_at") is None`. Additionally `persist_schedule_entries` carries a server-side `finalized_at=is.null` filter, so a Schedule re-poll can never move a finalized game's status, and `final_score`/`finalized_at` are not in that module's writable field set at all.

**`final_score`: yes, by design.** `update_final_score` is unguarded and re-writes on every reconciliation checkpoint. That is the intended corrections mechanism (Decision 5 — a provider stat correction at `+24h` should land). It becomes a real hazard only in combination with finding 6: with no persisted `checks_done`, the same score is re-copied on every tick forever. The write is idempotent in value, so no data is corrupted — the cost is calls, not correctness.

**Concurrency:** there is no advisory lock, no `state`/claim column, and no idempotency key on this path. Two overlapping ticks would both pass the `finalized_at is None` check and both attempt to stamp. The second `PATCH` would be a harmless no-op against a now-non-null row, but both would have already spent their provider calls. The MSF path's `game_postgame_ingestion_state` claim row is the existing architectural answer; this path does not use it.

### 10. Tests

Yes — `apps/sports-intel-layer/tests/test_postgame_worker.py` exists and is substantial (fixture-driven, covering detection, finalization stamping, stat corrections appending rather than overwriting, and multi-game cycles). The checkpoint schedule itself is covered separately by the `reconciliation` module's tests. What is **not** covered, because it does not exist, is cross-invocation checkpoint persistence.

### 11. Why no cron/dispatcher target invokes it

Three independent reasons, all confirmed:

1. **No HTTP endpoint.** `apps/sports-intel-layer/app/main.py` exposes `/v1/internal/msf-postgame/run`, `/v1/internal/msf-postgame/dispatch`, and the canonical-finalization endpoint. There is **no** endpoint that calls `run_postgame_worker`.
2. **No dispatcher target.** `apps/workers/app/cron_dispatch.py`'s `_TARGET_PATHS` has no SportsDataIO postgame entry.
3. **It is not safely cron-shaped.** Finding 6 — the worker's contract assumes a long-lived caller that owns `reconciliation_state` across cycles. Wiring it to a stateless cron without first persisting checkpoint state is what turns 192 calls into ~12,000.

Reason 3 is the substantive one. Reasons 1 and 2 are a morning's work; reason 3 is a design gap.

---

## PART 2 — QUOTA / BILLING SAFETY

### Every local/persisted source audited

| Source | What it says |
|---|---|
| **Railway config** (`sports-intel-layer`, dev — variable names only) | `SPORTSDATAIO_API_KEY` and `SPORTSDATAIO_DIAGNOSTIC_TOKEN` are set. **There is no SportsDataIO budget, quota, plan, or rate variable of any kind.** For contrast, The Odds API has four (`ODDS_API_MAX_CALLS_PER_DAY`, `ODDS_API_DAILY_CALL_RESERVE_FOR_RAMP`, `THE_ODDS_API_MONTHLY_CREDIT_BUDGET`, `THE_ODDS_API_MIN_REMAINING_CREDITS`). SportsDataIO has zero. There is no configured bound and nothing that could enforce one. |
| **Database ledgers** | `odds_api_credit_ledger`, `odds_api_daily_call_budget`, `news_provider_daily_quota` exist. **No SportsDataIO ledger, budget, quota, or call-accounting table exists anywhere in the schema.** The system cannot report how many SportsDataIO calls have been spent or how many remain, because it has never recorded one. |
| **`tests/fixtures/sportsdataio/PROVENANCE.md`** | Documents a **Free Trial**: "10 of a 12-call budget spent across two rounds (2026-08-11/12)"; an 11th call spent 2026-08-18; "**12/12 budget: 11 used, 1 remaining, final call intentionally not authorized**". |
| **`docs/ops/phase-8.0.5-pass2.2-quota-recovery-2026-09-07.md:108`** | Repeats "zero SportsDataIO calls (**11/12 used, final call untouched**)". |
| **`PROGRESS.md`, 2026-09-16 onward** | The full-season Schedule refresh was executed and "**1 SportsDataIO Schedule call**" was spent; `cron-schedule-refresh` has been enabled at `0 9 * * *` since, and `master_refresh_runs` shows successful runs on 2026-09-16, -17 and -18 — **at least 3 further successful SportsDataIO Schedule calls after the "11/12 used" accounting**. |
| **`docs/ops/nfl-provider-bakeoff-2026-09-03.md`** | SportsDataIO benchmark column reads "Confirmed live" for `TeamGameStats` and box scores. Re-verified: the **"plan-gated to 2022–2024" restriction belongs to API-SPORTS, not SportsDataIO** — a misattribution that was checked against the table header before writing this. |

### The contradiction, stated plainly

The persisted trial accounting says the key had **1 call left** on 2026-09-07. The persisted run history says **at least 4 successful calls have been made since 2026-09-16**. Both are real records in this repository. They cannot both describe the current account state, which means the trial accounting is stale and the key is now on *some* other footing — **but nothing in this repository, this database, or this Railway project records what that footing is.** No plan name, no tier, no call allowance, no renewal date, no entitlement list, and no statement of whether `TeamGameStats` and `PlayerGameStatsByWeek` are entitled for the **2026** season specifically (every live capture in the repo is 2025REG or earlier).

### Classification: **B — UNKNOWN**

Not C. Nothing shows the key is exhausted or unauthorized — it is demonstrably working for `Schedules` right now. Not A either: "confirmed safe" requires evidence of an active plan with a known bound, and no such evidence exists in any local or persisted source. Establishing it requires the SportsDataIO account/billing dashboard, which is outside this session.

Per the directive: **no trial call was made to discover quota.**

### What is missing, specifically

1. The **active SportsDataIO plan/tier name** on the account holding `SPORTSDATAIO_API_KEY`.
2. That plan's **call allowance and period** (per-day / per-month / hard cap vs. overage billing).
3. Whether **`TeamGameStats`** and **`PlayerGameStatsByWeek`** are entitled on that plan for the **2026** season — the Free Trial captures prove the endpoints work, not that they are entitled now.
4. Whether overage is **refused or billed**. This is the difference between a bounded mistake and an unbounded invoice, and it is the single most important unknown given finding 6.
5. The current period's **consumption to date** — unknowable locally, since no ledger has ever existed for this provider.

### Expected Week 2 cost, if it were authorized

| Scenario | Stats calls | Schedule calls |
|---|---|---|
| **As designed** (persisted checkpoints, 16 games × 2 × 6) | **192** | ~1 per cycle |
| **As the code actually behaves today** wired to a `*/15` cron (no persisted checkpoints) | **~12,000** over the 4-day lookback | ~384 |

### Can an already-persisted, zero-cost source solve final scoring?

**No.** Checked exhaustively:

- **The daily Schedule refresh cannot.** The live-captured `tests/fixtures/sportsdataio/schedules_normal.json` row carries 32 keys — `Status`, `IsClosed`, `ScoreID`, `PointSpread`, `OverUnder`, the moneylines, forecast and stadium blocks — and **no score field**. `ScoreID` is an identifier pointing at SportsDataIO's separate scores feed, not a score. So the one SportsDataIO call we already make every day gives us terminal **status** for free and cannot give us **numbers**. (Honest caveat: that capture is of `Scheduled`-status rows, so this is strong evidence about the feed's schema rather than proof about a `Final` row.)
- **Already-persisted data cannot.** Dev's Week 2 currently holds 16 games: 1 already `final` (DET @ BUF, kicked off 2026-09-18 00:15 UTC) with **null `final_score` and null `finalized_at`**, and 15 still `scheduled`. There is no raw capture, no boxscore, and no stat row for it. Week 1's 16 games are fully finalized, but that came from the MSF backfill, which is the path HQ has paused.
- **BALLDONTLIE is the one real alternative, and it is not zero-cost.** The bakeoff rates its final scores **GREEN** — "real final scores, per-quarter breakdown, plus a human-readable one-line result summary", with a noted quarter-score-null granularity gap — via `/nfl/v1/games`, which is a **free-tier** endpoint that returned **200 OK with the current key on two separate live occasions** (the Phase 7 discovery probe and the Pass 1 follow-up), in contrast to the ALL-STAR-tier `player_injuries` endpoint that 401s. It is the only provider in this project that is both authorized today and known to carry final scores. But there is **no BALLDONTLIE schedule/score adapter in the codebase** — `app/adapters/providers/balldontlie.py` implements `InjuryAdapter` only — so using it means writing one, and its 5 req/min limit would need a real token bucket. That is new architecture, not a zero-cost read.

---

## PARTs 3, 4, 5 — NOT STARTED

Blocked by the PART 2 classification, exactly as the directive instructs. Nothing was wired, no target added, no cron created, no variable set, no provider called.

Recorded so HQ has it for the authorization decision: **even under classification A, PART 3 could not proceed as-is.** The smallest honest fix for finding 6 is to persist `checks_done` per (game, provider). `game_postgame_ingestion_state` is the natural home — it already has `game_id`, `provider_name`, `attempt_count`, `next_eligible_attempt_at`, `error_classification` and `state`, and it already carries the MSF path's bounded-retry semantics — but it has **no column for a checkpoint label set**, so this needs a schema addition. Per HQ's standing rule, that proposed schema is reported here and **not applied**.

---

## PARALLEL — RECOMMENDATION PROOF (independent, unaffected)

Verified read-only, zero cost:

- `REFERENCE_SPORTSBOOK_PREFERENCE` and `MAX_LLM_CALLS_PER_GAME` are **live** on `ai-orchestrator` dev.
- Deployment `8769ffad` (commit `ecd5665`, branch `dev`) is **SUCCESS** on `cron-recommendation-worker`, created 15:47 UTC — it carries the 36h first-paid-run gate, the 1-game throttle, the pre-LLM eligibility reorder, and Recomputation V1.
- **Today's 06:15 tick ran on the *previous* deployment** and is a clean demonstration of the circuit breaker: 3 marker rows at 06:18 (CAR @ ATL, NO @ BAL, MIN @ CHI, all Sun 17:00), then the run halted — `CONSECUTIVE_IDENTICAL_FAILURE_LIMIT = 3` firing on the then-unset sportsbook preference. Compare 2026-09-17, which created **256** rows across 7 minutes. 3 instead of 256 is the guard working.
- **`recommendation_agent_outputs` still holds 3 rows, all dated 2026-08-07.** No recommendation cycle has ever made an LLM call. `recommendation_legs`, `recommendation_leg_grade_events` and `recommendation_product_grade_events` are all **0**.
- The next natural tick is **2026-09-19 06:15 UTC**. At that moment the 36h cutoff is 2026-09-20 18:15 UTC, so the eight Sunday 17:00 kickoffs become eligible for the first time; the throttle takes exactly one, ordered `scheduled_start asc, id asc`. The scheduled check-in at 06:45 UTC will verify it.

Nothing was forced. No cycle was manually triggered.

---

## BOUNDARY COMPLIANCE

MSF not re-enabled (`MSF_POSTGAME_ENABLED=false` untouched). Week 2 not manually finalized. No trial call. No provider call of any kind. No new service, target, endpoint, cron, or variable. No schema change. No probability, scoring or EV semantics touched. The recommendation proof left armed and unmodified. No unrelated repairs — the `final_score` unguarded-overwrite observation, the missing concurrency claim, the bulk-payload batching opportunity, and `finalized_at`'s "when we noticed" provenance are all **reported, not fixed**.
