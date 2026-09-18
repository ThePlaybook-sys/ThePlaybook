# Conditional Autonomy Runbook — STEP 4 / STEP 5 Audits (2026-09-18)

**Directive:** MANSA HQ — "CONDITIONAL AUTONOMY RUNBOOK". Proceed STEP 1 → STEP 5 automatically on
PASS; stop early only on a STOP condition.

**Outcome: STOPPED EARLY at STEP 4.** No authoritative recomputation policy exists — the directive's
own stop condition. The STEP 5 audit was completed anyway (it is independent and time-sensitive) and
**corrects a stated assumption**.

**Compliance:** dev only. Zero LLM calls. Zero provider calls. Nothing forced, nothing triggered.

---

## Why STEP 1 has not started

STEP 1 requires the **natural** `cron-recommendation-worker` run at **2026-09-19 06:15 UTC**. It is
~17 h away. The directive is explicit: *"Do not manually force work merely because a natural run has
not happened yet unless this directive explicitly permits it."* It does not permit it, so nothing was
forced. The armed configuration from the previous pass is untouched and live.

STEPS 4 and 5 are **pure audits** requiring no run, and both carry their own STOP conditions. Running
them now rather than at 06:45 tomorrow means HQ can decide in parallel with the proof instead of
after it.

---

# STEP 4 — RECOMPUTATION POLICY: **NO AUTHORITATIVE RULE EXISTS. STOP.**

## Current behaviour, established from code and live data

The only recomputation guard that exists is the idempotency check:

```python
correlation_id = f"{run_id}:{game_id}"          # apps/workers/app/recommendation_worker.py
existing = await read_recommendation_by_correlation_id(...)
if existing is not None and existing.get("cycle_completed_at") is not None:
    return ... status="skipped_already_computed"   # zero LLM
```

`run_id` is the latest **`master_refresh_runs`** row. And that row is **new every day** —
`cron-schedule-refresh` creates one at 09:00 UTC. Live proof from dev:

```
master_refresh_runs = 3   →   2026-09-16, 2026-09-17, 2026-09-18
```

**So the guard never fires across days.** Each morning mints a new `run_id`, which mints a new
`correlation_id`, which finds no prior row, which runs the full committee again — on identical
evidence, with no material change required. The guard only protects against a *repeat within the
same run*, which is a crash-retry protection, not a recomputation policy.

## Worst-case repeated spend

| | |
|---|---|
| Per game, per cycle | up to **48** model requests (the enforced ceiling) |
| Full horizon slate, one day | 16 × 48 = **768** |
| One game sitting 7 days in the horizon | 7 × 48 = **336** |
| Week 2's 16 games across the full horizon | **≈ 5,376** requests |

for work that legitimately needed ~768 **once**. Roughly **7× waste**, entirely from elapsed days
rather than changed evidence.

## What the architecture *does* have — and why it is not this policy

I looked for an existing rule before concluding, per the directive.

**Milestone 5.6 — Recommendation Lifecycle & Change Communication** is the closest thing, and it is
explicitly **"DESIGN APPROVED / DECISION LOCKED … NOT YET AUTHORIZED TO BUILD"**. It defines the
vocabulary `STRENGTHENED` / `WEAKENED` / `NO_LONGER_QUALIFIES` / `REPLACED` and a seven-value
`trigger_type`.

But it answers a **different question**: *what do we tell the user when our view changes after
activation*. It does not answer *when may we spend a committee run again*. And its own spec says so
in terms that settle this audit:

> **§7:** "The actual detection/trigger code for any of this — `market_monitoring_events` /
> `worker-market-monitor` remain zero rows/zero code; **this spec defines vocabulary, not a working
> pipeline**."
>
> **§7:** "**A re-evaluation numeric engine** (recomputing EV/confidence against new information) —
> explicitly out of scope here and for §9.5; **genuinely does not exist anywhere in the codebase**."

So: a locked *communication* vocabulary exists, unbuilt; a *re-evaluation* engine explicitly does
not. **Neither is a recomputation-eligibility policy, and inventing one is exactly what the directive
forbids.**

## Deterministic trigger signals that already exist today

Stated so HQ's decision is informed rather than abstract. These are live tables with real rows —
not proposals:

| Signal | Live state | Could support |
|---|---|---|
| `odds_snapshots` (append-only) | **2,333 rows** | materially fresher odds; **line movement** — `LineMovementFeatures` already exists in `app/features/market.py` |
| `market_monitoring_events` | **1 row** (Phase 7.1, `action_taken='none'`) | line-movement classification already computed, not yet consumed |
| `injury_reports` (append-only) | 1 row | injury/context change |
| `daily_game_intelligence` | 33 rows, per-category freshness | context staleness tiering |
| `recommendations.cycle_completed_at` | live | the existing within-run guard |
| kickoff proximity tier | live (`classify_window`) | elapsed-timing tier |
| `recommendation_product_lifecycle_events` | **0 rows**, 3 of ~7 event types built | lifecycle-event trigger |
| `trigger_type` / `trigger_event_data` columns | **proposed, not built** | — |
| re-evaluation numeric engine | **does not exist** | — |

## The smallest decisions HQ must make

1. **What makes a game eligible for a second paid committee run?** A defensible minimum using only
   what exists: *the reference sportsbook's line for this game has moved beyond the Phase 7.1
   threshold since the last completed cycle*, **or** *a new injury row landed for either team*,
   **or** *kickoff crossed into a nearer cadence tier*.
2. **Is there a floor regardless of change?** e.g. at most one committee run per game per day even if
   every trigger fires.
3. **Is there a cap regardless of triggers?** e.g. at most N committee runs per game per week.
4. **Does an unchanged game recompute at all** before kickoff, or does the first completed cycle
   stand until something moves?

**I have not implemented any of this.** Per the directive, the policy is HQ's.

## What this does NOT block

STEPS 1 → 3 are unaffected: STEP 4 sits *after* the 3-game expansion in the runbook's own order. The
1-game proof and the bounded 3-game expansion can still proceed autonomously, because the
`RECOMMENDATION_MAX_GAMES_PER_CYCLE` throttle caps daily spend regardless of the recomputation gap.
**The gap only becomes dangerous at full-slate, unthrottled operation** — which is precisely where
the runbook places this decision.

---

# STEP 5 — POSTGAME / FINALIZATION AUDIT: **AN ACTIVE PATH EXISTS**

## Correcting a stated assumption

The directive says *"MySportsFeeds may be intentionally paused. Do not assume MSF will finalize
Week 2."* Checked rather than assumed — **MSF postgame is ACTIVE, not paused.**

`MSF_POSTGAME_ENABLED` is **absent** from `sports-intel-layer` dev's variables. That does **not** mean
paused. The gate is deliberately inverted relative to `MASTER_REFRESH_ENABLED`:

> `msf_postgame_dispatcher.py`: "env var unset or any value other than a case-insensitive `"false"`
> means **enabled** — the safe default if the variable is ever accidentally removed is *keep
> running*, not *silently stop*."

**Live confirmation from the 13:00 UTC tick**, not inferred from the absent variable:

```
cron_dispatch succeeded target=msf-postgame-worker
result={'considered': 0, 'selected_game_ids': [], 'invoked_game_ids': [],
        'results': [], 'enrolled_game_ids': [], 'paused': False}
```

**`paused: False`.** `considered: 0` is correct — no Week 2 game has finished yet.

## The finalization chain for TB @ CLE

| Stage | Mechanism | State |
|---|---|---|
| terminal game status + final score | `cron-msf-postgame` (`*/15`) → `run_msf_postgame_capture` → `game_postgame_ingestion_state = 'confirmed_complete'` | **active** |
| canonical finalization | `run_canonical_finalization` → `games.status='final'`, `final_score`, `finalized_at` | **active, zero provider calls by construction** |
| grading evidence | `cron-postgame-grading` (`*/30`) → `worker-scheduled` → `ai-orchestrator` | **active, verified green since 2026-09-18 00:40** |

`canonical_finalization` reads only already-persisted rows (`game_postgame_ingestion_state` and the
`game_events.raw_payload` its `raw_capture_id` points at). It imports no adapter and constructs no
provider client — so the finalize step itself costs nothing. Its authority rules are refusals rather
than guesses: only `confirmed_complete`, the capture's own `playedStatus` must read `COMPLETED`, both
scores must be present and integral, and a score is **copied, never derived**.

## The one cost implication HQ should know

Because MSF is **not** paused, Week 2 finalization **will make real MySportsFeeds calls** when those
games complete. That is the authorized existing path and I changed nothing — but "MSF may be paused"
was the premise, and it is not true, so the spend is real and worth naming before Sunday rather than
discovering after.

**No new provider was activated and no cadence was increased.**

---

## Governance compliance

Never invented provider data, sportsbook prices or model outputs. Never bypassed deterministic
eligibility. Never exceeded an authorized ceiling. Nothing truncated and called complete. No scoring,
probability or EV semantics touched. No new paid provider, no increased paid cadence. Nothing forced
ahead of its natural run.
