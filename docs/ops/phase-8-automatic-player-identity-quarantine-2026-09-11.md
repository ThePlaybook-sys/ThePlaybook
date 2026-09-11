# Automatic MSF Player Identity Activation + Quarantine (2026-09-11)

MANSA HQ directive: "AUTOMATIC PLAYER IDENTITY + QUARANTINE BUILD."
Authorized: the `player_identity_quarantine` schema, a permanent
provider-ID-first automatic activation wrapper, and a zero-cost real
replay proof against the already-preserved Gate B fixture. Explicitly
NOT authorized (and not built): a live MSF boxscore worker, completed-
game polling, any provider call of any kind, SF@LAR boxscore retrieval,
player-game persistence orchestration, Context Intelligence,
recommendations, staging/production.

## 1. Schema: `player_identity_quarantine`

**Migration**: `supabase/migrations/20260911210000_player_identity_quarantine.sql`,
applied live to dev and verified (`information_schema.columns`,
`pg_get_constraintdef`, `pg_indexes`, `pg_class.relrowsecurity`).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `game_id` | uuid, FK `games(id) on delete cascade`, nullable | nullable because a malformed-identity case may arrive with no reliable game context in a future batch caller; never null in this pass's own tests, which always supply it |
| `provider_name` | text, not null, check in `('mysportsfeeds')` | room to extend later, same pattern as `game_provider_ids`/`game_postgame_ingestion_state` |
| `provider_player_id` | text, nullable | null exactly for `malformed_identity` |
| `provider_team_id` | text, nullable | |
| `raw_player_name` / `raw_position` | text, nullable | evidence for a human reviewer, never used to establish identity |
| `conflict_type` | text, not null, check in the 4 named classifications | `id_collision`, `team_unresolved`, `ambiguous_match`, `malformed_identity` |
| `candidate_player_id` | uuid, FK `players(id)`, nullable | set only for `ambiguous_match` -- the plausible existing duplicate, never auto-merged |
| `raw_capture_id` | uuid, FK `game_events(id)`, nullable | links back to the raw provider payload evidence when the caller supplies one |
| `status` | text, not null, default `'open'`, check in `('open','resolved')` | |
| `resolution_note` | text, nullable | for the future manual-review workflow, not written by this pass's code |
| `detected_at` / `resolved_at` / `updated_at` | timestamptz | `updated_at` auto-maintained by the existing, reused `set_updated_at()` trigger; a check constraint enforces `resolved_at` is null iff `status='open'` |

**Duplicate-row prevention**: a partial unique index
(`idx_player_identity_quarantine_open_identity`) on
`(game_id, provider_name, coalesce(provider_player_id, '~malformed~' ||
coalesce(raw_player_name, 'unknown')))` where `status = 'open'` -- the
database-level guarantee that two open cases can never exist for the
same identity in the same game, with the application-level
check-then-insert in the activation wrapper as the primary path and this
index as defense-in-depth against a genuine concurrent-caller race.
Confirmed live via `pg_indexes`.

**RLS**: enabled, zero policies -- confirmed live via
`pg_class.relrowsecurity = true`, `policy_count = 0`. Same convention as
`game_postgame_ingestion_state`/`activation_run_markers` (internal
bookkeeping/audit evidence, service-role access only via the service
key's RLS bypass).

**Supporting index**: `idx_player_identity_quarantine_open` on
`detected_at` where `status = 'open'`, for the future manual-review
workflow ("show me every open case").

## 2. Automatic MSF player activation

**Module**: `apps/sports-intel-layer/app/persistence/player_identity_activation.py`.

A permanent wrapper around the already-proven `ensure_player` pattern
(`app/persistence/player_identity.py`, called not reimplemented),
implementing HQ's rules A-J exactly:

- **Rule B (reuse)**: `resolve_player_ids` first, for every call -- an
  already-mapped `provider_player_id` returns immediately with zero
  team lookup, zero name check, zero quarantine read/write.
- **Rule C/D (team-first, never unresolved)**: a genuinely unseen
  `provider_player_id` must resolve `provider_team_id` through the
  persisted `team_provider_ids` mysportsfeeds mapping (the abbreviation
  scheme, e.g. `"NE"`/`"SEA"` -- the same scheme
  `parse_game_boxscore`'s own `PlayerStatLine.team` field carries) --
  missing or unmapped, in either case, quarantines `team_unresolved`,
  never creates.
- **Rule F/G (name similarity is a safety signal only)**: before ever
  creating a new player, checks existing canonical players on the
  resolved team who do NOT yet carry a mysportsfeeds mapping (an
  already-mapped namesake is already-resolved identity, not a fresh
  ambiguity -- excluded from the comparison set) for a name similarity
  ≥ 0.82 (`difflib.SequenceMatcher`, the exact cutoff the prior manual
  pass used -- reimplemented here since no reusable fuzzy-matching
  function exists anywhere in the codebase, confirmed by grep). A hit
  quarantines `ambiguous_match` with `candidate_player_id` set; it never
  merges and never blocks the create path for a genuinely different
  player.
- **Rule A/E (provider-ID-first creation)**: only after both checks
  clear does the wrapper create a fresh `players` row and link it,
  identically to `ensure_player`'s own create step.
- **Rule H (id_collision)**: if `link_provider_player_id` raises
  `PlayerIdentityError` after the create (a genuine race on the
  `(provider_name, provider_player_id)` unique constraint --
  `link_provider_player_id`'s own upsert only covers
  `(player_id, provider_name)`, so this is the one collision it cannot
  silently absorb), the wrapper issues a compensating `DELETE` on the
  just-created orphan `players` row (the two PostgREST calls aren't
  transactional) and quarantines `id_collision` rather than leaving an
  unlinked orphan.
- **Rule H (malformed_identity)**: no usable `provider_player_id` at all
  quarantines immediately, before any other lookup.
- **Rule I (a quarantined player never blocks a peer)**: satisfied
  structurally -- the wrapper operates one player at a time and returns
  an `ActivationResult` for every outcome (resolved or quarantined)
  rather than raising for a normal quarantine case. The one exception
  type it can raise, `PlayerIdentityActivationError`, is reserved for a
  genuine infra failure (a non-2xx Supabase response) it cannot itself
  classify into one of the four cases.
- **Rule J (idempotent across retries/redeploys)**: quarantine creation
  is check-then-insert against the same identity key the DB's own
  partial unique index uses, returning the existing open row rather than
  creating a second one; a `409` from that index (a genuine concurrent-
  caller race the check-then-insert didn't catch) is caught and resolved
  by re-reading rather than raised.

No live provider call is made anywhere in this module -- every function
call operates on provider identity strings the caller already has from
an already-fetched/parsed payload.

## 3. Zero-cost real replay: Gate B's 69 real players

**Test**: `apps/sports-intel-layer/tests/test_player_identity_activation_gate_b_replay.py`.

Uses only the already-committed, real MySportsFeeds NE@SEA fixture
(`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`,
game 163541, COMPLETED) parsed via the existing, unmodified
`parse_game_boxscore` adapter -- **no new MySportsFeeds call was made
anywhere in this pass.**

**Live-data proof preceding the test** (run against dev,
project `nhwjtsdebgiwskshzqiq`, immediately before writing the test):
querying `player_provider_ids` for exactly the 69 real
`provider_player_id` values this fixture contains confirmed **69/69
already carry a mysportsfeeds mapping, all 69 distinct canonical
players** -- not assumed, not inferred from the earlier Gate B
persistence pass (which itself only resolved 2/69 at the time it was
written; the remaining 67 were resolved by later, separate passes this
session, most recently MSF Week 1 Identity Recovery's game/team identity
work and this pass's own predecessor foundation build).

**Test result**: all 69 real players, run one at a time through
`activate_msf_player`, resolved via the **REUSE path (Rule B)** --
`result.outcome == "resolved"` for every one, each `player_id` matching
the exact live-confirmed mapping, 69 distinct resolved player ids. The
test deliberately registers no respx route at all for
`team_provider_ids`, `players` (POST), or `player_identity_quarantine`
-- if the reuse path had incorrectly fallen through to team resolution,
player creation, or quarantine for any of the 69, respx would have
raised a "no route matched" error and failed the test structurally, not
just by a wrong assertion. **Zero new players created. Zero duplicate
mappings. Zero false quarantines. Zero provider calls of any kind.**

## 4. Tests

**New**: `tests/test_player_identity_activation.py` (10 tests, respx-mocked,
following this project's established pattern) --
1. Reuse path never touches team/quarantine endpoints (Rule B).
2. Safe unseen-player creation, provider-ID-first (Rules A/C/E).
3. Missing `provider_team_id` -> `team_unresolved`, never creates (Rule D).
4. Unmapped `provider_team_id` -> `team_unresolved`, never creates (Rule C/D).
5. Malformed identity (`provider_player_id` absent) -> quarantines
   immediately, without even attempting player/team resolution (Rule H).
6. Ambiguous name similarity on an unmapped existing teammate ->
   quarantines with `candidate_player_id` set, never merges, never
   creates a second player (Rules F/G).
7. An already-mapped, similarly-named teammate is correctly excluded
   from the ambiguity check -- a genuinely new player is still safely
   created (proves the ambiguity check's own exclusion rule, not just
   its trigger condition).
8. Provider-ID collision on link -> compensating `DELETE` of the orphan
   `players` row, then quarantine (Rule H).
9. Repeated identical quarantine call is idempotent -- second call
   returns the first call's row, zero duplicate inserts (Rule J).
10. A quarantined player (malformed identity) followed by an unrelated
    safe peer in the same loop -- the peer resolves normally, proving
    the wrapper never raises for a quarantine outcome (Rule I).

**New**: `tests/test_player_identity_activation_gate_b_replay.py` (1 test,
see Section 3).

**Full `apps/sports-intel-layer` suite**: baseline 783/783 plus these 11
new tests -- **794/794 passing, zero regressions.**

## 5. Live security/performance advisors (post-migration)

**Security**: `player_identity_quarantine` appears in the existing
INFO-level "RLS Enabled No Policy" bucket alongside
`game_postgame_ingestion_state`/`activation_run_markers` -- expected,
matches convention, not a new/different finding. No new WARN-level
finding attributable to this pass (the four pre-existing WARNs --
`function_search_path_mutable` on two unrelated functions, three
`SECURITY DEFINER` functions callable by `anon`/`authenticated`, and
leaked-password-protection-disabled -- all predate this migration and
are untouched by it).

**Performance**: two new INFO-level "unindexed foreign key" findings on
`player_identity_quarantine.candidate_player_id` and
`.raw_capture_id` -- consistent with the ~38-and-growing already-accepted
unindexed-FK pattern across this schema where the FK isn't itself a hot
lookup path (the columns this table's own query patterns actually
filter on -- `game_id`, `provider_name`, `status` -- are covered by the
two indexes this migration adds). One new INFO-level "unused index"
finding on `idx_player_identity_quarantine_open` -- expected for a
brand-new table with no query history yet, not a defect.

## 6. Concrete blocker for the future permanent boxscore worker

**`PlayerStatLine` (the adapter's own provider-neutral output model,
`app/adapters/models.py`) does not carry player position.**
`parse_game_boxscore` reads `player.position` from MySportsFeeds' raw
payload but never surfaces it on `PlayerStatLine` -- only
`game_external_id`, `player_external_id`, `player_name`, `team`, and
`stats` exist on that model today. `activate_msf_player`'s own
`raw_position` parameter has nowhere to get a real value from a
`PlayerStatLine` today; this pass's Gate B replay test passes
`raw_position=None` for all 69 real players precisely because of this
gap, disclosed rather than papered over with an invented value.

This is not a blocker for anything this pass built (the activation
wrapper accepts `raw_position` as an explicit parameter regardless of
its source, and reuse -- the only path the replay exercises -- never
touches position at all), but it is a real, concrete blocker for the
eventual permanent boxscore worker: any future caller wanting to
persist real position data on newly-created players will need
`parse_game_boxscore`/`PlayerStatLine` extended to carry
`player.position` through from the raw payload first. Named here for
that future pass, not fixed in this one (out of this pass's authorized
scope).

## Out of scope, exactly as instructed

No live MSF boxscore worker. No completed-game polling. No provider
call of any kind. No SF@LAR boxscore retrieval. No player-game
persistence orchestration. No Context Intelligence. No recommendation
changes. Staging and production untouched. The pre-existing, unrelated
Proof 1b test debt (`team_provider_ids_constraints_test.sql`, disclosed
in the prior pass) did not block this pass's execution and was not
touched.
