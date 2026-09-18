# Phase 8 — Persistent Checkpoint Foundation + BALLDONTLIE Finalization (2026-09-18)

**Directive:** MANSA — FINALIZATION AUTONOMY NEXT PASS: PERSISTENT CHECKPOINT FOUNDATION → BALLDONTLIE AUDIT → CONDITIONAL FINALIZATION
**Environment:** dev only
**Provider calls made this pass:** **ZERO.** The BALLDONTLIE audit was answered entirely from a capture this project already owns. MSF untouched and still paused. No SportsDataIO call.
**Outcome:** foundation built and proven; BALLDONTLIE classified **A**; Part 3 implemented and deployed **inert**. The activation flag is deliberately unset — the cost numbers go to HQ first, as the directive requires.

---

## PART 1 — PERSISTENT POSTGAME CHECKPOINT FOUNDATION

### The defect, restated as a class

`app.workers.postgame_worker` keeps checkpoint progress in a caller-supplied dict and says so in its own docstring: *"no worker-run-history persistence layer exists yet."* A cron tick is a fresh process, so `checks_done` is empty every invocation, `is_reconciliation_complete` is never true, and at least one checkpoint is always due. That is not a SportsDataIO bug. **Any** final-score provider driven by a stateless cron inherits it, which is why it is fixed at the persistence layer rather than per vendor.

### The smallest additive design

`game_postgame_ingestion_state` already carried the whole contract except two things: it was provider-**shaped** but provider-**locked** (`check (provider_name in ('mysportsfeeds'))` — the same one-vendor hardcoding the directive forbids), and it had nowhere to record *which* checkpoints were done, only whether one capture had finished.

Migration `20260918190000_generic_postgame_checkpoint_foundation`, applied to dev, is purely additive — no column dropped, no row rewritten, no existing caller changed:

1. **Provider unlock** to a closed allow-list (`mysportsfeeds`, `sportsdataio`, `balldontlie`). An allow-list rather than free text: a typo (`BallDontLie`) would otherwise mint a ghost provider whose rows no worker claims, and the row would look healthy while its game silently never finalized.
2. **`checkpoints_done text[] not null default '{}'`** — the set of completed labels, in the vocabulary `app.workers.reconciliation.CHECKPOINT_OFFSETS` already owns. Every pre-existing MSF row reads `'{}'`, which is both true and harmless.
3. **`trg_game_postgame_ingestion_state_monotonic`**, enforcing three invariants in the database rather than in Python, per Volume 3's append-only-via-trigger rule — a guarantee that lives only in Python is one any future caller can skip.

### Proven live against dev, inside a transaction that rolled back

| Invariant | Result |
|---|---|
| Checkpoint set may grow | `grow_checkpoints=OK` |
| Checkpoint set may **not** shrink | `shrink=BLOCKED` |
| `attempt_count` may **not** decrease | `reset_attempts=BLOCKED` |
| `confirmed_complete` may **not** reopen | `reopen=BLOCKED` |
| Typo'd provider rejected | `ghost_provider=BLOCKED` |
| `sportsdataio` now permitted | `sportsdataio_allowed=OK` |

The block ended with a deliberate `raise`, so nothing persisted — verified afterwards: the table still holds exactly the 16 pre-existing `mysportsfeeds`/`confirmed_complete` rows.

### Module

`app.persistence.game_postgame_ingestion_state` now takes `provider_name` as a keyword on every function, defaulting to `mysportsfeeds` so the three existing callers (`msf_postgame_worker`, `msf_postgame_dispatcher`, `canonical_finalization`) are unchanged byte for byte. Two new functions, `read_checkpoints_done` and `record_checkpoints_done`; the latter **unions rather than replaces**, so a caller that knows only about the checkpoint it just finished cannot erase one an earlier process finished, and it writes nothing at all when the label is already stored — a duplicate tick costs one read.

### HQ's ten tests

`tests/test_persistent_checkpoint_foundation.py`, **15 passed**. Requirement 10 is *enforced*, not asserted: respx is strict and only Supabase routes are registered, so a request to any provider host raises.

| # | Requirement | Test |
|---|---|---|
| 1 | Fresh process sees previous state | `test_1_fresh_process_sees_previous_checkpoint_state` (+ absent row reads as empty, not an error) |
| 2 | Restart does not re-run a completed checkpoint | `test_2_...` — also asserts the *old* behaviour for contrast: the same instant re-buys four checkpoints with an empty set |
| 3 | Concurrent claim cannot double-dispatch | `test_3_...` — two ticks, exactly one non-`None` claim |
| 4 | Transient failure advances bounded retry | `test_4_...` — backoff and count land in the row, not the process |
| 5 | Permanent failure does not retry forever | `test_5_...` — `capture_failed_permanent` can never match the claim's WHERE |
| 6 | Finalized game = zero provider work | `test_6_...` — complete at any later instant, not just this one |
| 7 | Future game = zero provider work | `test_7_...` |
| 8 | State survives a new cron invocation | `test_8_...` — two clients, no shared Python state |
| 9 | Completion is idempotent | `test_9_...` — zero PATCH calls on a duplicate |
| 10 | No provider HTTP needed | `test_10_...` |

---

## PART 2 — BALLDONTLIE FINAL-SCORE AUDIT → **CLASSIFICATION A**

**Zero provider calls.** The decisive evidence was already in dev's own `game_events`: the 2026-09-11 Week 1 recovery call, persisted whole as an evidence envelope (endpoint, params, status, headers, body).

| # | Question | Answer, from persisted evidence |
|---|---|---|
| 1 | Endpoint with identity/status/scores/kickoff | `GET https://api.balldontlie.io/nfl/v1/games`. Row fields: `id`, `status`, `status_state`, `date`, `home_team`, `visitor_team`, **`home_team_score`**, **`visitor_team_score`**, quarter/OT splits, `week`, `season`, `postseason`, `venue` |
| 2 | Request shape | **Bulk by (season, week)**: `seasons[]=2026&weeks[]=1&per_page=25` returned all 16 games in one request. `meta` carried only `per_page` — no cursor at 16 rows |
| 3 | 2026 support | **HTTP 200, `season: 2026`, `games_found: 16`** — a real response from this season, not documentation |
| 4 | Identity coverage | Week 1: **16/16** canonical games match on (kickoff, home team), exact, **zero tolerance used**. `game_provider_ids` holds 16 balldontlie rows (Week 1) and **0 for Week 2** — derivable from the same bulk call. `team_provider_ids` 10/32, **not needed**: matching is on `games.home_team` text |
| 5 | Plan/tier and rate limit | `x-ratelimit-limit: 5`, `x-ratelimit-remaining: 4` — **5 requests/minute**, captured live. `nfl/v1/games` is the **free-tier** endpoint (the 2026-09-07 evidence: `games` 200, ALL-STAR-tier `player_injuries` 401, same key) |
| 6 | Cost model | **Rate-only.** No per-request charge, no monthly-quota header, no credit field anywhere in the response |
| 7 | Copyable, not inferred | Yes — `home_team_score`/`visitor_team_score` are whole-game provider fields, copied verbatim. Quarter splits are never summed (the bake-off recorded quarter nulls on real `Final` games) |
| 8 | One request, many games | **Yes — 16 games per request.** Preserved in the implementation |
| 9 | Raw → canonical → grading | Yes. `write_raw_game_events` → `finalize_game` → existing `postgame-grading` cron, all already built |
| 10 | Existing capture proves the shape | **Yes, and it is unusually good evidence** — see below |

### The capture holds all three lifecycle states at once

| Game | `status` | `status_state` | Away | Home |
|---|---|---|---|---|
| NE @ SEA | `Final` | `final` | 10 | 13 |
| SF @ LAR | `1:31 - 1st` | `in_progress` | 3 | 0 |
| NO @ DET | `9/13 - 1:00 PM EDT` | `scheduled` | null | null |

**The middle row is the safety case, and it is real data, not a hypothetical.** A rule keyed on "score is not null" would have frozen a first-quarter 3-0 as the result of that game. The code therefore branches on the machine-readable `status_state`, never on the display string and never on score presence. There is a test for exactly that row.

### Cross-provider agreement

BALLDONTLIE reports NE 10, SEA 13. Dev's canonical `final_score` for that game — written by the **MySportsFeeds**-sourced backfill — is `{"away": 10, "home": 13}`. **Two independent providers, one real 2026 game, exact agreement.** The directive's "final scores conflict between authoritative sources" STOP condition is not triggered; on the one game where both have spoken, they agree.

---

## PART 3 — IMPLEMENTATION

| Piece | What |
|---|---|
| Model | `FinalScoreLine` (`app/adapters/models.py`) — keeps `provider_status` and `is_final` separate on purpose |
| Adapter | `BallDontLieFinalScoreAdapter.fetch_week_final_scores` — bulk by (season, week), `per_page=100`, refuses a partial week if a cursor unexpectedly appears |
| Worker | `app/workers/balldontlie_finalization_worker.py` |
| Endpoint | `POST /v1/internal/balldontlie-finalization/run` |
| Dispatcher target | `balldontlie-finalization` |
| Cron service | `cron-balldontlie-finalization` (dev), `*/30 * * * *`, `apps/workers`, `restartPolicy: NEVER` |

**Its own cron, not a lodger.** Finalization *produces* finalized games; `postgame-grading` *consumes* them and would deadlock on itself if it also produced them. `msf-postgame-worker` is a different, paused provider. One cron, one responsibility.

**Claim first, fetch second** — the ordering that makes the zeros real. A game is claimed through the Part 1 foundation before any request; weeks are derived from *claimed* games, so a slate where nothing is claimable issues no request at all.

### Tests — 29 new, all passing

`test_balldontlie_finalization_worker.py` (18) and `tests/adapters/test_balldontlie_final_score_adapter.py` (11), the latter parsing the real captured payload verbatim. Highlights: in-progress game never finalized; final-but-scoreless never written; already-finalized never overwritten; score copied verbatim; raw evidence written **before** the canonical score; no exact match → reported, never guessed; `WSH`→`WAS` alias resolves; 16 games cost exactly 1 request; two weeks cost exactly 2; attempt budget survives restart; disabled gate makes **no call of any kind** (proven with strict respx and zero routes registered).

Full suites: **sports-intel-layer 1086 passed**, **workers 101 passed**, with the same 5 pre-existing wall-clock failures in `test_odds_cadence_persistence.py` — untouched, out of scope, as in every prior pass.

---

## POLLING / COST POLICY — WORST CASE, BEFORE ACTIVATION

| Clause | How it is achieved |
|---|---|
| Pre-kickoff game = 0 calls | `scheduled_start <= now - 3h` in the query |
| Finalized game = 0 calls | `finalized_at is null` in the query |
| Missing mapping = 0 calls | identity resolved from the response, after the fetch |
| One response satisfies many games | 16 games per request, test-enforced |
| Transient failure bounded | durable `next_eligible_attempt_at`, +20 min |
| Permanent failure stops | `capture_failed_permanent` is unclaimable; `MAX_ATTEMPTS=6` quarantines **before** the fetch |
| Rate limit respected | ≤2 requests per tick against a 5/min limit |
| Restart does not reset attempts | DB trigger forbids `attempt_count` decreasing |
| No unbounded polling | every bound is in the query or the durable row |

**Numbers at `*/30` (48 ticks/day):**

- **Calls per game: 0 marginal.** Cost is per *week*, not per game — 1/16th of a call per game on a full Sunday.
- **Calls per NFL week (realistic):** ~**10**. A week only costs a call on ticks where it still has a claimable unfinalized game; games leave the candidate set the moment they finalize.
- **Calls per day on Sunday (realistic):** ~**6**. (Worst case, if every tick all day had a claimable game: 48 for one week, 96 across two.)
- **Absolute daily ceiling:** **96** — 48 ticks × at most 2 distinct NFL weeks in the 4-day lookback.
- **Rate-limit utilisation:** 96 / 7,200 daily capacity = **1.3%**. Within any single minute, at most 2 of 5 requests = 40%, once per 30 minutes.
- **Monetary cost: none.** Free-tier endpoint, rate-only limit, no per-request charge.

### ACTIVATION IS NOT DONE — ONE FLAG, HQ's CALL

`BALLDONTLIE_FINALIZATION_ENABLED` is **unset**, so the worker returns `status="paused"` having made no call of any kind, and the endpoint is a no-op. The directive says to report worst-case *before* activation, and a report Mac reads after the fact is not that.

**To activate:** set `BALLDONTLIE_FINALIZATION_ENABLED=true` on `sports-intel-layer` (dev), **without** `skipDeploys` (the gate lives on that service, so it needs a new deployment to become live), and confirm SUCCESS. **For the Week 2 proof this must happen before Sunday 2026-09-20 ~20:00 UTC**, when the 17:00 games end.

---

## BOUNDARY COMPLIANCE

MSF not re-enabled and not touched. No SportsDataIO call, and its postgame worker not enabled — still the audit's UNKNOWN. Zero provider calls this pass. No probability, scoring, or EV semantics touched. The armed recommendation proof was not altered, cancelled, or triggered; `REFERENCE_SPORTSBOOK_PREFERENCE` and `MAX_LLM_CALLS_PER_GAME` remain as set, and the natural 06:15 UTC tick on 2026-09-19 is untouched. No unrelated repairs: the `postgame_worker`'s own process-local dict is left as-is (HQ said not to enable it; the foundation it needs now exists), and the 5 pre-existing wall-clock test failures remain unfixed and out of scope.
