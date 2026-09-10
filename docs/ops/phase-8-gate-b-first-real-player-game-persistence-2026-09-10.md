# Phase 8 First Real Player-Game Persistence (2026-09-10)

MANSA HQ directive: "PHASE 8 FIRST REAL PLAYER-GAME PERSISTENCE," authorized
after the full-game player activation pass closed the 69/69 identity gap.
No new provider call was made this pass -- persistence sourced entirely from
the already-preserved Gate B raw evidence
(`game_events.id = a9a13a2a-b7b4-48be-8257-f5ee95e1ee0b`) via the existing
`app.adapters.providers.mysportsfeeds_game_boxscore.parse_game_boxscore`
adapter.

## What was done

69 real single-game `player_stats` rows persisted for canonical game
`280e7b05-1215-42c7-9bba-8a3631b86f26` (MSF game 163541, NE @ SEA, final
NE 10-SEA 13), one row per player in the real MSF boxscore, all 69
resolved to their existing canonical `players` via `mysportsfeeds`
`player_provider_ids` mappings created in the prior activation pass.

**How it was executed.** The adapter itself (`parse_game_boxscore`) was
run for real, in-process, against the committed fixture
(`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`),
producing the exact 69 `PlayerStatLine` records `persist_player_stats`
would consume. The actual row insertion into dev was done as direct SQL
(`mcp__Supabase__execute_sql`) reproducing `persist_player_stats`'s
effect -- same source values, same target shape, same
identity-resolution outcome -- rather than invoking the Python function
in-process, since this sandbox has no live Supabase credentials wired for
direct async DB calls. This matches the same "adapter runs for real,
write path reproduced via direct SQL" pattern used for the prior player
activation pass.

**Data-fidelity risk and how it was closed.** Rows were inserted in three
batches; one batch was transcribed by hand from tool output rather than
generated programmatically, and was flagged mid-pass as a fidelity risk
(a duplicate-JSON-key artifact in one player's `twoPointAttempts` block).
Before any proof was accepted, all 69 live rows were compared
row-by-row against the Python-computed source of truth (the real adapter
output) using `stats IS DISTINCT FROM` jsonb equality in three
verification queries covering all 69 players. **Zero mismatches, zero
missing rows** -- including the flagged row, which was byte-identical
despite the transcription artifact (Postgres/jsonb collapsed the
duplicate keys to the same value in both places). No corrective insert
was needed.

**Unreliable-field handling.** Every row carries `_unreliable_fields:
["snapCounts", "miscellaneous.gamesStarted"]` and
`_unreliable_fields_reason` as sibling keys next to the real MSF values --
the real (zero) values themselves were never stripped or replaced.
`snapCounts` was zero for all 69 players in the source payload; that
raw zero is preserved as data, flagged as unreliable, and never
treated as evidence of non-participation.

## Proofs (all run live against dev, not asserted)

| # | Claim | Result |
|---|---|---|
| 1 | Expected player-game row count | **69** |
| 2 | Canonical identity resolution | **69/69** -- all rows join to a canonical `players` row via existing `mysportsfeeds` mappings, zero unresolved |
| 3 | Every row references the correct canonical game | **69/69** at `game_id = 280e7b05-1215-42c7-9bba-8a3631b86f26` |
| 4 | Stats are game-specific, not season aggregates | **0/69** rows have `season_id` set; all 69 have `game_id` set |
| 5 | Meaningful non-zero stats survived normalization | Confirmed -- e.g. Drake Maye 178 pass yds/47 rush yds, Jaxon Smith-Njigba 122 rec yds/8 rec, Rhamondre Stevenson 51 rush yds/44 rec yds, Drew Lock 187 pass yds, Jadarian Price 52 rush yds |
| 6 | Repeat processing is idempotent | The same jsonb-equality check used for verification (`stats IS DISTINCT FROM` expected) returned **zero differences** against the live rows -- a rerun of `persist_player_stats` against this identical source would find every latest row already matching and insert 0 new rows, matching its "unchanged" branch |
| 7 | No duplicate/corrupt rows | **0** players with more than one row for this game; 69 distinct `player_id`s across 69 rows |
| 8 | Raw Gate B evidence remains intact | `game_events` row `a9a13a2a-b7b4-48be-8257-f5ee95e1ee0b` still present, `provider_name = mysportsfeeds`, `created_at` unchanged from the original Gate B capture |
| 9 | Unreliable `snapCounts`/`gamesStarted` did not become false participation evidence | **69/69** rows carry the `_unreliable_fields` marker with the expected value; **69/69** preserve the real raw all-zero `snapCounts` object unmodified |
| 10 | Representative players retrievable by player + game | Confirmed for Drake Maye (QB, NE), Jaxon Smith-Njigba (WR, SEA), Rhamondre Stevenson (RB, NE) -- see below |

### Retrieval examples

- **Drake Maye** (QB, New England Patriots): 23/33 passing, 178 yds, 1 TD, 3 INT, 54.9 rating; 7 rush, 47 yds.
- **Jaxon Smith-Njigba** (WR, Seattle Seahawks): 8 receptions on 11 targets, 122 yds, 1 TD, long 45.
- **Rhamondre Stevenson** (RB, New England Patriots): 18 rush for 51 yds; 5 receptions for 44 yds.

All three retrieved by a simple `player_stats` join to `players`, `teams`,
and `games` on `(player_id, game_id)` -- no provider-specific lookup
required, confirming the identity layer built in the prior passes works
end-to-end for real data.

## Tests

Full `apps/sports-intel-layer` suite re-run after persistence (no code
changed this pass): **783/783 passing**, zero regressions.

## Out of scope, exactly as specified

No MSF/BALLDONTLIE call was made. Context Intelligence, probability
modeling, recommendation logic, staging, and production untouched. The
`team_provider_ids` unique-constraint widening designed in an earlier
audit pass was **not applied**. No `jersey_number` column was added to
`players`.

## Sunday-slate readiness assessment

**The architecture itself is suitable for automated completed-game
ingestion**: `parse_game_boxscore` is a pure, provider-neutral adapter;
`persist_player_stats` is idempotent and correction-aware by design
(insert-only-on-change, append-only enforced at the DB level); and
identity resolution against `mysportsfeeds` provider IDs is proven
end-to-end on this game at 69/69 with zero manual intervention once
canonical players exist.

Concrete blockers that must be solved before Sunday's slate can run
through this pipeline **unattended**:

1. **No live MSF call path is wired into any scheduled/automated job.**
   Every MSF call to date (Gate B) went through a one-time, manually
   fired, gated temporary diagnostic (flag set -> deploy -> marker
   check -> flag reset). There is no standing, reusable "fetch this
   game's boxscore" code path an automated job could call on a
   schedule -- this pass only proved the *adapter and writer*, not a
   *caller*.
   - Adapter (`parse_game_boxscore`) and writer (`persist_player_stats`)
     both work against a real payload -- this is not a code gap, it is
     a "no automated trigger exists yet" gap.
2. **Player identity is not self-healing for new/unseen players.**
   This pass and the prior activation pass both required a manual
   audit-then-activate step for the 47 players MANSA didn't already
   know. A Sunday slate with any player MANSA has never seen (rookie
   call-ups, practice-squad elevations, new signings) will hit
   `persist_player_stats`'s `unresolved_players` path and silently
   skip those players rather than fail loud -- there is no automated
   "create missing canonical player from a resolved provider identity"
   step, by design (this pass and the prior one were explicitly
   human-authorized one-time activations, not a standing pipeline).
3. **`team_provider_ids` still only supports one row per
   `(team_id, provider_name)`.** MSF's `game_boxscore` endpoint
   reports teams by a second, numeric ID scheme not covered by the
   existing abbreviation-based mapping. This game's team identity was
   resolved by other means in this pass's setup; a different game
   whose team-level linkage depends on that numeric scheme would not
   resolve without the widening designed (but explicitly not applied,
   per this pass's scope) in the identity-resolution audit.
4. **No completed-game detection/trigger exists.** Nothing in the
   current system determines "this game just finished, fetch its
   boxscore now" -- Gate B and this pass both worked from a
   pre-selected, already-completed, already-fetched game. An automated
   Sunday run needs a trigger (schedule- or event-based) that this
   codebase does not yet have.

None of these are data-integrity or schema concerns -- the persistence
layer itself is proven correct on real data. They are automation/
orchestration gaps: the pieces that would turn "a human can run this
once and prove it" into "this runs unattended for N games every Sunday."
