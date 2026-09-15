# MSF Pause / Backlog-Safe Provider State (2026-09-15)

MANSA HQ directive: "MSF PAUSE / BACKLOG-SAFE PROVIDER STATE." MySportsFeeds
is being intentionally canceled/paused for cost reasons -- a deliberate
business decision, not a failure. This pass implements a clean,
distinguishable pause mechanism for the postgame dispatcher, confirms
backlog safety and bounded recovery, audits (without weakening) 401/403
credential-error detection, checks DEN@KC, and documents the full provider
lifecycle. **The MSF postgame pipeline itself is not redesigned, removed,
or otherwise touched beyond the pause check.** Zero provider calls made by
this pass. Zero manual DEN@KC action.

## 1. DEN@KC -- current/final status

Checked live before any code change (real time at check: 2026-09-15
09:40:21 UTC). **Already `confirmed_complete`**, finished by the existing,
unmodified automation hours before this pass began -- no decision about
"letting the in-flight job finish" was needed:

| Field | Value |
|---|---|
| `state` | `confirmed_complete` |
| `attempt_count` | 2 |
| `updated_at` | 2026-09-15 05:01:45 UTC |
| `next_eligible_attempt_at` | 2026-09-15 04:46:27 UTC |
| `last_http_status` | 200 |
| `last_error` | null |
| `error_classification` | null |
| `raw_capture_id` | `5bfe1b5f-c513-47f3-b9b3-e4e77f35bc72` |
| `player_stats` rows | 79 |
| Quarantines | 0 |
| `raw_captures` (game_events) | 2 (matches `attempt_count` exactly -- no duplicates) |

## 2. `MSF_POSTGAME_ENABLED` -- implementation

**Location**: `apps/sports-intel-layer/app/workers/msf_postgame_dispatcher.py`,
the same module every prior pass this session extended -- no new module,
service, cron, or table.

- New `MSF_POSTGAME_ENABLED_ENV_VAR = "MSF_POSTGAME_ENABLED"` constant and
  `_msf_postgame_enabled() -> bool` helper: unset, empty, or any value
  other than a case-insensitive `"false"` means **enabled**. Deliberately
  fails open -- a missing or misconfigured variable can never silently
  stop ingestion; only an explicit `"false"` pauses it.
- The check runs as the **very first thing** `dispatch_due_msf_postgame_games`
  does, before Phase 1 (enrollment) or Phase 2 (dispatch), before any
  Supabase query at all. When paused: one `_logger.warning(...)` log line
  naming the pause explicitly as intentional (not an error), and an
  immediate `return DispatchResult(considered=0, paused=True)` -- full
  no-op, zero HTTP calls of any kind.
- `DispatchResult` gained `paused: bool = False`.
- `app/main.py`'s `DispatchMSFPostgameResponse` gained `paused: bool`,
  wired straight through from the dispatcher's own result -- same
  thin-adapter discipline as every other field on that endpoint.
- Module docstring gained a full "Provider Pause State" section
  documenting the complete lifecycle (see Section 6 below) and citing
  exactly why 401/403 handling and bounded recovery needed no code change
  (Sections 4 and 3).

## 3. Proof: paused mode exits cleanly and makes zero provider calls

Six new tests in `tests/test_msf_postgame_dispatcher.py`, one new test in
`tests/test_msf_postgame_endpoint.py`:

- `test_dispatch_paused_returns_clean_zero_result` -- `MSF_POSTGAME_ENABLED=false`
  returns `paused=True`, `considered=0`, every list field empty, no
  exception raised.
- `test_dispatch_paused_makes_zero_http_calls` -- **no respx route
  registered at all**; any HTTP call the function made (enrollment
  discovery, selection, `ensure_scheduled_row`, or the worker's own
  Supabase reads/writes) would raise respx's own unmocked-request error.
  `ensure_scheduled_row` and `run_msf_postgame_capture` are also
  monkeypatched to raise `AssertionError` if called at all -- neither
  fires.
- `test_dispatch_paused_case_insensitive_false` -- `"false"`, `"False"`,
  `"FALSE"`, `"fAlSe"` all pause.
- `test_dispatch_unset_env_var_preserves_existing_enabled_behavior` --
  regression proof: with the variable unset, behavior is byte-identical
  to every pre-pause-feature test in this file (`paused=False`, normal
  discovery/selection/dispatch).
- `test_dispatch_non_false_values_are_treated_as_enabled` -- `"true"` and
  by extension any non-`"false"` string is treated as enabled (fail-open
  proof).
- `test_dispatch_passes_through_paused_flag` (endpoint file) -- the real
  HTTP boundary passes a mocked `paused=True` `DispatchResult` through to
  the JSON response unchanged.

**Full `apps/sports-intel-layer` suite: 890 collected, 885 passing** --
the same 5 pre-existing, unrelated `test_odds_cadence_persistence.py`
failures disclosed in every prior pass this session, confirmed unrelated
again (this pass touched none of that module).

Because paused mode never reaches any Supabase call, it structurally
cannot increment `attempt_count`, mark a game failed, quarantine a
player, or alter any terminal row -- there is no code path between the
pause check and any such mutation for this to prove beyond "zero HTTP
calls," which the test above already establishes at the transport layer.

## 4. Backlog safety and bounded recovery -- audited, not rebuilt

No new code was needed for either property; both already exist and were
re-verified against the pause design rather than re-implemented:

- **Backlog is never lost while paused.** `select_unenrolled_eligible_games`
  and `select_due_msf_postgame_games` are both pure re-derivations from
  persisted `games`/`game_provider_ids`/`game_postgame_ingestion_state`
  data every time they run -- never from in-memory dispatcher state. A
  game that becomes newly eligible for enrollment or newly due for
  capture during a pause is simply not discovered or acted on that tick;
  it remains exactly as eligible on every later tick. No hard-coded date
  range is involved anywhere in either query, so auto-discovery on
  re-enable requires no configuration.
- **Bounded recovery after re-enable.** `MAX_ENROLLMENTS_PER_DISPATCH_TICK=20`
  and `MAX_GAMES_PER_DISPATCH_TICK=2` already bound every tick's work
  regardless of backlog size, and both selection queries are already
  oldest-first ordered (`select_unenrolled_eligible_games` by
  `scheduled_start` ascending; `select_due_msf_postgame_games` by
  `next_eligible_attempt_at` ascending, nulls/`validated` first). A large
  backlog drains in oldest-kickoff-first order across as many ticks as it
  takes, exactly the existing Volume 2 §1.1 principle #11 bounded-workload
  discipline this session already locked in -- no new scheduler, cap, or
  table was built or is needed.

## 5. 401/403 (invalid-credential) behavior -- audited, not changed

Confirmed by re-reading `_default_fetch_boxscore`
(`app/workers/msf_postgame_worker.py`, unmodified this pass): a real
MySportsFeeds 401/403 is already classified as `status="permanent_error"`,
which `run_msf_postgame_capture` already turns into a durable
`capture_failed_permanent` row with `error_classification="permanent"`
and the real `last_http_status` (401 or 403) preserved.

This is already cleanly distinguishable from an intentional pause with
**zero code change required**:

| | Intentional pause | Real credential failure |
|---|---|---|
| `DispatchResult.paused` | `True` | `False` |
| Rows touched | none | the specific game's row -> `capture_failed_permanent` |
| `last_http_status` | untouched (no HTTP call made) | `401`/`403`, persisted |
| Log signal | one `_logger.warning` naming the pause explicitly | the worker's own existing error path |
| Provider calls made | zero | one (the failing call itself) |

No change was needed or made to `_default_fetch_boxscore`,
`run_msf_postgame_capture`, or any persistence function -- the two states
were already structurally distinct before this pass, and the new pause
check adds a distinction one layer above (whether the worker is even
reached at all) without touching that existing distinction.

## 6. Full provider lifecycle (documented, non-error at every stage)

Recorded in the dispatcher module's own docstring (see the new "Provider
Pause State" section) and summarized here:

1. **ACTIVE** -- `MSF_POSTGAME_ENABLED` unset/true. Normal operation, as
   built by every prior pass this session.
2. **PAUSED** -- `MSF_POSTGAME_ENABLED=false`. Every tick is a clean,
   logged, zero-call no-op.
3. **Backlog accumulates safely** -- games that would have been enrolled
   or dispatched simply wait, discoverable exactly as any existing
   backlog item already is (this session's own NE@SEA discovery is the
   live proof this discovery path already handles an arbitrarily old
   backlog correctly).
4. **RE-ENABLED** -- variable set back to unset/true, or removed. The
   very next scheduled tick resumes both phases exactly as if no pause
   had happened -- no special "resume" code path exists or is needed,
   because there was never a separate paused *data* state, only a paused
   *dispatcher entry point*.
5. **Bounded recovery** -- the existing per-tick caps and oldest-first
   ordering drain the backlog across as many ticks as it takes (Section
   4), never a single unbounded burst.
6. **Current operation** -- once drained, ticks look identical to state 1
   again.

None of these states is an error state; only a real infra failure
(`MSFPostgameDispatcherError`, an unhandled Supabase read failure) or a
real per-game outcome recorded in `DispatchResult.results` represents an
actual problem.

## 7. Exact Railway variable to set

**Service: `sports-intel-layer`** (not `cron-msf-postgame`). The pause
check lives inside `dispatch_due_msf_postgame_games`, which executes
inside `sports-intel-layer`'s own process when `cron-msf-postgame` POSTs
to `POST /v1/internal/msf-postgame/dispatch` -- `sports-intel-layer` is
the process that reads its own environment via `os.environ.get(...)`, so
the variable must be set there, not on the calling cron service.

**Variable**: `MSF_POSTGAME_ENABLED=false`

**Not flipped by this pass.** Per HQ's own instruction, this pass
implements/tests/documents the mechanism and reports the exact change
needed -- it does not touch the live Railway variable. `skipDeploys: true`
applies if/when this variable is actually set (a variable-only change,
no deploy required for the running process to pick it up on its next
cold start/restart -- note: because `sports-intel-layer` is a
long-running service, not a cron job, a plain variable set does NOT
retroactively affect an already-running process without a restart;
Railway's own variable-change behavior for long-running services should
be confirmed before flipping this in production-equivalent environments).

## 8. Safety recommendation on immediate cancellation

**Safe to cancel MySportsFeeds now, conditioned on setting
`MSF_POSTGAME_ENABLED=false` on `sports-intel-layer` first (or
simultaneously) with the cancellation**, for these reasons:

- The integration is already proven end-to-end at real scale: 13/13
  Sunday games + DEN@KC + NE@SEA, 1,292+ real player-stat rows across
  this session, 0 quarantines, 0 duplicates, 0 unrecovered errors.
- The pause mechanism is a true no-op with zero Supabase side effects
  when engaged (Section 3) -- setting it before/with cancellation means
  the dispatcher stops trying to call a provider that will imminently
  reject every request, avoiding a burst of real 401/403s (harmless,
  since Section 5's handling is already correct and durable, but
  needless).
- Nothing about pausing or cancellation loses any data: every currently-
  `scheduled`/`eligible_for_postgame_check`/`validated` row, and every
  future game that would have been auto-enrolled, remains fully
  discoverable and will be picked up automatically and safely the moment
  `MSF_POSTGAME_ENABLED` is unset/re-enabled and MySportsFeeds access (if
  ever restored) is available again.
- If `MSF_POSTGAME_ENABLED` is NOT set before cancellation, the dispatcher
  will simply keep trying and receiving real 401/403 responses on its
  existing schedule -- already safely handled per Section 5 (durable
  `capture_failed_permanent` rows, no crash, no quarantine, no bad data)
  but noisy and pointless. Setting the pause flag first is a cleanliness
  improvement, not a data-safety requirement -- the system does not
  strictly need it to avoid harm, only to avoid needless real HTTP calls
  against a canceled account.

## Out of scope, exactly as instructed

No Context Intelligence. No recommendation work. No provider calls beyond
already-running authorized automation (zero made by this pass). No
unrelated cleanup. No redesign or removal of the MSF postgame pipeline.
No manual DEN@KC action (moot -- already `confirmed_complete`). The live
`MSF_POSTGAME_ENABLED` Railway variable was **not** flipped by this pass.
