# Phase 8 Player Performance Engine Integration (2026-09-15)

MANSA HQ directive: "PHASE 8 PLAYER PERFORMANCE ENGINE INTEGRATION."
Registers `player_performance` as a real, official Context Intelligence
`engine.py` `SUPPORTED_DIMENSIONS` entry, fixes the real opponent-
resolution format mismatch the JSN proof exposed, and proves the full
chain live through the actual engine path (not just the standalone
compute functions). `build_evidence()` and recommendation behavior remain
untouched. No schema changes -- the opponent fix uses only real,
already-persisted, already-existing tables.

---

## 1. Engine registration

`app/context_intelligence/engine.py`:

- `SUPPORTED_DIMENSIONS` -> `("weather", "market", "news", "venue",
  "player_performance")`.
- `player_performance` removed from `unsupported.py`'s
  `UNSUPPORTED_DIMENSIONS` dict (its stale reason string -- "no real
  player identity or player_stats data exists" -- is no longer merely
  inaccurate prose, as the 2026-09-09 audit already flagged; it is now
  outright wrong, so it was removed rather than left to drift further).
- `build_contextual_intelligence` gained an optional `player_id: str |
  None = None` parameter -- the first dimension in this module scoped to
  something other than `game_id` alone. When `player_id` is `None`
  (every existing caller's own shape, unchanged), `player_performance`
  resolves to `no_player_requested_result()` and **none of the new reads
  fire at all** -- proven live by
  `test_no_player_id_never_triggers_the_new_reads`, which deliberately
  leaves `player_stats`/`players`/`game_events`/`team_provider_ids`
  unmocked; respx's own unmocked-request error would surface if the
  engine called any of them.
- When `player_id` is given, the engine fetches that player's own real
  `player_stats` rows, the real `games` rows they reference, that
  player's own real identity (`players.name`/`position`/`team_id`), and
  real opponent-identity data (Section 2), then calls
  `compute_player_performance_context`.
- `player_performance`'s own `target_event_timestamp` is the engine's
  `now` (not the target `game_id`'s own kickoff) -- the natural "what do
  we currently, actually know about this player" framing. For a
  genuinely upcoming `game_id` this makes no practical difference (no
  `player_stats` row can exist yet for an unplayed game either way); for
  a `game_id` that has already happened (the JSN/SEA@NE proof), it
  correctly includes that real, completed game as valid historical
  evidence.

**`build_evidence()` and recommendation behavior are untouched** --
confirmed via `git status`: `app/agents/probability_modeling.py` was not
touched by this pass.

---

## 2. Opponent identity fix

**Root cause, as disclosed in the prior pass**: `games.home_team`/
`away_team` are free text, inconsistently formatted (some full team
names, some short provider-style codes like `"SEA"`/`"NE"`), with no
foreign key to `teams`. The prior pass's exact-name-match resolver
correctly failed on the real SEA@NE game rather than guess -- but that
left opponent identity genuinely unresolved for that (and likely many
other) real games.

**The fix uses real, already-persisted, canonical provider-identity
data -- no new table, no new column, no hardcoded team/abbreviation
anywhere in the code.** Investigated live before writing any code:
`game_events.raw_payload` (the real MySportsFeeds `game_boxscore` raw
capture this session's own MSF pipeline already writes) carries the raw
MSF response's own `body.game.homeTeam.id`/`awayTeam.id` fields -- real
MySportsFeeds numeric team identifiers. Confirmed live for the real
SEA@NE game: `homeTeam.id=79` (Seattle), `awayTeam.id=50` (New England).
Separately, `team_provider_ids` (provider_name='mysportsfeeds') already
has real rows mapping both of those exact numeric ids to real `team_id`s
-- `79 -> Seattle Seahawks`, `50 -> New England Patriots`, confirmed live.

The resolution chain is therefore:

```
game_events.raw_payload -> body.game.homeTeam.id / awayTeam.id   (real MSF numeric team ids)
    -> team_provider_ids (provider_name='mysportsfeeds')          (real, already-persisted mapping)
    -> team_id -> teams.name                                      (real canonical identity)
```

Implemented as two clearly separated pieces:

- `extract_msf_team_provider_ids(raw_payload: dict) -> tuple[str, str] |
  None` (`player_performance.py`, pure, no I/O) -- the one
  MySportsFeeds-shape-specific piece, isolated and labeled as such, not
  pretended to be provider-generic. Returns `None` (never a guess, never
  a partial tuple) for any payload that doesn't have this exact shape.
- `resolve_opponent_by_team_id(identity, *, player_team_id)` (pure,
  fully generic) -- operates only on already-resolved real `team_id`s,
  exact equality only, never fuzzy. Returns `(None, None)` when identity
  wasn't resolvable, the player's own team is unknown, or (a genuine
  anomaly) it matches neither side.
- `resolve_team_identity_for_games` (`context_intelligence_reads.py`,
  real I/O) -- composes `read_game_events_raw_payloads` +
  `read_team_provider_ids` (+ a `teams` name lookup) + the pure extractor
  above into one real `{game_id: {"home_team_id", "home_team_name",
  "away_team_id", "away_team_name"}}` map.

**No hardcoded team/abbreviation/player literal anywhere in this code.**
**No fuzzy matching anywhere** -- every comparison is exact numeric or
exact UUID equality. **When identity cannot be resolved** (no real
`game_events` row for the provider, an unrecognized payload shape, or no
`team_provider_ids` mapping yet), `opponent`/`home_or_away` stay `None`
and the observation's own `reliability_limitations` names exactly why --
proven by `test_observation_opponent_stays_none_when_no_identity_resolved_for_game`.

---

## 3. Observation semantics preserved

Unchanged from the prior pass, reconfirmed by the full existing test
suite plus new tests:

- **One player + one game = one observation.** `resolve_canonical_
  observation` (`observation_identity.py`, untouched this pass) still
  collapses any number of raw `player_stats` rows for the same
  `(player_id, game_id)` pair to exactly one canonical observation.
- **Correction rows never inflate sample size.** Proven again at both
  the observation level (`duplicate_raw_row_count`) and the dimension
  level (`sample_size`), now also proven **within a real multi-game
  result** (`test_multi_game_still_collapses_correction_rows_within_each_game`):
  two distinct games, one of which also carries a duplicate correction
  row, produces `sample_size == 2` (not 3), with the duplicated game's
  own `duplicate_raw_row_count == 2` still disclosed.
- **Provenance, `duplicate_raw_row_count`, correction history**: all
  identical in shape and behavior to the prior pass -- nothing deleted,
  nothing hidden, every raw row's existence still traceable.
- **Point-in-time limitation**: `PLAYER_PERFORMANCE_POINT_IN_TIME_
  LIMITATION` still present, verbatim, on every observation, proven again
  through the real engine path in `test_jsn_sea_ne_real_engine_proof`.
- **`data_completeness` semantics**: still `"joined"`/`"unavailable"`
  only from this dimension (never `"partial"`), still independent of
  `confidence`/`insufficient_evidence` -- proven again through the real
  engine path (`dim.data_completeness == "joined"` while
  `dim.confidence is None` and `dim.insufficient_evidence is True`, all
  simultaneously true and correct).

---

## 4. Real engine proof

`test_jsn_sea_ne_real_engine_proof` (`tests/context_intelligence/
test_engine.py`) runs `build_contextual_intelligence` itself -- the real
engine entry point, not the compute functions directly -- with every
Supabase boundary respx-mocked to the exact real DEV values (the same
values `test_player_performance.py`'s own real-proof class uses).
Confirms, through the actual engine path:

- **`player_performance` as supported**: `"player_performance" in
  SUPPORTED_DIMENSIONS`, and the returned dimension's own `.dimension ==
  "player_performance"`.
- **Exactly one game observation**: `sample_size == 1`,
  `facts["game_count"] == 1`, one entry in `facts["observations"]`.
- **11 targets, 8 receptions, 122 receiving yards, 1 receiving TD**:
  `role_usage_signals["receiving"] == {"targets": 11, "receptions": 8,
  "recYards": 122, "recTD": 1}`.
- **Resolved opponent identity**: `opponent == "New England Patriots"`,
  `home_or_away == "home"` -- via the real provider-identity chain, not
  text matching; no "could not be determined" limitation fires.
- **Correct provenance**: `provenance[0]["table"] == "player_stats"`,
  `provenance[0]["row_count"] == 2` (both real rows disclosed).
- **No duplicate inflation**: `sample_size == 1` despite 2 real raw rows;
  `duplicate_raw_row_count == 2` still disclosed; canonical row correctly
  identified as the newer, real-dispatcher capture.
- **Honest point-in-time limitation**: present verbatim in the real
  observation's own `reliability_limitations`.
- **`data_completeness` separate from confidence**: `"joined"` with
  `confidence is None` and `insufficient_evidence is True`
  simultaneously -- real evidence found, honestly below the trend floor.

---

## 5. Multi-game architecture proof

`test_engine_accepts_multiple_distinct_games_as_separate_observations`
(`test_engine.py`) and `test_multi_game_still_collapses_correction_rows_
within_each_game`/`test_reaching_the_sample_floor_flips_insufficient_
evidence_off` (`test_player_performance.py`) prove, through both the real
engine path and the pure compute layer, that the architecture already
accepts multiple distinct canonical games for the same player:

- Two distinct games (the real SEA@NE game plus one **synthetic**
  second game, explicitly labeled as such, used only to exercise the
  engine's own multi-game wiring since no second real game exists yet)
  produce `sample_size == 2`, two entries in `facts["observations"]`,
  correctly ordered oldest-event-first.
- The real game's own duplicate correction row is still correctly
  collapsed (`duplicate_raw_row_count == 2`) while the synthetic game
  (a single row) correctly shows `duplicate_raw_row_count == 1` --
  collapsing happens per-game, never across games.
- Crossing `INSUFFICIENT_SAMPLE_FLOOR` (2) with two real-shaped games
  correctly flips `insufficient_evidence` to `False` -- the shared
  scoring machinery already works correctly for >1 game with zero
  further code changes, exactly as the prior pass's own docstring
  predicted.

**Explicitly not represented as real MANSA evidence** -- every synthetic
fixture is labeled as such in its own test docstring and variable names
(`"synthetic-game-2"`, `"synthetic-row-2"`), matching the directive's own
instruction.

---

## 6. Tests

**23 new/changed tests, full suite 895 passed, zero regressions**
(up from 882 before this pass):

- `test_player_performance.py`: 9 new opponent-identity mechanism tests
  (`extract_msf_team_provider_ids` shape recognition and rejection,
  `resolve_opponent_by_team_id` home/away/missing-identity/missing-
  player-team/anomaly cases, end-to-end observation-level disclosure),
  1 new `no_player_requested_result` test, 1 new multi-game-with-
  correction-row test, 1 new opponent-resolution assertion added to the
  JSN real-proof class; existing tests updated to the new
  `player_team_id`/`team_identity_by_game` parameter shape (the old
  `player_team_name`-based opponent tests were replaced, not merely
  patched, since the resolution mechanism itself changed).
- `test_engine.py`: 4 new tests (dimension registration, zero-extra-cost
  when no player_id given, the full JSN real engine proof, the
  multi-game architecture proof).
- `test_unsupported.py`: `_EXPECTED_DIMENSIONS` updated (5 dimensions,
  `player_performance` removed).

**Full `apps/ai-orchestrator` suite: 895 passed, zero regressions.**

---

## 7. Remaining limitations

- **Still not wired into `build_evidence()` or any recommendation
  path.** That remains a separate, later, Phase-4-reopening decision,
  exactly as this pass's own boundary requires.
- **Opponent resolution depends on a real MySportsFeeds `game_events`
  raw capture existing for the game.** For any game whose only evidence
  is a `player_stats` row with no corresponding real `game_events` row
  for `provider_name='mysportsfeeds'` (or whose raw payload doesn't carry
  the expected shape, or whose extracted numeric team id has no
  `team_provider_ids` mapping yet), opponent stays honestly `None` --
  this is a real, disclosed dependency on a second table now, not a
  free-standing resolution from `player_stats` alone.
- **No trend/consistency methodology exists yet, even above the sample
  floor.** `confidence`/`similarity_score` remain always `None` from this
  dimension, unchanged from the prior pass.
- **Position is still current/static, not historically tracked.**
  Unchanged from the prior pass.
- **Same-day point-in-time timing precision is still not guaranteed.**
  Unchanged -- `PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION` still names
  this honestly.
- **Injuries, lineup/depth breadth, game-state/PBP, trend scoring**:
  untouched, exactly as instructed.
- **No genuine second real historical game exists yet** -- the multi-game
  architecture proof (Section 5) is real code proven with one real game
  plus one synthetic game; it is not, and does not claim to be, a real
  multi-game Context Assembly Proof. That remains blocked on real time
  (Week 2 completing), independently constrained by the already-recorded
  MSF cancellation status (access ends 2026-09-17).

---

## 8. Smallest next Phase 8 step

Two candidates, neither required by this pass, presented for the next HQ
decision:

1. **Broaden opponent-identity coverage.** `resolve_team_identity_for_
   games` currently only resolves opponents for games with a real
   `mysportsfeeds` `game_events` raw capture -- since this session's MSF
   postgame pipeline already writes one for every game it processes
   (confirmed: 20 real `game_events` rows exist across the 16 real
   completed games), this should already cover every real game's own
   player observations once exercised against more players -- a smaller
   task than it sounds, likely already fully covered, worth confirming
   with a broader live check rather than assumed.
2. **The real multi-game Context Assembly Proof itself** remains
   blocked on real time, not code -- unchanged from the prior pass's own
   conclusion, now further constrained by the recorded MSF access
   cutoff (2026-09-17), which will likely arrive before Week 2 games
   complete.

This pass does not execute either. No `build_evidence()` change, no
recommendation change, no schema change, no trend scoring, no
injury/lineup/PBP work was made or attempted.
