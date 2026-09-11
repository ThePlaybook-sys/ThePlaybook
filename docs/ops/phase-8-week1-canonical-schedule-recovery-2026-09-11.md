# Week 1 Canonical Schedule Recovery (2026-09-11)

MANSA HQ directive: "WEEK 1 CANONICAL SCHEDULE RECOVERY." One real,
HQ-authorized BALLDONTLIE `nfl/v1/games` call (`weeks=[1]`) to recover the
real provider game ids for the 11 canonical Week 1 games the 2026-09-07
calibration pass intentionally left unseeded
(`docs/ops/phase-8-sunday-canonical-game-coverage-audit-2026-09-11.md`).
Exactly one provider request authorized and made -- no MSF calls, no
boxscore calls, no schema change, no Sunday worker built.

## What was built and fired

Same temporary-diagnostic-then-revert pattern as every prior live-call
pass this project has run (Gate B included): a gated module
(`RUN_BALLDONTLIE_WEEK1_SCHEDULE_RECOVERY`), the existing, standing
`build_real_balldontlie_client()` (already used elsewhere in this
project, not recreated), the same `activation_run_markers` idempotency
guard. **The one deliberate difference from the 2026-09-07 probe, per
HQ's explicit instruction**: the full raw response is persisted durably
via the existing, unmodified `app.persistence.game_events.
write_raw_game_events` -- not logged to Railway and left there. That
probe's raw payload was never recoverable from anything persisted
(confirmed by the coverage audit); this one is, permanently, in
`game_events`.

10 new tests (respx-mocked, zero live calls) written and passing before
the flag was ever set; full suite 793/793 before firing. Fired via one
`set-variables` call (deploy allowed, since a deploy was the explicit
point), confirmed via `list-deployments` (`SUCCESS`), flag reset to
`"0"` (`skipDeploys: true`) immediately after. Diagnostic module, its
test file, and the startup hook were then fully reverted (deleted/
removed) -- matching this project's dominant precedent (every prior
temporary diagnostic except Gate B's own game_boxscore probe has been
fully reverted after use) -- full suite re-confirmed 783/783 after
revert, zero regressions.

## The one real call: result

**HTTP 200. 16 games found. Raw response durably persisted**
(`game_events`, anchored to the pre-existing SEA/NE canonical `game_id`
per this pass's own disclosed modeling choice -- `write_raw_game_events`
requires a single `game_id` and this response covers all 16; `raw_payload`
is un-normalized jsonb, so this choice affects no other game's data).
`games_found: 16` recorded both in the redacted log summary and the
persisted evidence envelope itself.

## Validation: the expected 16-game universe

The persisted raw response's 16 games, read back (no new call):

| Game | Kickoff (UTC) | Provider id |
|---|---|---|
| NE @ SEA | 2026-09-10 00:20 | 1392216 |
| SF @ LAR (Thursday, Melbourne) | 2026-09-11 00:35 | 1392217 |
| CHI @ CAR, BAL @ IND, ATL @ PIT, CLE @ JAX, TB @ CIN, NYJ @ TEN, NO @ DET, BUF @ HOU (1:00 PM ET) | 2026-09-13 17:00 (all 8) | 1392218-1392225 |
| MIA @ LV, GB @ MIN, WAS @ PHI, ARI @ LAC (4:25 PM ET) | 2026-09-13 20:25 (all 4) | 1392226-1392229 |
| DAL @ NYG (SNF) | 2026-09-14 00:20 | 1392230 |
| DEN @ KC (MNF) | 2026-09-15 00:15 | 1392231 |

Exactly the 16-game universe HQ named (NE@SEA + SF@LA + 13 Sunday +
DEN@KC), confirmed field-by-field: provider game id, away team, home
team, kickoff timestamp, and week/season-type (`week: 1`, `season: 2026`
on every row) all present and consistent.

**One naming note, disclosed not silently normalized**: BALLDONTLIE's own
abbreviation for the Jacksonville Jaguars is `JAX` (HQ's message used
`JAC`) and for the Washington Commanders is `WSH` (the already-seeded
canonical row for this team uses `WAS`, from the 2026-09-07 pass). Both
are the same real team in both cases -- `games.home_team`/`away_team` are
plain text, not FK'd to `teams`, so this is a display-convention question,
not an identity question. This pass used `WAS` for Washington (matching
the already-established convention on the existing row, for internal
consistency) and BALLDONTLIE's own `JAX` for Jacksonville (no prior
`games` row existed to establish a different convention). Worth a project-
wide abbreviation-standard decision at some point; not a blocker for
anything in this pass.

## Reconciliation against the existing 5 canonical rows

All 5 already-canonical real games were checked against this real
response -- **all 5 match provider reality exactly**: home/away, kickoff
timestamp, week/season all correct, **and all 5 already carry a correct
`game_provider_ids` (`balldontlie`) row** (including the SEA/NE opener,
whose mapping to id `1392216` already existed and matches this response
exactly) -- so, per HQ's explicit instruction #7, **none of the 5 were
touched.**

**One real discrepancy found, disclosed, and deliberately NOT
auto-corrected this pass (per #7)**: the SEA/NE opener's local `games.status`
column still reads `'scheduled'`, though the real game is long final (this
response's own `status_state: "final"`) and its complete boxscore has
already been captured and 69/69 player-game stats persisted in the two
prior Phase 8 passes. This is exactly the kind of "canonical row gone
stale relative to newer provider/internal reality" gap named in the new
Technical Debt & Feature Backlog entry below -- surfaced here, not fixed,
since fixing it would be modifying one of the "existing 5" outside this
pass's authorized scope.

## Activation: the 11 genuinely missing games

Built and executed one atomic, idempotent SQL statement (the same
`WITH ... WHERE NOT EXISTS` CTE pattern already proven in the Full Game
Player Activation pass) creating exactly the 11 missing `games` rows and
their `game_provider_ids` (`balldontlie`) mappings -- reusing the real,
just-captured provider ids, real team abbreviations, real kickoff
timestamps, and real venue names (`stadium`, taken directly from the raw
response's own `venue` field) verbatim. `venue_lat`/`venue_long`/
`venue_type`/`venue_id` were left null for all 11 -- those fields are not
present in BALLDONTLIE's schedule response for the existing 5 either
(they were populated by a later, separate pass), and this pass does not
invent them.

**Idempotency/collision design, exactly as HQ specified:**
- A **provider-id collision guard** on `game_provider_ids` (`WHERE NOT
  EXISTS ... provider_name = 'balldontlie' AND provider_game_id = X`) --
  never overwrites an existing different mapping, and doubles as the
  rerun-safety guard.
- A **matchup/kickoff conflict guard** on `games` (`WHERE NOT EXISTS ...
  home_team = X AND away_team = Y AND scheduled_start = Z`) -- a canonical
  row is only ever created if no existing row already claims that exact
  matchup and kickoff.
- The `game_provider_ids` insert only fires for games that were actually
  just inserted (`EXISTS (SELECT 1 FROM inserted_games ...)`) -- a game
  that failed its conflict guard gets no orphaned provider mapping either.

**Verified live**: all 11 provider ids (1392217-1392225, 1392230,
1392231) were genuinely new (zero collision with the 5 already-mapped
ids) and all 11 matchup/kickoff tuples were genuinely new (zero conflict
with any of the 12 pre-existing rows, seed fixtures included) -- so all
11 inserted cleanly on the first run. **Rerunning the identical statement
a second time inserted zero rows in either table** -- idempotency proven,
not asserted.

## Proofs (all run live against dev, not asserted)

| # | Claim | Result |
|---|---|---|
| 1 | Exactly 16 real Week 1 canonical games | **16** (`games` joined to `game_provider_ids` where `provider_name='balldontlie'`, `season_type='regular'`, `week=1`) |
| 2 | All 16 have BALLDONTLIE provider mappings | **16/16** |
| 3 | Exactly 13 games on Sunday Sept 13 | **13** (ET-anchored window, `2026-09-13T04:00:00Z` to `2026-09-14T04:00:00Z` -- the naive UTC-calendar-day window undercounts to 12, since the 8:20 PM ET SNF kickoff falls at `2026-09-14T00:20:00Z`; noted and corrected during verification, not glossed over) |
| 4 | SF @ LA represented correctly | **LAR (home) / SF (away)**, confirmed |
| 5 | DEN @ KC represented correctly | **KC (home) / DEN (away)**, confirmed |
| 6 | Home/away correct for all 16 | **16/16**, byte-for-byte against HQ's official list (`away @ home` convention) |
| 7 | Zero duplicates | **0** duplicate `provider_game_id`s, **0** duplicate `(home_team, away_team, scheduled_start)` tuples |
| 8 | Seed/test fixtures untouched | **4/4** still present, `manual_seed=false`, synthetic `seed-game-*` ids, distinct from all real rows |
| 9 | Idempotent rerun | **0 new rows** in either table on an identical second execution |

`games` table total: **23** rows (4 unrelated seed fixtures + 3 unrelated
October-cluster rows + 16 real Week 1 games) -- accounts for every row,
zero unexplained growth.

## Tests

10 new tests for the temporary diagnostic (all respx-mocked, zero live
calls in the test suite): 793/793 passing before the live call. After
reverting the diagnostic module/tests/hook: 783/783 passing, zero
regressions.

## Architectural requirement recorded, per HQ's explicit instruction

Added to `docs/blueprint/engineering-roadmap-build-order.md`'s Technical
Debt & Feature Backlog (Immediate category): MANSA has no mechanism that
reconciles canonical `games` against an authoritative provider schedule
and surfaces missing/duplicate/conflicting/stale rows -- this incident
was only caught because HQ manually cross-checked the real schedule, not
because MANSA's own architecture detected a 5-of-16 gap. The stale
`status='scheduled'` row found on the SEA/NE opener during this pass's
own reconciliation step is recorded as the concrete illustration of the
"stale" category specifically. Not designed or built this pass -- entry
exists so a future pass can scope it deliberately rather than rediscover
the need from scratch.

## Out of scope, exactly as instructed

No MSF call. No boxscore call. No schema change (both `games` and
`game_provider_ids` already existed and already supported everything
this pass needed). No recommendation/Context Intelligence change. No
Sunday ingestion worker built. Staging and production untouched
throughout.
