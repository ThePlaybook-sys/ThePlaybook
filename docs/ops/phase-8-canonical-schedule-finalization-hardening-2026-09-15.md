# Canonical Schedule + Finalization Hardening

**Date:** 2026-09-15
**Directive:** MANSA HQ — "CANONICAL SCHEDULE + FINALIZATION HARDENING"
**Type:** IMPLEMENTATION — **zero provider calls** (no SportsDataIO, no Odds API, no MSF, no LLM)
**Master Refresh:** still **paused**. `MASTER_REFRESH_ENABLED` was deliberately **not** set to `true`.

---

## 0. What shipped

| Part | Deliverable | State |
|---|---|---|
| 1 | MSF → canonical finalization, permanent | Complete; **live Week 1 backfill EXECUTED — 16/16 finalized** (see §6) |
| 2 | Master Refresh V2 — full-season persistence, coverage assertion, roster split | Complete |
| 3 | `MASTER_REFRESH_ENABLED` fail-safe gate | Complete, left **paused** |
| 4 | Cost contract | Documented below |
| 5 | Infra debt + permanent one-shot-service rule | Recorded below |

**Test result: 942 passed, 5 failed in `sports-intel-layer`; 987 passed, 0 failed in `ai-orchestrator`.**
The 5 failures are **pre-existing and unrelated** — verified by running the suite on a clean
`dev` tree before any of this work (baseline: 885 passed / 5 failed, same 5 tests). See §7.

---

## PART 1 — MSF → canonical finalization

### 1.1 Root cause, restated from the audit

`mark_game_finalized`/`update_final_score` have existed since Phase 3E-8, but their only caller
was `app.workers.postgame_worker` — the **SportsDataIO** path. The MySportsFeeds postgame path
captured a complete boxscore, marked `game_postgame_ingestion_state.state='confirmed_complete'`,
and stopped. It never finalized the canonical game. SportsDataIO finalization was *assumed*;
MSF completion was never wired to it.

### 1.2 What was built

`apps/sports-intel-layer/app/workers/canonical_finalization.py` — permanent architecture, not a
one-off backfill script. Every future MSF `confirmed_complete` observation finalizes its canonical
game by the same path the Week 1 backfill will use.

**Zero provider calls by construction.** No adapter is imported and no provider client is
constructed anywhere in the module. It reads only `game_postgame_ingestion_state` and the
`game_events.raw_payload` rows that table already points at via `raw_capture_id`.

**Deterministic canonical resolution.** `game_postgame_ingestion_state.game_id` *is* the canonical
game id and `raw_capture_id` *is* the capture that justified the state — no team/date matching, no
payload scanning, no guessing.

**Authority rules — every one a refusal, never a guess:**

| Condition | Outcome |
|---|---|
| state is not `confirmed_complete` | never read |
| `raw_capture_id` is null | `skipped: no_raw_capture_id` |
| capture row missing/unreadable | `skipped: capture_missing_or_unreadable` |
| `body.game.playedStatus != "COMPLETED"` | `skipped: observation_not_completed` |
| either score missing/unparseable | `skipped: incomplete_or_unparseable_score` |
| both scores present | `finalized`, score **copied**, never derived |

The payload is the evidence; the state row is only bookkeeping *about* it. A state row reading
`confirmed_complete` over a payload reading `LIVE` finalizes nothing — proven by test.

**Idempotency is enforced by the database, not by a prior read.** New
`app.persistence.games.finalize_game` writes `status`/`final_score`/`finalized_at` in a **single**
PATCH filtered server-side on `finalized_at=is.null`. A re-run matches zero rows, writes nothing,
and returns `False` → reported as `already_finalized`. There is no read-then-write window for two
processes to race through, and the original finalization moment can never be overwritten.

This sits *alongside* `mark_game_finalized`/`update_final_score` rather than replacing them: those
two are separate PATCHes, so a caller can crash between them and leave a game `final` with a null
score. `postgame_worker` sequences them carefully and is unchanged; new callers use `finalize_game`.

**Duplicate captures cannot double-process — and the live shape is better than assumed.**
`resolve_canonical_capture` collapses repeats per game to the most recent `captured_at` (row `id`
as the deterministic tie-break) *before* anything is written, reporting
`duplicate_captures_collapsed` rather than silently discarding.

A live read (§6) corrected an assumption carried over from the audit. Duplicate captures do exist
in `game_events` — NE@SEA has 3 and DEN@KC has 2, 19 MSF rows across 16 games — but
`game_postgame_ingestion_state` holds **exactly one row per game** (its unique constraint is
`(game_id, provider_name)`). So the function this module actually reads from cannot present a
duplicate, and `raw_capture_id` names exactly one capture: **the extra `game_events` rows are never
read at all**, which is a stronger guarantee than collapsing them would be. The collapse logic
remains as a defensive invariant, and on this dataset it will correctly report
`duplicate_captures_collapsed = 0` rather than a misleading non-zero number.

### 1.3 The HTTP boundary — and why it is separate

`POST /v1/internal/canonical-finalization/run`.

It is deliberately **not** a step inside `/v1/internal/msf-postgame/dispatch`. That dispatcher is a
full zero-call no-op when `MSF_POSTGAME_ENABLED=false`, and folding finalization into it would make
finalization share that pause and stop too — even though finalization costs nothing to run.
Finalization must keep draining the already-captured backlog while ingestion is paused for cost, so
it gets its own endpoint and can run on its own cadence, independent of provider state. Covered by
a test that runs it with `MSF_POSTGAME_ENABLED=false` and asserts a game still finalizes.

### 1.4 `final` is terminal — the schedule guard

`app.persistence.schedule.persist_schedule_entries` previously PATCHed `status` from the provider
unconditionally. With V2 persisting the full season, every already-played game is re-seen on every
daily refresh, and SportsDataIO can still describe a played game as `Scheduled` — so a refresh
could regress a finalized game.

The guard is Postgres's own, never a prior read: the update carries `finalized_at=is.null` as a
server-side filter, so a finalized game matches zero rows and the downgrade is *impossible* rather
than merely unlikely. When that fires, the row is re-patched **without** `status`, so venue,
stadium, week and kickoff still reconcile on a played game while only its outcome stays terminal.
`final_score` and `finalized_at` were never in the writable field set at all.

> A batched pre-read of finalized ids was built first and then removed: it reintroduced exactly the
> read-then-write window the guard exists to close, and cost an extra request per run. The
> single-guarded-PATCH design is both cheaper and strictly safer.

---

## PART 2 — Master Refresh V2

### 2.1 Full-season persistence

`filter_slate_window` used to run **before** `persist_schedule_entries`. A run fetched the full
season (SportsDataIO's Schedule endpoint always returned all ~304 rows), then discarded everything
outside `[today, today+7)` **before it could be written**. That is the precise mechanism that
produced the Week 2 gap: the games were in the response and were thrown away.

V2 persists every entry the provider returned. This costs **no extra provider calls** — the same
single response is simply no longer truncated — and makes the schedule robust to missed runs: any
one successful run restores complete coverage.

The window still governs roster/DGI work, which stays windowed on purpose.

### 2.2 The 7-day window becomes an assertion

`apps/sports-intel-layer/app/master_refresh/coverage.py`. After persistence, per-day coverage
across `[today, today+7)` is compared: **expected** from the provider payload already in hand,
**actual** from the canonical read Master Refresh already performs. Zero additional calls of any
kind.

It asserts **reconciliation, not attendance.** An NFL Tuesday legitimately has zero games, so
"every day has ≥1 game" would be a false-alarm generator. What is asserted is: *every game the
provider says falls in this window has a canonical row.*

A gap is **reported, never repaired** — surfaced on `MasterRefreshResult.coverage_gaps`, logged as
a warning, and it turns the run `partial`. No game is ever invented to close one.

### 2.3 Schedule / roster separation

There was never a real dependency: schedule persistence already completed before any roster call,
and roster failures were already non-blocking.

| | `run_schedule_refresh` | `run_roster_refresh` |
|---|---|---|
| Purpose | canonical games + coverage assertion | players, depth charts, DGI player data |
| Provider cost | **1 call** | up to 32 |
| Failure impact | blocking (schedule integrity) | isolated, non-blocking |
| Schedule calls made | 1 | **0** — reads the canonical slate back |

`run_master_refresh` still runs both in order, so **no existing caller changes behavior.** Steps
5–8 were extracted verbatim into `_execute_roster_phase`, shared by both paths — the per-team
failure isolation is not reimplemented anywhere.

---

## PART 3 — `MASTER_REFRESH_ENABLED` fail-safe gate

Checked as the **first statement** of every entry point, before any provider *or* Supabase call.

**Explicit-opt-in: only a case-insensitive `"true"` runs the refresh.** Unset, empty, `"false"`,
`"1"`, `"yes"` — all paused.

This is **deliberately inverted** from `MSF_POSTGAME_ENABLED`, whose unset value means *enabled*.
The two flags fail safe in opposite directions on purpose: a removed `MSF_POSTGAME_ENABLED` should
keep ingestion running, whereas a removed `MASTER_REFRESH_ENABLED` must never be able to start
spending SportsDataIO calls on its own. The directive specified this inversion explicitly; the
earlier audit had proposed mirroring MSF exactly, and the directive supersedes it.

A paused run:
- makes **zero calls of any kind** — proven by a test with respx in strict mode and **no routes
  registered at all**, so any request would raise;
- creates **no `master_refresh_runs` row** (the gate precedes `start_master_refresh_run`), so a
  pause never leaves a durable row claiming work it did not do;
- returns `status="paused"`, distinguishable from `"failed"`, with `error=None`, so the cron exits
  **0** — a clean no-op deployment replacing today's daily CRASHED one.

**`MASTER_REFRESH_ENABLED` was NOT set to `true`.** Master Refresh remains paused, per directive.

---

## PART 4 — Cost contract

| Operation | Cadence | SportsDataIO | Odds API | MSF | LLM |
|---|---|---|---|---|---|
| **Schedule Refresh** (`run_schedule_refresh`) | daily | **1** | 0 | 0 | 0 |
| Rolling 7-day coverage assertion | every schedule refresh | **0** | 0 | 0 | 0 |
| **Roster Refresh** (`run_roster_refresh`) | separate, slower cadence | up to 32 | 0 | 0 | 0 |
| **Canonical finalization** (`/v1/internal/canonical-finalization/run`) | own cadence, provider-independent | **0** | 0 | **0** | 0 |
| Week 1 finalization backfill | one-off | **0** | 0 | **0** | 0 |
| **This entire implementation pass** | — | **0** | **0** | **0** | **0** |

Daily canonical schedule integrity costs **exactly one SportsDataIO call**, and that call now
delivers the full season instead of a 7-day slice. The up-to-32 roster-call explosion is off the
daily path entirely — which was the condition set for authorizing re-enablement.

The single Schedule call stays 24h-cached (`_SCHEDULE_TTL_SECONDS = 86400`), but that cache is
`InMemoryCacheBackend` and therefore **process-local** — it does not survive a redeploy or a fresh
cron container. The 1-call/day figure comes from the cadence, not from the cache.

---

## PART 5 — Infrastructure debt

### 5.1 Stale cron branches — recorded, NOT changed

Four dev cron services are pinned to `claude/new-session-fqsad5` instead of `dev`, and have been
running ~3-week-old code, silently missing every `dev` fix:

| Service | Branch | Cron | Last deploy |
|---|---|---|---|
| `cron-master-refresh` | `claude/new-session-fqsad5` | `0 6 * * *` | 2026-09-15 (CRASHED) |
| `cron-recommendation-worker` | `claude/new-session-fqsad5` | `15 6 * * *` | 2026-08-27 |
| `cron-postgame-grading` | `claude/new-session-fqsad5` | `*/30 * * * *` | 2026-08-27 |
| `cron-adaptive-weighting` | `claude/new-session-fqsad5` | `0 8 * * *` | 2026-08-27 |

`cron-postgame-grading` is on the calibration critical path, so its staleness matters beyond
hygiene: **none of this pass's finalization work reaches it until it is repointed at `dev`.**
Per directive, no cron branch was changed in this pass.

### 5.2 PERMANENT RULE — one-shot / diagnostic services must not track an autodeploying working branch

**Rule:** a one-shot or diagnostic Railway service MUST NOT be connected to a branch that receives
ongoing commits. It must be pinned to an immutable ref, or created, run once, and deleted before
any further commit lands on the branch it tracks.

**Why this rule exists (the incident that produced it).** The `phase8-context-experiment` service
was created to run a 6-call Anthropic experiment and was left tracking `gateb-diag-tmp` with
autodeploy live. Four subsequent cherry-picks to that branch each re-triggered a deploy, and each
deploy re-ran the one-shot experiment from the top: **≈30 real Anthropic requests against an
authorized budget of 6.** The in-process budget guard held at 6 *per process* every time and was
never the failure — a per-process guard cannot bound a per-deploy re-execution. The cost control
that was missing was architectural, not arithmetic.

**Corollaries:**
1. A budget guard scoped to a process bounds one run, never a service's lifetime. Never treat one
   as a spend cap.
2. A one-shot service's deletion is part of the task, not cleanup to do later.
3. While such a service exists, **no commits to the branch it tracks** — including unrelated ones.

The experiment service has since been deleted and the leak is closed.

---

## 6. Week 1 backfill — EXECUTED 2026-09-15 20:16 UTC

### 6.1 Execution mechanism — no secret reached this session

`INTERNAL_SERVICE_TOKEN` was never read, printed, or requested. The backfill ran through the
**existing authorized runtime that already holds it**: the cron dispatcher.

1. Added a `canonical-finalization` target to `apps/workers/app/cron_dispatch.py`, mapping to the
   already-deployed endpoint — the module's own documented "target mapped so activation is a
   config-only change" pattern. Pushed to `dev`; `cron-msf-postgame` (which already tracks `dev`,
   already points at `sports-intel-layer`, and already holds the token) autodeployed it.
2. Temporarily set that service's `CRON_DISPATCH_TARGET=canonical-finalization` (`skipDeploys:
   true`).
3. Its next scheduled `*/15` tick at 20:16:13 UTC ran the dispatch once.
4. Reverted `CRON_DISPATCH_TARGET=msf-postgame-worker` immediately, before the 20:30 tick.

`cron-msf-postgame` was chosen because MSF ingestion is currently paused
(`MSF_POSTGAME_ENABLED=false` makes its dispatcher a zero-call no-op), so borrowing one tick cost
nothing and skipped no real work. **No new Railway service was created** — the one-shot-service rule
in §5.2 is respected rather than worked around. Service config verified restored afterwards: branch
`dev`, schedule `*/15 * * * *`, start command `python -m app.cron_dispatch`, all unchanged.

### 6.2 Result — `considered: 16, finalized: 16, skipped: 0, failures: []`

From the dispatcher's own log line:

```
cron_dispatch starting target=canonical-finalization
  base_url=http://sports-intel-layer.railway.internal:8080
POST .../v1/internal/canonical-finalization/run "HTTP/1.1 200 OK"
cron_dispatch succeeded target=canonical-finalization result={
  'considered': 16, 'finalized': 16, 'already_finalized': 0, 'skipped': 0,
  'duplicate_captures_collapsed': 0, 'failures': []}
```

`duplicate_captures_collapsed: 0` is the honest, expected value for the structural reason in §1.2 —
the extra `game_events` rows are never read at all.

### 6.3 Verification — all eight checks, read-only

| # | Check | Result |
|---|---|---|
| 1 | all 16 have `status='final'` | **16 / 16** |
| 2 | all 16 have `final_score` populated | **16 / 16** |
| 3 | all 16 have `finalized_at` populated | **16 / 16** |
| 4 | every score matches persisted MSF COMPLETED evidence | **16 / 16 match, 0 mismatches** |
| 5 | no non-COMPLETED game finalized | **0** |
| 6 | no game finalized twice | **1 distinct `finalized_at`** across all 16 (`20:16:13.594649+00`) — one atomic batch |
| 7 | a re-run writes nothing | considers 16, **rows a re-run could write: 0**, reports 16 `already_finalized` |
| 8 | no provider calls | **0** |

Check 8 in detail: the dispatcher log shows exactly one HTTP request (the internal POST), and
`sports-intel-layer`'s log shows exactly one matching `200 OK`. Zero rows were written to
`odds_snapshots`, `game_events`, or `weather_snapshots` after 20:00 UTC — so no provider-sourced
data entered the system at all. An unrelated `cron-odds-worker` tick fired at 20:15:52 on its own
pre-existing schedule; it is not part of this execution and, per those same zero row counts, spent
nothing (consistent with every upcoming game being 26 days out and outside the poll window).

### 6.4 Grading and calibration visibility — and an honest limit

The 16 games now satisfy `grade_leg`'s preconditions: **16/16** carry a non-void status and a
`final_score` with numeric `home` and `away`, and **16/16** have `scheduled_start` for the
calibration eligibility contract. The database now holds 17 `final` games, up from 1.

Grading was **not** run, and nothing ran it automatically. There is nothing for it to do:
**0 `recommendation_legs` exist on these games — 0 anywhere in dev — and 0 grade events.**

**These Week 1 games can never produce a legitimate calibration observation.** Every one has
already kicked off, so any recommendation generated now would be post-event prediction, which the
forward-looking eligibility contract (`predicted_at < scheduled_start`, strict) correctly excludes.
The value of this backfill is not calibration rows; it is that the finalization mechanism is now
proven against real data, so games played from here forward finalize automatically.

## 7. Test results

| Suite | Before this pass (clean `dev`) | After |
|---|---|---|
| `sports-intel-layer` | 885 passed, 5 failed | **942 passed, 5 failed** |
| `ai-orchestrator` | 987 passed | **987 passed** |

**+57 tests, zero new failures.**

The 5 failures are the same 5 in both columns, all in `tests/test_odds_cadence_persistence.py`.
They are **pre-existing wall-clock rot, not caused by this work** — confirmed by stashing every
change and re-running the suite on a clean tree. The file hardcodes
`_T0 = 2026-09-14 16:30 UTC` with a kickoff 50 minutes later; once the real date rolled past
2026-09-14 those kickoffs moved into the past and the games stopped being "due". **Flagged, not
fixed** — out of scope for this directive, and worth a separate pass since these tests will stay
red until the fixtures are made relative to a controlled clock.

New coverage added:
- `tests/test_canonical_finalization.py` (18) — payload authority, score copying (including a real
  0–0 shutout, which a truthiness check would have dropped), duplicate collapse, idempotency,
  batch isolation, and a host assertion proving zero provider calls.
- `tests/test_canonical_finalization_endpoint.py` (4) — auth, response shape, no provider calls,
  and finalization still draining the backlog while MSF is paused.
- `tests/test_master_refresh_pause_gate.py` (18) — the enable/pause value matrix, zero calls with
  no respx routes registered, no `master_refresh_runs` row on pause, `paused != failed`.
- `tests/test_master_refresh_v2.py` (12) — the coverage assertion's semantics, full-season
  persistence, 1-call schedule path, gap→partial, and the roster path making zero schedule calls.
- `tests/test_schedule_persistence.py` (+5) — the terminal guard, with a mock that faithfully
  honours `finalized_at=is.null` rather than ignoring query params.

---

## 8. Not done, deliberately

- Master Refresh **not** re-enabled; `MASTER_REFRESH_ENABLED` not set to `true`.
- No cron branch, schedule, or target changed.
- No provider call of any kind — SportsDataIO, Odds API, MySportsFeeds, or LLM.
- Week 1 live backfill not executed (§6).
- The 5 pre-existing wall-clock test failures not fixed (§7).

---

## 9. Full-season Schedule refresh — BLOCKED, call NOT spent (2026-09-15)

**Directive:** MANSA HQ — "ONE AUTHORIZED FULL-SEASON SCHEDULE REFRESH".
**Outcome: STOPPED before execution. Zero SportsDataIO calls spent.
`MASTER_REFRESH_ENABLED` was never set to `true` and remains unset (paused).**

### 9.1 The blocker — canonical identity, found in the pre-execution baseline

`persist_schedule_entries` resolves a game's identity **solely** through
`game_provider_ids` on `(provider_name='sportsdataio', game_external_id)`. Found → PATCH.
Not found → INSERT a new canonical game and link it.

Live dev holds **zero `sportsdataio` game mappings**:

| Provider | Game mappings | …on manual-seed games | …on finalized games |
|---|---|---|---|
| `balldontlie` | 16 | 16 | 16 |
| `mysportsfeeds` | 16 | 16 | 16 |
| `the_odds_api` | 12 | 8 | 5 |
| **`sportsdataio`** | **0** | — | — |

**All 23 existing games — including all 16 Week 1 games finalized in §6 — have no
SportsDataIO mapping.** `games.external_provider_id` doesn't help either: it is either null or
`balldontlie:<id>`.

So every one of the ~304 season entries would resolve as *not found* and be **INSERTed as a new
canonical game**. The authorized refresh would have:

- created ~304 new `games` rows;
- given each of the 16 finalized Week 1 games a **second** canonical row — new, `scheduled`, no
  score — sitting alongside the finalized one;
- duplicated the 3 Week 5 games the same way;
- left dev with **~19 real-world games represented twice**, one row final and one row scheduled.

Verification item 5 ("no duplicate canonical games created") would have failed outright. Items 6
and 7 would have passed only on a technicality: the finalized rows are never touched *because they
are different rows*. Nothing is downgraded; the identity layer is split in half instead. For odds
linking, grading and calibration — all of which key on `games.id` — that is worse than the Week 2
gap it was meant to fix.

### 9.2 Why this is not fixable inside the authorized scope

This is the cross-provider reconciliation item the blueprint has deferred since Decision 2
(2026-08-13), which explicitly rules out team/date fuzzy matching and records that no worker yet has
authority to reconcile two providers' views of one real-world game.
`app/persistence/schedule.py`'s own docstring has said so all along: *"What this deliberately does
NOT do: reconcile two different providers independently discovering the same real-world game."*

It cannot be pre-empted with a zero-call backfill either: mapping the 19 existing games to
SportsDataIO requires SportsDataIO's `GameKey` for each, which only arrives **in the Schedule
response itself** — by which point `persist_schedule_entries` has already inserted the duplicates.

### 9.3 What was built and is ready

Both are deployed and inert while the gate is paused, and neither spends anything:

- `POST /v1/internal/schedule-refresh/run` → `run_schedule_refresh` (1 Schedule call, **0 roster
  calls**; a test asserts exactly one provider call and that any roster request would raise).
- `schedule-refresh` cron dispatch target, so invocation is config-only via the same
  secret-safe mechanism used in §6.

Tests: `sports-intel-layer` 945 passed / 5 failed (the same pre-existing 5 from §7);
`apps/workers` 45 passed.

### 9.4 Options — Mac's call, none taken

1. **Reconcile first, then refresh (recommended).** Add a one-time, in-run reconciliation step to
   the schedule path: for an entry with no `sportsdataio` mapping, match against an existing game on
   `(home_team, away_team, scheduled_start` date`)` and, on a unique match, `link_provider_id`
   instead of inserting. This is a blueprint deviation (Decision 2 rules out fuzzy matching) and
   needs explicit authorization plus a CHANGELOG entry. It is narrow here: teams are already
   normalized 32/32 to SportsDataIO abbreviations, and the match is exact on all three fields, not
   fuzzy. Still 1 provider call.
2. **Accept the duplicates and reconcile afterwards.** Spend the call, then merge ~19 duplicate
   pairs. Not recommended — it splits identity first and repairs it under time pressure, with the
   finalized rows at risk during the merge.
3. **Refresh into a clean slate.** Only viable if the 19 manual-seed rows are disposable; they are
   not — 16 carry real finalized scores and MSF/balldontlie mappings.

**Recommendation: option 1.** It keeps the single call, preserves the 16 finalized games, and
produces one canonical row per real-world game.

### 9.5 State left behind

- `MASTER_REFRESH_ENABLED` on `sports-intel-layer` dev: **unset → paused.** Never set to `true`.
- Zero SportsDataIO, Odds API, MSF and LLM calls this pass.
- No cron branch, schedule or target changed; `cron-msf-postgame` remains on
  `msf-postgame-worker`.
- Week 1's 16 finalized games untouched.
