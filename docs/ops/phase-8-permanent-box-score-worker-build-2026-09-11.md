# Permanent Box Score Worker Build, No Live Call (2026-09-11)

MANSA HQ directive: "PERMANENT BOX SCORE WORKER BUILD, NO LIVE CALL."
Builds the permanent completed-game MSF boxscore ingestion path end to
end -- position contract fix, the worker orchestration itself, and a
zero-cost full-pipeline replay against Gate B's real NE@SEA payload.
**No MySportsFeeds call was made anywhere in this pass.**

## 1. Position contract gap closed

**`app/adapters/models.py`**: `PlayerStatLine` gains one new optional
field, `position: str | None = None` -- purely additive, every existing
caller/constructor is unaffected.

**`app/adapters/providers/mysportsfeeds_game_boxscore.py`**:
`parse_game_boxscore` now reads `player.get("position")` (confirmed
present directly on MSF's real `player` object, e.g. `{"id": 166956,
..., "position": "LS"}`) and surfaces it on `PlayerStatLine.position`.
An empty string or missing key both produce `None` -- never invented,
never defaulted to a placeholder. The `stats` dict itself is completely
untouched by this change (position was never part of it).

**Tests** (`tests/adapters/test_mysportsfeeds_game_boxscore_adapter.py`,
5 new): real position extraction (Drake Maye "QB", Julian Ashby "LS");
all 69 real fixture players carry a real non-empty position; a
genuinely missing `position` key produces `None`; a blank `""` string is
treated as absent, not invented; adding `position` does not alter
`stats`' own content (`passYards`, `_unreliable_fields`, etc. unchanged).

## 2. Permanent MSF postgame worker

**New module**: `app/workers/msf_postgame_worker.py` --
`run_msf_postgame_capture(*, supabase_client, game_id, now=None,
fetch_boxscore=None)`, one canonical game at a time (matching this
pass's own framing). Flow exactly as specified:

```
ELIGIBLE -> atomic claim -> resolve MSF game_provider_id
-> perform boxscore request -> preserve raw response
-> validate response/game identity -> inspect playedStatus
-> not COMPLETED: schedule next check, no final persistence
-> COMPLETED: automatic player identity activation/quarantine
   -> persist safe player-game stats -> record partial/full outcome
   -> advance durable ingestion state
```

Separate from `app.workers.postgame_worker` (SportsDataIO's own,
differently-cadenced game-final/reconciliation concern) -- this worker
owns `game_postgame_ingestion_state`'s MSF-only state machine end to end.

**Dependency-injection seam, matching every existing worker's own
convention**: `fetch_boxscore` defaults to `_default_fetch_boxscore` --
real, permanent code that WOULD make a live call -- but it is never
invoked anywhere in this pass. Every test (unit and replay alike)
injects its own fake instead.

**New supporting persistence modules**:
- `app/persistence/game_postgame_ingestion_state.py` -- read/claim/
  update helpers for the table the Sunday Ingestion Foundation Build
  created but left unread. Atomic claim is the exact `UPDATE ... WHERE
  state='eligible_for_postgame_check' AND next_eligible_attempt_at <=
  now() RETURNING *` shape the migration's own comment specified,
  scoped to one `game_id` (no batch `LIMIT` needed). `ensure_scheduled_row`
  is check-then-insert, never an upsert -- never clobbers in-flight or
  terminal state.
- `app/persistence/game_events.py` (+2 functions, additive only):
  `write_raw_game_event` (writes exactly one row, returns its `id` --
  needed for `game_postgame_ingestion_state.raw_capture_id`'s FK, unlike
  the existing `write_raw_game_events`, which returns only a row count
  and is left completely unchanged for its one existing caller) and
  `read_game_event` (reads one row back by id -- the resume path's own
  requirement).
- `app/persistence/player_stats.py`: `upsert_player_stat_row_if_changed`
  extracted from `persist_player_stats`'s own inline dedup-then-insert
  logic -- identical behavior, now reusable by this worker (which
  resolves player identity per-line via `player_identity_activation`,
  not `persist_player_stats`' own batch resolve-then-persist shape).
- `app/persistence/seasons.py`: `fetch_current_season_year` extracted
  from `fetch_current_season_string` -- the shared league/season-year
  resolution, reused to build MySportsFeeds' own season-string format
  (`"{year}-{year+1}-regular"`, confirmed real from the Gate B
  diagnostic and the MSF Week 1 Identity Recovery pass) rather than
  SportsDataIO's `"{year}REG"`.
- `app/persistence/games.py`: `get_game` -- single-game-by-id read (kickoff
  for the initial `next_eligible_attempt_at` computation).
- `app/workers/msf_call_control.py`: the already-approved cadence numbers
  in one place (`FIRST_CHECK_OFFSET` = +3h30m, `FOLLOWUP_CHECK_OFFSET` =
  +1h, `HARD_CAP_ATTEMPTS` = 4, `MAX_LOCAL_TRANSIENT_RETRIES` = 2) --
  deliberately separate from `app.workers.reconciliation` (SportsDataIO's
  own, differently-shaped +10m/+30m/+2h/+24h/+72h schedule) and
  `app.workers.windows` (pre-kickoff proximity, a different axis).

All four refactors (player_stats/seasons extractions) are behavior-
preserving -- confirmed by running every existing test that exercises
them (`test_player_stats_persistence.py`, `test_gate_b_player_game_persistence.py`,
`test_season_resolver.py`, `test_postgame_worker.py`) before writing any
new code, all still green.

## 3. Exact state-transition semantics

| Situation | State after | Outcome reported |
|---|---|---|
| No row yet, not due | `scheduled` (created) | `skipped_not_eligible` |
| Row exists, not due / already claimed | unchanged | `skipped_not_eligible` |
| No `mysportsfeeds` game mapping | `capture_failed_permanent` | `capture_failed_permanent` |
| Fetch: transient failure, below hard cap | `eligible_for_postgame_check`, `next_eligible_attempt_at = now+1h` | `capture_failed_transient` |
| Fetch: transient failure, hard cap reached | `capture_failed_permanent` | `capture_failed_permanent` |
| Fetch: 401/403/400 (any attempt count) | `capture_failed_permanent` | `capture_failed_permanent` |
| Fetch succeeds, payload fails validation (wrong game id / unparseable / no `playedStatus`) | `validation_failed` (raw evidence already written, left untouched) | `validation_failed` |
| Fetch succeeds, `playedStatus != COMPLETED`, below hard cap | `eligible_for_postgame_check`, `next_eligible_attempt_at = now+1h` | `not_ready` |
| Fetch succeeds, not `COMPLETED`, hard cap reached | `capture_failed_permanent` | `capture_failed_permanent` |
| `COMPLETED`, all players resolve/persist | `confirmed_complete` | `confirmed_complete` |
| `COMPLETED`, some players quarantine, rest persist | `partially_confirmed` | `partially_confirmed` |
| `COMPLETED`, a genuine persistence failure mid-loop | **left at `validated`** (unchanged from the pre-loop write) | `persistence_failed` |
| Row already `confirmed_complete` / `partially_confirmed` / `capture_failed_permanent` / `validation_failed` | unchanged | `already_finalized` (fetch never even attempted) |
| Row at `validated` (resume) | advances to `confirmed_complete`/`partially_confirmed`/stays `validated` again on repeat failure | resumes with **zero new provider calls** |

**No schema change was needed.** `validated` -- already present in the
state enum the Sunday Ingestion Foundation Build created -- turned out
to be exactly the "persistence failure after valid raw capture -> named
recoverable state" HQ's rule 5 asked for: raw captured, game identity +
`playedStatus` confirmed COMPLETED, but per-player processing not yet
finalized. A retry re-enters at this exact state and resumes straight
into per-player processing against the SAME preserved raw body -- proven
directly by a dedicated test (`test_resume_from_validated_state_makes_zero_new_fetch_calls`).

## 4. Call-control / retry-budget implementation

- `attempt_count` increments exactly once per **completed check
  attempt** -- never per internal local transient retry, never per
  identity-activation/stat-persistence retry (HQ's explicit rule 3).
  Proven directly: `test_transient_fetch_failure_at_hard_cap_escalates_permanent`
  starts with a pre-existing `attempt_count=3`, one more tick pushes it
  to exactly 4 (hard cap), regardless of how many local sub-retries
  `_default_fetch_boxscore` would have made internally for that one tick.
- `_default_fetch_boxscore` (never invoked this pass) bounds transient
  transport errors / 429 / 5xx to `MAX_LOCAL_TRANSIENT_RETRIES = 2`
  additional attempts (3 total) before surfacing `transient_error` for
  that tick -- immediate, no artificial backoff sleep (disclosed
  judgment call: a real network round trip already spaces retries, and
  this worker's own cadence is hourly-at-tightest).
- 401/403/400 short-circuit to `permanent_error` on the FIRST response,
  never locally retried -- proven by `test_permanent_fetch_failure_escalates_regardless_of_attempt_count`.
- "Already captured/confirmed games never call again": proven
  structurally -- `test_already_finalized_game_never_calls_fetch_or_touches_anything_else`
  and the Gate B replay's own second-call test register NO route beyond
  the initial state read; any further call would raise a mock error.
- "Worker restart/redeploy must not create duplicate provider calls":
  the atomic claim (proven no-double-claim in the Sunday Ingestion
  Foundation Build's own pgTAP suite) covers concurrent workers; the
  `validated`-state resume path (zero new fetch calls, proven directly)
  covers a redeploy that lands mid per-player processing.

## 5. Raw preservation

`write_raw_game_event` is called immediately after a successful (200)
fetch, BEFORE validation and before any player/stat mutation --
`test_successful_fetch_preserves_raw_evidence_before_validation` proves
this holds even when validation subsequently FAILS (the evidence row is
written and byte-identical to the real response regardless of the
validation outcome). Nothing in this worker or its persistence layer
ever issues an UPDATE/DELETE against `game_events` -- a validation
failure moves only the durable ingestion-state row to
`validation_failed`; the raw row it already wrote is structurally
unreachable for mutation (no such call exists in this module).

## 6. Partial-player-failure semantics

Implemented exactly as specified (Section 3 table above):
`confirmed_complete` (zero quarantines) vs. `partially_confirmed` (some
quarantined, safe rows still persisted) are two different, explicit,
never-conflated outcomes -- `test_completed_one_quarantined_player_yields_partially_confirmed`
proves one team_unresolved quarantine does not block the other player's
resolution/persistence in the same game, matching Rule I from the prior
Automatic Player Identity pass. A response that's fundamentally unusable
(wrong game id, missing `playedStatus`) never reaches player processing
at all -- `validation_failed` instead.

## 7. NE@SEA Gate B replay result (zero-cost, no MSF call)

`tests/test_msf_postgame_worker_gate_b_replay.py` runs the FULL permanent
orchestration (claim -> MSF game-id resolution -> season resolution ->
injected fetch returning the real fixture -> raw preservation ->
validation -> `playedStatus` inspection -> per-player activation ->
idempotent persistence -> final state) against the real, already-
preserved NE@SEA payload:

- **69/69 real players resolved via reuse** (`resolved_players=69`,
  `quarantined_players=0`) -- the exact same live-confirmed
  provider_player_id -> canonical player_id mapping the prior Automatic
  Player Identity pass's own replay used.
- **69 stat rows persisted, 0 unchanged** (first pass), **0 duplicate**
  rows -- proven by asserting the `player_stats` POST route's own call
  count and the exact set of `player_id` values written.
- **Zero new players, zero quarantines** -- no route was even registered
  for `/rest/v1/players` (POST) or `/rest/v1/player_identity_quarantine`;
  any attempt would have raised a mock error and failed the test.
- **Raw evidence preserved exactly once**, byte-identical to the real
  fixture, confirmed via the `game_events` POST body.
- **Deterministic/idempotent rerun**: a second invocation against the
  now-`confirmed_complete` row makes **zero further calls of any kind**
  (`test_rerun_against_confirmed_complete_is_a_structural_no_op`) -- no
  fetch, no raw write, no player activation, no stat persistence.
- Ingestion state advanced `validated -> confirmed_complete`, confirmed
  directly from the sequence of states written.

## 8. Tests

**New**: 5 position-contract tests (adapter), 4 call-control tests
(pure), 9 ingestion-state persistence tests, 14 worker-level scenario
tests (every row of the Section 3 table proven individually), 2 Gate B
replay tests. **34 new tests total.**

**Full `apps/sports-intel-layer` suite**: baseline 794/794 (from the
prior Automatic Player Identity pass) plus these 34 -- **828/828
passing, zero regressions.**

## 9. SF@LAR readiness -- NOT YET FULLY READY, one concrete blocker found

Checked live against dev (project `nhwjtsdebgiwskshzqiq`) before writing
this report:

| Requirement | Status |
|---|---|
| Canonical game exists, MSF game id known | **READY** -- `game_provider_ids` maps `50d14afd-...` <-> MSF `163542` (from the MSF Week 1 Identity Recovery pass) |
| SF/LAR canonical team ids known | **READY** -- both teams exist in `teams` |
| SF/LAR MSF **numeric** team identity | **READY** -- `team_provider_ids` holds SF=`78`, LAR=`77` (from the Sunday Ingestion Foundation Build's 32-team backfill) |
| SF/LAR MSF **abbreviation** team identity | **MISSING** -- see below |
| Permanent worker code | **READY** -- built and proven this pass (zero-cost replay) |
| `game_postgame_ingestion_state` row for this game | **Does not exist yet** -- not a blocker, the worker creates it automatically (`scheduled`, `next_eligible_attempt_at = kickoff+3h30m`) on its first invocation |

**The blocker**: `parse_game_boxscore`'s `PlayerStatLine.team` field
carries MySportsFeeds' own boxscore-response team **abbreviation**
(confirmed real from Gate B: `"NE"`/`"SEA"`), and
`activate_msf_player`'s team-resolution step
(`resolve_team_ids(provider_name="mysportsfeeds", provider_team_ids=[line.team])`)
resolves against that same abbreviation scheme. **Neither SF nor LAR has
an abbreviation-scheme `mysportsfeeds` row in `team_provider_ids` --
only the numeric scheme.** This gap was already disclosed (not newly
discovered) in the 2026-09-11 MSF Week 1 Identity Recovery report
("LAR MSF team identity: numeric id 77, abbreviation `"LA"` -- **not
yet** in `team_provider_ids`") and confirmed still open by this pass's
own live query. Left uncorrected, a live SF@LAR capture today would
resolve zero players and quarantine all 69+ of them on
`team_unresolved` -- `partially_confirmed` at best, likely
functionally empty.

**The fix is small, real, and NOT made this pass** (no schema change,
same idempotent backfill pattern already used for the other 12 teams'
abbreviation rows and all 32 teams' numeric rows): two new
`team_provider_ids` rows, `(SF team_id, 'mysportsfeeds', 'SF')` and
`(LAR team_id, 'mysportsfeeds', 'LA')` -- both real, already-confirmed
provider values, not new evidence to recover. This is the one remaining
step before a live SF@LAR call can be authorized.

## Out of scope, exactly as instructed

No live MySportsFeeds call was made. No Sunday enablement. No staging
or production changes. No Context Intelligence. No recommendation
changes. The pre-existing, unrelated Proof 1b test debt was not touched
(did not block this pass).
