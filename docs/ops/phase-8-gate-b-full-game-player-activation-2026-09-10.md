# Phase 8 Full Game Player Activation (2026-09-10)

MANSA HQ directive: "PHASE 8 FULL GAME PLAYER ACTIVATION," authorized
after the Gate B identity resolution audit found all 47 unresolved
players to be genuinely missing canonical players (Class C, 47/47 --
zero ambiguous, zero conflicts). No provider call was made this pass;
this works entirely from the preserved Gate B payload and existing
MANSA data.

## What was done

47 canonical `players` rows created (21 NE, 26 SEA), each with exactly
one `player_provider_ids` row (`provider_name='mysportsfeeds'`) linking
it to its real MSF player id. Real data population via direct SQL against
dev, not a migration -- matching this project's own established
"schema via migration, real data via execute_sql" convention (no schema
changed; `players`/`player_provider_ids` already fully supported this).

**Pattern used**: the same identity-first, provider-id-as-dedup-key
logic `app.persistence.player_identity.ensure_player` already
implements (check for an existing `mysportsfeeds` mapping first; create
`players` + `player_provider_ids` together only if absent) -- expressed
as one idempotent SQL statement (`WHERE NOT EXISTS` gate on
`provider_player_id` before the insert) rather than 47 individual async
calls, since this was a one-time real-data activation, not new
application code. Before committing, verified live that none of the 47
MSF ids already belonged to any canonical player (see audit pass) and
that no name in the 47 was a near-duplicate of an existing canonical
player (fuzzy check, cutoff 0.82, zero flags).

**Jersey number was NOT persisted.** `players` has no column for it
(`id, team_id, name, position, external_provider_id` only) -- this is a
real schema gap, not an oversight this pass worked around. Jersey number
remains available in the raw Gate B evidence (`game_events.raw_payload`)
for a future pass if a `players.jersey_number` column is ever added; not
added here since it wasn't required to reach 69/69 identity coverage
and no schema change was authorized.

## Proofs (all run live against dev, not asserted)

| Claim | Result |
|---|---|
| Players for NE + SEA (expected 81 = 34 + 47) | **81** |
| Gate B boxscore identity coverage | **69/69** |
| All 69 Gate B MSF ids resolve uniquely | **69 resolved, 69 distinct player_ids** -- no collisions |
| No duplicate canonical players created | Zero `provider_player_id` or `player_id` appears more than once in `mysportsfeeds` `player_provider_ids` rows |
| Rerunning activation creates zero additional players | The exact same idempotent SQL statement was run a second time -- **returned zero rows** |
| Existing 34 players/mappings unchanged | Re-queried all 34 original `(provider_player_id -> player_id, name, team_id, position)` tuples -- **byte-identical** to the pre-activation state |

Full `apps/sports-intel-layer` suite re-run after activation (no code
changed this pass): **783/783 passing**, zero regressions.

## Out of scope, exactly as specified

No player-game stats were persisted. No second MSF/BALLDONTLIE call. The
`team_provider_ids` unique-constraint widening designed in the prior
audit pass was **not applied** -- still pending separate authorization.
Context Intelligence, probability modeling, recommendation logic,
staging, and production untouched.

## Net effect

Gate B's real completed game (163541, NE @ SEA) now has **69/69 real
players identity-resolved** in MANSA's canonical `players` table, up
from 22/69 before this pass -- unblocking the previously-designed
player-game persistence pipeline (`app.adapters.providers.
mysportsfeeds_game_boxscore` + `persist_player_stats(provider_name=
"mysportsfeeds")`) to resolve every player in this game once
persistence is separately authorized.
