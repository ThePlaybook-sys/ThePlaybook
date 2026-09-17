# Recommendation Worker Autonomy Safety Gate (2026-09-17)

**Directive:** MANSA HQ — prove that enabling candidate generation cannot cause an unbounded LLM
fan-out, before `REFERENCE_SPORTSBOOK_PREFERENCE` is set.

**Compliance:** zero LLM calls. Zero provider calls. `REFERENCE_SPORTSBOOK_PREFERENCE` **not set**.
No recommendation run triggered. Dev only.

---

## The headline finding, stated first

**The `ConfigError` is not a cost circuit breaker, and treating it as one is unsafe.**

The traceback proves it. The failure is raised at `recommendation_worker.py:359`:

```
File "/app/app/orchestration/recommendation_worker.py", line 359, in run_game_recommendation
    reference_sportsbook_preference=reference_sportsbook_preference(),
File "/app/app/config.py", line 26, in reference_sportsbook_preference
    raise ConfigError(
```

Line 359 is the `generate_candidates_for_game(...)` call. The **game-level fan-out —
6 LLM agents — runs at line 336, twenty-three lines earlier.** So on every one of the
257 games, the committee fan-out was invoked *before* the config check could stop anything.

The run cost nothing for a different reason, and it is one nobody chose: each fan-out's agents
failed before reaching a provider. Verified three ways — no `api.anthropic.com` traffic in the
deploy log for the window (read against `f6fb2ece`, the deployment that actually served those
requests), `recommendation_agent_outputs` still at **3 rows, newest 2026-08-07**, and ~1.37s per
game, far too fast for six model round-trips.

**I must correct my own earlier report.** On 2026-09-17 09:15 I wrote "No agent ran." That was
imprecise: the fan-out *was* invoked; the agents failed before reaching a provider. "No LLM call"
holds and is now verified against the correct deployment — my first check queried the wrong
deployment id and returned a false negative, which I caught and re-ran.

The practical consequence: **whatever suppressed those calls is undesigned and unowned.** Fix the
underlying agent fault without fixing selection, and the next 06:15 run spends 6 calls per game
across the whole season.

---

## PART 1 — Why 257 games?

### The selector had exactly one filter

`apps/workers/app/persistence/games.py`, as it stood:

```python
params={"status": "eq.scheduled", "select": "id"}
```

That is the entire eligibility contract. Every stage HQ asked about, measured against dev:

| Selection stage | Enforced? | Live numbers |
|---|---|---|
| Total canonical games | — | 276 |
| Final vs upcoming | ✅ `status='scheduled'` only | 258 scheduled, 17 final, 1 live |
| **Kickoff time window** | ❌ **none** | 2 past-dated, 16 in-window, 240 beyond |
| **Odds availability** | ❌ none | 21 games have any odds row at all |
| **Odds freshness** | ❌ none at selection | (exists downstream, after the fan-out) |
| **Mapped sportsbook availability** | ❌ none at selection | (exists downstream, after the fan-out) |
| **Already-processed / retry state** | ⚠️ downstream only | `cycle_completed_at` checked inside `ai-orchestrator` |
| **Recommendation eligibility** | ❌ none beyond status | — |

**257 = every `status='scheduled'` game in the database at 06:19**, kicking off from that morning
through **2027-01-10**. (258 now; the 09:00 refresh added GameKey `202610902`.)

### Verdict: a selection defect, unambiguously

A normal run must not process an entire season because those games exist canonically — HQ's own
framing, and the codebase already agrees with it everywhere else. `read_grading_candidate_game_ids`,
sitting **twelve lines below** in the same file, carries a documented
`GRADING_CANDIDATE_LOOKBACK_DAYS = 14` bound. The recommendation counterpart had none.

---

## PART 2 — The safe eligible set (the architecture already defined it)

Per the directive, no new product horizon was invented. `sports-intel-layer`'s
`app/master_refresh/slate.py` states it:

> **MASTER REFRESH OPERATING HORIZON, approved by Mac 2026-08-13 (Volume 2 §8 v4.4):**
> `[today, today + 7 days)` UTC. … **This is the canonical statement of the horizon; do not
> silently reinterpret it elsewhere.**

Every specialized worker already honours it — Odds, Weather, Injury and Player Props each declare
their own `_CANDIDATE_WINDOW_DAYS = 7` with a docstring explaining it is numerically aligned rather
than a reinterpretation. **The Recommendation Worker was the only consumer that ignored it.**

### The contract now enforced, in the query

```python
RECOMMENDATION_WINDOW_DAYS = 7

params={
    "status": "eq.scheduled",
    "scheduled_start": [f"gte.{now.isoformat()}", f"lt.{window_end.isoformat()}"],
}
```

| Requirement | How it is met |
|---|---|
| not final | `status='scheduled'` — excludes final/live/postponed/canceled |
| genuinely upcoming | `scheduled_start >= now` — catches the 2 stale Aug fixtures still marked scheduled |
| inside the authorized horizon | `scheduled_start < now + 7d` — the canonical window, reused not reinvented |
| sufficiently fresh odds | **structural**: specialized workers only poll inside the same 7 days, so a game beyond it provably has no fresh odds. Freshness itself stays where it already lives, in `generate_candidates_for_game` |
| resolvable provider identity | unchanged — `odds_game_linking` owns it |
| configured reference sportsbook | unchanged — `select_reference_sportsbook`, downstream |
| not unnecessarily reprocessed | unchanged — `cycle_completed_at` in `ai-orchestrator` |
| not in retry/backoff suppression | **new** — consecutive-identical-failure breaker, Part 4 |

Both bounds are in the **PostgREST query**, not in Python: an unbounded slate can never reach the
dispatch loop to be filtered.

**Correct eligible count under the fixed rules: 16** (down from 257).

---

## PART 3 — Hard cost bounds

### Maximum LLM calls, counted from the code

Per game: 6 game-level agents, unconditionally, before any odds guard. Per candidate: 3 (shared
chain: Probability Modeling, Expected Value, Risk Manager) + 1 (Meta Agent) + at most 1 (Elite
reconciliation, only when an Elite subscriber exists) + 1 per active subscriber (Bankroll Coach).
`_V1_MARKET_TYPES` is moneyline/spread/total, both sides each → **up to 6 candidates per game**.

Dev today has **2 active subscribers, 1 Elite**. Independently corroborated by the
2026-09-15 prep doc, which counted 30 baseline per game from the same code.

| | Per game | Per run |
|---|---|---|
| Fan-out | 6 | — |
| 6 candidates × (3 + 1) | 24 | — |
| Elite second pass (1 Elite subscriber present) | up to 6 | — |
| Bankroll Coach (2 subscribers × 6 candidates) | 12 | — |
| **Maximum per game** | **48** | — |
| **257 games — what would have run** | | **≈ 12,336** |
| 16-game slate (the fixed contract) | | ≈ 768 |
| 20-game ceiling (absolute worst case) | | **≤ 960** |

Even with *no* odds at all — every game skipping candidates — the old path still cost
**257 × 6 = 1,542 calls**, because the fan-out precedes the guard.

### The bound implemented

```python
DEFAULT_MAX_GAMES_PER_RUN = 20          # env: RECOMMENDATION_MAX_GAMES_PER_RUN
CONSECUTIVE_IDENTICAL_FAILURE_LIMIT = 3
```

| Required property | How |
|---|---|
| explicit max games per run | `max_games_per_run()`, env-overridable |
| explicit max candidates per game/run | already architectural: 6 (3 V1 markets × 2 sides) |
| explicit max LLM requests per run | derived and bounded: **≤ 20 × 48 = 960** |
| **fail closed** | slate > ceiling → **zero dispatches**, `status="failed"` |
| Sentry-visible | `"failed"` is the status `cron_dispatch` reports at `error` |
| no silent truncation | the run is **refused entirely**, never trimmed and reported complete |

`games_selected` and `games_not_attempted` are on every result, so an incomplete run always says so.

**`20` is DERIVED, not a Blueprint number**, and disclosed as such in the constant's docstring — the
same class of decision as `GRADING_CANDIDATE_LOOKBACK_DAYS = 14`. An NFL week is at most 16 games and
a 7-day window can straddle two weeks, so 20 allows a legitimate straddle while staying an order of
magnitude below a season. **The mechanism is the important half; the number is flagged for HQ.**

---

## PART 4 — Marker / retry behaviour

### Why 256 markers from 257 failures

Parsed from the run payload:

- **256 games → HTTP 500.** Each reached `ai-orchestrator`, which creates the `recommendations`
  marker row as its *first* step (Milestone 4.9's correlation-id upsert), then raised `ConfigError`.
  One marker each.
- **1 game (`1aac9188-0cd4-42ed-8444-6e480657de73`) → transport failure**, "Server disconnected
  without sending a response". It never completed server-side, so **no marker row**.

256 + 1 = 257. Fully accounted for.

### Do they accumulate? Yes — that was the real problem

All 256 have `status = NULL` and `cycle_completed_at IS NULL`: open, not user-visible, correctly
retry-eligible. But `correlation_id` is `f"{run_id}:{game_id}"`, and tomorrow's run uses the **new**
`master_refresh_run` id — 256 fresh correlation IDs, **256 more rows, every day, indefinitely**,
from a fault that is identical every time.

They do not corrupt retry selection (the idempotency check is `cycle_completed_at`-based and these
are correctly incomplete), but unbounded growth from a deterministic misconfiguration is exactly
what the directive asked to fix.

### The fix

Two bounds, compounding:

1. **Horizon** — 16 candidate games instead of 257, so the worst case is 16 markers, not 256.
2. **Consecutive-identical-failure breaker** — a deterministic fault fails identically on every
   game, so after **3** the run halts with `status="failed"`. Worst case becomes **3 marker rows**,
   not 256.

`_failure_signature()` strips the per-game id before comparing, because
`AiOrchestratorCallError` embeds `game_id=...` — without that, every message differs and the breaker
would never trip on precisely the case it exists for. A genuinely transient per-game fault does not
repeat its text verbatim, so isolated failures still run the whole slate.

**No historical evidence deleted.** The 256 existing rows are untouched — they are the record of
what happened.

---

## PART 5 — Sentry semantic failure fix

**257 of 257 games failed and Sentry stayed silent.** `cron_dispatch` logged `succeeded`.

Cause: `result_failure_summary` returned `None` for `status="completed"` (a member of
`_NON_ERROR_STATUSES`) **before** ever inspecting the payload. And the fallback `failures` check
would not have caught it either — this worker reports per-game errors in `games[].error`, not a
top-level `failures` list.

**The fix is ordering plus a generic census**, not a 257-specific exception:

```python
nested = _nested_failure_census(result)   # checked BEFORE the known-good status set
if nested is not None:
    failed, total, sample = nested
    level = "error" if failed == total else "warning"
```

`_NESTED_RESULT_KEYS = ("games", "legs", "products", "items")` covers every worker family in the
project — recommendation's `games`, grading's `legs`/`products` — because they all follow the same
house shape: a list of dicts carrying a `status` and/or an `error`. An item counts as failed on
`status == "failed"` **or** a non-null `error`, since the two families differ in which they set.

- all items failed → **`error`**
- some failed → **`warning`**
- none failed, or nothing nested → **`None`**, so a genuinely clean `completed` run stays silent

---

## PART 6 — Reference sportsbook audit (nothing set)

**There is no authoritative product decision.** Searched Volume 1 (business/product), the blueprint
CHANGELOG, and all ops docs: no mention of DraftKings, FanDuel or any book as a product choice. The
only recurring concrete value is `"draftkings"` as a **test fixture**, which is not a decision.

**Intended role.** `select_reference_sportsbook` walks an ordered preference list and takes the
first book with *fresh* V1-market data; that book's line is the price every candidate is generated
from and every EV is computed against. It is a **system reference for pricing**, not a betting
recommendation — it decides what "the line" means for the whole committee.

**Ordered fallback is supported**, not just one book — `REFERENCE_SPORTSBOOK_PREFERENCE` is parsed
as comma-separated (`"draftkings,fanduel"`), and the fallback genuinely matters: if the first book
has no fresh row for a game, the next is tried before the game is skipped.

**Live dev coverage** (from `odds_snapshots`):

| Book | Snapshots | Games |
|---|---|---|
| `draftkings` | 189 | 21 |
| `fanduel` | 189 | 21 |
| `betonlineag` / `betrivers` / `lowvig` | 189 | 21 |
| `betmgm` | 188 | 21 |
| `bovada` | 186 | 20 |
| `betus` | 186 | 21 |
| `mybookieag` | 177 | 21 |

**Consequences of the choice.** DraftKings and FanDuel are tied on coverage and are the two books a
US retail user is most likely to actually hold an account with — which matters because a
recommendation priced against a book the user cannot bet at is advice they cannot act on. The
offshore books (`betonlineag`, `lowvig`, `mybookieag`, `bovada`) often post sharper or earlier
numbers, which would make EV look better while being less actionable. The choice is therefore a
**product** decision about actionability, not a data-quality one.

**Casing**: every real provider row is lowercase. Four legacy 2026-08-06 seed rows use
`DraftKings`/`FanDuel`. If the match is exact-string, the configured value must be lowercase.

**Should it be user-selectable eventually?** Architecturally it is already close: the preference is
an ordered list resolved per game, and nothing in `generate_candidates_for_game` assumes it is
global. But making it per-user multiplies the committee fan-out by the number of distinct
preferences — the candidates change, so nothing downstream can be shared. That is a real cost
decision, not a config toggle, and it belongs to a later phase. **A single system reference is
correct for V1.**

---

## VERIFY — 8 of 8, by test

`apps/workers/tests/test_recommendation_worker_safety_gate.py` (16 new tests):

| # | Property | Test |
|---|---|---|
| 1 | completed/final games cannot enter | `test_final_and_live_games_cannot_enter_recommendation_processing` |
| 2 | far-future games cannot enter | `test_far_future_season_games_cannot_enter_outside_the_authorized_horizon`, `test_past_dated_scheduled_games_are_excluded`, `test_the_real_257_slate_reduces_to_the_in_window_games` |
| 3 | stale/no-odds games do not reach agents | `test_stale_or_missing_odds_never_reach_llm_agents_because_the_game_is_never_dispatched` |
| 4 | run-level bound cannot be exceeded | `test_run_level_bound_cannot_be_exceeded_and_fails_closed` (257 vs 20 → **0 dispatches**), `test_bound_not_tripped_by_a_legitimate_slate`, `test_max_games_per_run_default_and_override` |
| 5 | no infinite retry-marker growth | `test_deterministic_config_failure_halts_instead_of_burning_the_slate` (3 dispatches, not 16), `test_isolated_per_game_failures_do_not_trip_the_breaker` |
| 6 | 257/257 produces a Sentry failure | `test_257_of_257_nested_failures_produce_a_sentry_failure_summary`, `test_partial_nested_failure_is_reported_as_a_warning`, `test_fail_closed_bound_is_sentry_visible`, `test_nested_check_applies_generically_to_grading_shapes` |
| 7 | clean completed runs stay silent | `test_genuinely_clean_completed_run_remains_non_reportable`, `test_clean_success_and_deliberate_pauses_remain_silent` |
| 8 | zero real LLM calls | `test_no_real_llm_or_provider_call_is_reachable_from_this_suite` — structural: every test is `respx.mock`-wrapped, and the worker service has no adapter, SDK or API key in its dependency graph |

**Regression: workers 84/84, ai-orchestrator 987/987, sports-intel-layer 1042 passed with the same
5 pre-existing wall-clock failures** in `test_odds_cadence_persistence.py` (unrelated, untouched,
verified byte-identical on a clean tree in an earlier pass).

---

## Is it now safe to set `REFERENCE_SPORTSBOOK_PREFERENCE`?

**Yes, on the worker side — with one caveat HQ should decide on first.**

Safe now: the slate is 16 rather than 257; the ceiling fails closed at 20 with zero dispatches;
a deterministic fault halts after 3; the worst case is bounded at ≤960 LLM calls per run and ~768
for a real slate; and a total failure can no longer hide inside a `completed` status.

**The caveat, stated plainly: the 6-agent game-level fan-out still runs before the odds guard.**
Within a 16-game slate that is at most 96 calls spent on games that may produce no candidates —
bounded and affordable, but still waste. Moving the odds/sportsbook check *above* the fan-out inside
`ai-orchestrator` would eliminate it. That is a change to `ai-orchestrator`'s orchestration order,
which this directive scoped to the worker, so it is **proposed, not done**.

---

## Owner decisions needed

1. **`REFERENCE_SPORTSBOOK_PREFERENCE` value** — recommend `"draftkings,fanduel"` (lowercase): tied
   top coverage, and the two books a US retail user most likely holds. No documented decision exists.
2. **Confirm or override `RECOMMENDATION_MAX_GAMES_PER_RUN = 20`** — mechanism shipped, number
   derived.
3. **Authorize reordering the fan-out behind the odds guard** in `ai-orchestrator` (the caveat above).

## Exact next step for the first legitimate pre-kickoff recommendation

Week 2's 16 games are inside the horizon but currently sit in the **FAR** odds cadence tier, so no
fresh odds exist yet (`odds_worker_poll_state` has 0 rows; `games_due: 0` every cycle). Freshness is
bounded by the kickoff-proximity tier, so candidates can only generate once games enter the nearer
tiers — roughly 24h out. The sequence is: (1) HQ sets the sportsbook preference; (2) the odds worker
naturally ramps as Week 2 kickoffs approach and persists fresh lines; (3) the next 06:15 run finds
fresh data and produces the first real pre-kickoff recommendation. **No further code is required.**
