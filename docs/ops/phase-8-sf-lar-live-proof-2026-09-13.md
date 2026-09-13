# SF@LAR Live Proof (2026-09-13)

MANSA HQ directive: "SF@LAR LIVE PROOF — AUTHORIZED." The first live
execution of the permanent MSF postgame ingestion path, for canonical
game `50d14afd-2861-4e07-b235-90ea857f004d` (MSF game 163542, SF @ LAR).
**DEV only. Exactly one real MySportsFeeds boxscore request was made.**

## Mechanism: the permanent worker, not diagnostic-flavored logic

Two things were built:

1. **`POST /v1/internal/msf-postgame/run`** (`app/main.py`) — a permanent,
   reusable HTTP endpoint calling `run_msf_postgame_capture` directly, in
   the exact same "thin HTTP-to-function adapter" shape as every other
   `/v1/internal/*/run` endpoint in this service. This stays in the
   codebase permanently as the correct future invocation surface (Sunday
   included, not enabled by this pass).
2. A **temporary one-shot startup trigger**, gated behind
   `RUN_MSF_POSTGAME_SF_LAR_LIVE_PROOF` and reverted immediately after
   use. This was necessary only because this session has no way to read
   back `INTERNAL_SERVICE_TOKEN`'s real value from Railway to
   authenticate an HTTP call against the permanent endpoint above — the
   trigger sidesteps that by calling `run_msf_postgame_capture` directly
   from inside the already-credentialed running process. It reimplements
   nothing: 100% of the real behavior (claim, MSF fetch, raw
   preservation, validation, identity activation, persistence, state
   advancement) is the same permanent worker code the HTTP endpoint also
   calls. Guarded by the same `activation_run_markers` idempotency
   mechanism every prior MSF diagnostic in this project has used.

Both were deployed to `sports-intel-layer`/dev (auto-deploy from `dev`),
fired once, verified, and the temporary trigger was fully reverted
(module + hook + its test deleted, flag reset to `"0"`) — the permanent
endpoint remains.

## Exact provider call count: 1

`game_postgame_ingestion_state.attempt_count = 1` after the run.
Railway deploy logs show a single `SF_LAR_LIVE_PROOF_START` →
(~2 minutes of real work) → `SF_LAR_LIVE_PROOF_RESULT` cycle, consistent
with exactly one real MSF boxscore HTTP round trip (no local
transient-retry loop was needed — the first response succeeded).

## HTTP/result metadata

- `last_http_status`: **200**
- Raw capture: **`game_events.id = 91aaf3b3-f681-4b93-b616-f632947cbb4a`**,
  `provider_name = 'mysportsfeeds'`, `captured_at = 2026-09-13 15:58:50 UTC`
- `raw_payload->'provider_game_id' = "163542"`, matching the requested
  MSF game exactly (validation passed)

## playedStatus / final score

`raw_payload->'body'->'game'->'playedStatus' = "COMPLETED"`. Real final
score, read directly from the preserved raw payload's own `scoring`
block: **San Francisco 49ers 27, Los Angeles Rams 7** (SF is the away
side, numeric MSF id 78, `awayScoreTotal: 27`; LAR is home, numeric MSF
id 77, `homeScoreTotal: 7`) — both numeric ids match the already-known,
already-persisted real mapping exactly.

## Player count / identities

- **95 real players** appeared in this boxscore (34 fewer/more than
  Gate B's NE@SEA 69 -- a different game, different real roster count,
  not a discrepancy).
- **Identities reused: 0.** Every one of these 95 provider_player_ids
  had never been seen by MANSA before this call (neither SF nor LAR had
  any players in the system prior to this run, aside from one unrelated
  seed fixture -- see discrepancy note below).
- **New canonical players created: 95.** Confirmed two ways: (1)
  `resolved_players = 95` in the worker's own result, all via the create
  path (Rule A/C/E, numeric-first team resolution — SF=78/LAR=77, no
  abbreviation rows needed, confirming this pass's own Pre-Live
  Hardening); (2) directly counting `player_provider_ids` rows newly
  linked for these 95 `player_stats` rows, all `provider_name =
  'mysportsfeeds'`.
- **Quarantined players: 0.** `player_identity_quarantine` has zero rows
  for this `game_id` — no `team_unresolved`, no `ambiguous_match`, no
  `id_collision`, no `malformed_identity`, no `team_identity_conflict`.

## Player-game rows persisted

**95 `player_stats` rows**, 95 distinct `player_id` values — exactly
matching `resolved_players`/`persisted_rows` from the worker's own
result, zero `unchanged_rows` (first-ever capture, nothing to compare
against).

## Ingestion final state

`game_postgame_ingestion_state`: **`state = 'confirmed_complete'`**,
`attempt_count = 1`, `error_classification = null`, `last_error = null`,
`quarantine_reason = null` (zero quarantines, so none needed). The
`validated → confirmed_complete` transition happened in the same tick —
no partial-persistence failure occurred, so the `validated`-state resume
path was not exercised live this pass (it remains proven by the existing
test suite from the Permanent Box Score Worker Build pass).

## Duplicate rows: zero

Confirmed after firing the trigger a **second time** (via a real Railway
service restart, same deployment, same code, same flag still set) --
see idempotency section below. `game_events` still has exactly 1 row for
this game; `player_stats` still has exactly 95 rows; `game_postgame_ingestion_state.attempt_count`
and `.updated_at` are byte-identical to the first run's values.

## Idempotency / reprocessing result — proven live, no second provider call

After the first execution, the `sports-intel-layer`/dev service was
**restarted in place** (Railway `restart-service`, no rebuild, same
running image, same `RUN_MSF_POSTGAME_SF_LAR_LIVE_PROOF=1` flag still
set) to force a second real startup-hook attempt:

- First run: `SF_LAR_LIVE_PROOF_START` at `15:58:49.819` →
  `SF_LAR_LIVE_PROOF_RESULT` (`confirmed_complete`) at `16:00:49.876`
  (~2 minutes, consistent with a real network round trip + 95-player
  processing).
- Second run (after restart): `SF_LAR_LIVE_PROOF_START` at
  `16:05:02.5157` → `SF_LAR_LIVE_PROOF_RESULT`
  (`{"skipped": true, "reason": "run_key ... already claimed -- skipping
  duplicate run"}`) at `16:05:02.5157` — **under 1 millisecond**, proving
  no MySportsFeeds call and no worker invocation happened at all.
- Directly confirmed in the database: `attempt_count` still `1`,
  `updated_at` unchanged from the first run, `game_events` row count
  unchanged (1), `player_stats` row count unchanged (95).

This proves the specific property this pass's own trigger guarantees
(no duplicate call on redeploy/restart). The complementary property —
that the permanent worker's own `_ALREADY_FINALIZED_STATES` short-circuit
independently guarantees the identical zero-call outcome for ANY future
caller of `run_msf_postgame_capture` against this now-`confirmed_complete`
game (including the permanent HTTP endpoint, with no dependence on this
pass's own trigger's marker) — is not re-demonstrated live here since it
was already proven directly, repeatedly, in the Permanent Box Score
Worker Build pass's own test suite
(`test_already_finalized_game_never_calls_fetch_or_touches_anything_else`,
`test_rerun_against_confirmed_complete_is_a_structural_no_op`) and is
unchanged by anything in this pass.

## Discrepancy between MSF and MANSA canonical data

One expected, **by-design** discrepancy, not a bug: MANSA's canonical
`games` row for this game still reads `status = 'live'`,
`final_score = null`, `finalized_at = null` — all stale. This MSF
pipeline deliberately never writes to those columns (they belong to
SportsDataIO's own, separate `postgame_worker.py` pipeline); MSF's own
completion signal is `game_postgame_ingestion_state.state`, which now
correctly reads `confirmed_complete`, exactly matching the original
ingestion design's own stated principle ("`games.status` is never
authoritative for 'is this game over' — only a provider's own
`playedStatus` is"). Team/home-away orientation shows **zero**
discrepancy: SF=away/numeric 78, LAR=home/numeric 77 in both MSF's raw
payload and MANSA's canonical `games` row, byte-consistent.

One unrelated data-hygiene note, fully explained, not a bug: `players`
now shows 48 rows for each of SF/LAR (96 total), one more than the 95
distinct players in this game's `player_stats`. The extra row is a
pre-existing, unrelated seed/test fixture (`"Seed QB Niners"`, id
`a4000000-0000-0000-0000-000000000005`) that predates this pass and
correctly did not appear in the real boxscore (it isn't a real player).

## Tests / regressions

Full `apps/sports-intel-layer` suite, run before deploying and again
after reverting the temporary trigger: **861/861 passing both times**
(3 new permanent tests for the HTTP endpoint added and kept; the 2
temporary hook-wiring tests were added, then removed on revert, net
861 = the pre-existing 858 + 3 permanent). Zero regressions at any point
in this pass.

## Does this prove the permanent worker safe enough for today's 13-game DEV enablement?

**Partially — the ingestion mechanics are proven; the fleet-scale
question is not, and Sunday enablement is explicitly not authorized by
this pass.** What this one real, live, end-to-end run proves:

- The full pipeline (claim → resolve → fetch → preserve raw → validate
  → inspect `playedStatus` → numeric-first identity activation →
  idempotent persistence → durable state advancement) works correctly
  against a real, previously-untested MSF game and a previously-
  untested pair of teams (SF/LAR), not just the NE@SEA fixture this
  session had already replayed dozens of times.
- Numeric-first team resolution works exactly as hardened: 95/95 real
  players safely created with zero quarantines, using ONLY the numeric
  MSF team identity — no abbreviation-scheme data existed or was needed
  for either team, directly confirming the Pre-Live Worker Hardening
  pass's own central claim under real conditions, not just synthetic
  tests.
- Idempotency/no-duplicate-call-on-restart is proven live, not just
  asserted.

**What remains unproven and explicitly out of this pass's scope:**
call-control behavior across a real multi-game slate sharing the same
worker invocation cadence; the cache/rate-aware scheduling paths
(`Cache-Control`/`Retry-After`) under a real not-yet-COMPLETED or
429 response (this one call was a first-try 200/COMPLETED, so neither
path was exercised live); concurrent-invocation behavior across several
games at once; and the actual per-game MSF game-id/team mappings for
the other 12 Sunday games (not verified this pass). Sunday enablement
remains a separate, later, explicitly not-yet-authorized decision.

## Out of scope, exactly as instructed

DEV only. Exactly one live MySportsFeeds call. No second game called.
No Sunday enablement. No staging/production. No Context Intelligence.
No recommendation changes. No manual data patching of any kind — every
number in this report is the system's own real, live output.
