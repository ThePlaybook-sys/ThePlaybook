# Phase 8 Player-Game Persistence Design + Implementation (2026-09-10)

MANSA HQ directive: "PHASE 8 PLAYER-GAME PERSISTENCE DESIGN +
IMPLEMENTATION PASS," authorized after Gate B's PASS. Works exclusively
from the preserved real Gate B payload (game 163541, NE @ SEA,
`playedStatus: "COMPLETED"`) -- **no new MySportsFeeds request was made
this pass.**

## 1. Schema audit -- existing `player_stats` model reused, unchanged

`player_stats(id, player_id, game_id, stats jsonb, created_at)` (Phase
3E-8), append-only via `block_snapshot_updates()` (Phase 3F-3), with the
Phase 8.3A widening (`game_id` nullable, `season_id` added, `check
(game_id is not null or season_id is not null)`). Existing readers/
writers inspected: `app.persistence.player_stats.persist_player_stats`
(the one production writer -- correction-aware, idempotent: inserts only
when incoming stats differ from the latest row for a (game, player)
pair), `app.persistence.player_season_stats` (the season-scoped sibling,
already provider-parameterized), `app.workers.postgame_worker` (the one
existing caller, SportsDataIO only).

**No concrete integrity problem exists in `player_stats` itself.** The
only real gap found was `persist_player_stats`'s own hardcoded
`_PROVIDER_NAME = "sportsdataio"` module constant -- a code limitation,
not a schema one. Fixed minimally: `provider_name` is now a keyword
parameter (default `"sportsdataio"`, zero behavior change for the
existing Postgame Worker call site), threaded into the already
provider-neutral `resolve_game_ids`/`resolve_player_ids`. **No new
schema, no new table, no new migration.**

Checked and confirmed already live (not assumed): `game_provider_ids`,
`player_provider_ids`, and `team_provider_ids`'s `provider_name` check
constraints all already allow `'mysportsfeeds'` (widened in
`20260908150000_mysportsfeeds_provider_identity.sql` and
`20260909190200_mysportsfeeds_game_provider_ids.sql`, both prior passes)
-- no further constraint widening needed for this pass.

## 2. Adapter: `app.adapters.providers.mysportsfeeds_game_boxscore`

New file, **pure parsing function** (`parse_game_boxscore(payload: dict)
-> AdapterResponse[list[PlayerStatLine]]`, no network I/O), built only
against the real, committed fixture
`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`.
Parses `stats.{away,home}.players[]` (34 + 35 = 69 real players) into
provider-neutral `PlayerStatLine` objects: `game_external_id` = MSF's
own `game.id` (163541), `player_external_id` = MSF's own `player.id`,
`team` = the real `game.{away,home}Team.abbreviation`, `stats` = the
player's entire real `playerStats[0]` block, verbatim.

## 3. Unreliable fields -- disclosed structurally, never silently trusted

Gate B's real payload showed `snapCounts.{offenseSnaps,defenseSnaps,
specialTeamSnaps}` and `miscellaneous.gamesStarted` as **uniformly zero
across all 69 players and both team totals**, including players with
real, substantial performance elsewhere in the same response (Drake
Maye: 178 pass yards / 47 rush yards, 0 offense snaps). Per HQ's
explicit instruction, these raw values are preserved untouched
(provenance-preserving) but every persisted `stats` dict gets one
MANSA-authored sibling key, `_unreliable_fields` (`["snapCounts",
"miscellaneous.gamesStarted"]`) plus `_unreliable_fields_reason` --
structural, machine-checkable, impossible for a future reader to miss
the way a docstring-only warning could be.

## 4. Identity resolution

- **Players**: MSF's real numeric `player.id` is the join key against
  `player_provider_ids`. Live-checked against the real dev DB: **22 of
  69 (32%)** of this game's real players already resolve to canonical
  `players` rows (Phase 8.2's prior roster activation). The other 47 are
  genuinely unresolved -- `persist_player_stats` reports them via
  `unresolved_players`, never guesses by name, never auto-creates.
- **Teams**: audited whether MSF's numeric team ids from this payload
  (`awayTeam.id=50`, `homeTeam.id=79`) should be inserted into
  `team_provider_ids`. **Not safe, not implemented, reported per HQ's
  own conditional instruction.** Live-checked: `team_provider_ids`
  already has real `mysportsfeeds` mappings for New England Patriots and
  Seattle Seahawks -- but keyed by **abbreviation string** (`"NE"`/
  `"SEA"`, from Phase 8.2's `players.json`/`lineup.json` activation),
  not this endpoint's numeric id. `team_provider_ids` carries `unique
  (team_id, provider_name)` -- a second `mysportsfeeds` row for the same
  team (this time keyed by `"50"`/`"79"`) would violate that constraint.
  MySportsFeeds evidently uses two different identifier schemes for the
  same team across its own endpoints. Team identity for this adapter
  resolves correctly today via the **existing** abbreviation mapping
  (`PlayerStatLine.team` carries the abbreviation directly, matching
  every other adapter's `home_team`/`away_team` convention); the numeric
  id is not persisted anywhere. A future pass could reconcile the two
  schemes (e.g. a second mapping table, or relaxing the unique
  constraint to `(team_id, provider_name, provider_team_id)`) but that
  is a real design decision, not a safe insertion to make silently here.

## 5. Persistence properties (all reused from the existing `player_stats`
   correction-aware design, none newly invented)

- **Idempotent**: proven directly against the real fixture -- reprocessing
  the identical payload against pre-seeded matching rows inserts 0 new
  rows.
- **Game-specific, never season-conflated**: every persisted row carries
  `game_id`, never `season_id` -- a structurally distinct code path from
  `player_season_stats`.
- **Correction-safe**: proven directly against the real fixture -- a
  stale prior observation triggers exactly one new row with the current
  real value; the append-only trigger (`block_snapshot_updates()`)
  structurally prevents any UPDATE, and no test registers a PATCH/PUT
  mock, so respx would raise if the code path ever attempted one.
- **Provenance-preserving**: `AdapterResponse.provider_reported_at` =
  MSF's own real `lastUpdatedOn` (`2026-09-10T12:45:08.670Z`), never
  fabricated.

## 6. Tests

19 new tests, all passing, all against real data (no synthetic MSF
payloads):
- `tests/adapters/test_mysportsfeeds_game_boxscore_adapter.py` (9) --
  pure parsing against the real fixture: 69-line extraction, single
  game_id across every line, correct team split (34/35), real non-zero
  stat values (Drake Maye), stable string join keys with no duplicates,
  the unreliable-fields marker present on every line, real
  `provider_reported_at`, malformed-row skipping, empty-payload safety.
- `tests/test_gate_b_player_game_persistence.py` (5) -- real
  fixture -> adapter -> `persist_player_stats(provider_name=
  "mysportsfeeds")` end to end: correct game_id + partial real identity
  resolution, explicit unresolved-player reporting (67 of 69), zero
  snapCounts persisted-but-flagged, no-duplicate reprocessing, and a
  genuine correction inserting one new row without mutating the old one.
- `tests/test_player_stats_persistence.py` (+1) -- proves
  `provider_name` is genuinely threaded into the identity-resolution
  query params (`eq.sportsdataio` vs. `eq.mysportsfeeds` in the actual
  request URL), not merely accepted and ignored.

**Full apps/sports-intel-layer suite: 783/783 passing, zero
regressions.**

## 7. Out of scope, exactly as specified

No second MySportsFeeds (or any provider) request was made. BALLDONTLIE
untouched. Context Intelligence not wired to this adapter's output.
Probability modeling and recommendation logic untouched. Staging/
production untouched. No live persistence run against the real dev DB
was performed -- these are respx-mocked tests proving the pipeline is
correct; actually persisting Gate B's real 22-resolved-player rows into
the live dev `player_stats` table is a separate, explicitly-authorizable
next step, not implied by "prove this works."

## 8. Readiness for broader Sunday completed-game ingestion

**Architecture: ready.** The adapter + generalized `persist_player_stats`
correctly handle a real completed-game boxscore end to end, with
correct partial identity resolution, correction-safety, and idempotency
all proven against real data.

**Not yet ready for unattended Sunday-scale ingestion**, for reasons
outside this pass's authorized scope:
1. No live-fetching wrapper exists yet (this pass is parse-only, by
   design -- "no new provider calls"). A `MySportsFeedsGameBoxscoreAdapter`
   class mirroring `MySportsFeedsPlayerSeasonStatsAdapter`'s fetch
   pattern is the natural next piece.
2. Player-identity coverage is only 32% for this one game's real
   roster -- broader ingestion will surface many more `unresolved_players`
   until a real backfill pass (matching Phase 3E-8's own precedent)
   expands `player_provider_ids` coverage.
3. The team-id scheme conflict (§4) is unresolved and would recur for
   every game, though it does not block player-stat persistence today.
4. No orchestration/scheduling exists yet to call this per-game, guarded
   by the same one-call-per-game discipline Gate B itself required --
   that's a Master Refresh / worker-layer design question, not this
   pass's.
