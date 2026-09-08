# Phase 8.3D — Player Stats Persistence (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.3D — PLAYER STATS PERSISTENCE"
(2026-09-08). Builds the provider-neutral, sport-agnostic persistence
path for confirmed real player performance data, using ONLY the
committed Phase 8.3C fixture — **zero external provider calls made or
authorized this pass.**

---

## 1. Schema verdict

**No migration needed — the existing schema, as widened by Phase 8.3A,
already safely represents everything this pass requires.** Confirmed by
direct live-schema inspection before writing any code:

```
player_stats: id (uuid, pk), player_id (uuid, not null, FK players),
  game_id (uuid, nullable, FK games), stats (jsonb, not null),
  created_at (timestamptz), season_id (uuid, nullable, FK seasons)
```

Mapped against HQ's own seven requirements:

| Requirement | Existing column | Verdict |
|---|---|---|
| Canonical player | `player_id` (FK to `players`, resolved via `player_provider_ids`) | ✓ |
| Provider | not a column on `player_stats` itself — tracked one layer up, via `player_provider_ids.provider_name` | Real, disclosed gap — see below, not fixed this pass |
| Season | `season_id` (FK to `seasons`, added Phase 8.3A) | ✓ |
| Optional game | `game_id` (nullable since Phase 8.3A) | ✓ |
| Captured/as-of time | `created_at` (auto-set) | ✓ |
| Stat payload | `stats` (unconstrained `jsonb`) | ✓ |
| Provenance | see "Provider" above | Same disclosed gap |

**The one real gap: `player_stats` (and `team_stats`, identically)
has no first-class `provider_name` column.** A given row's provider is
only recoverable indirectly, by cross-referencing `player_provider_ids`
for the same `player_id`. This is a genuine limitation, not invented —
but not "genuinely necessary" to fix this pass: (1) fixing it correctly
would mean touching `team_stats` symmetrically too, out of scope for a
player-stats-only pass; (2) exactly one provider (`mysportsfeeds`) has
ever written real player-season data, so the ambiguity this would guard
against is theoretical today, not real; (3) HQ's own instruction is to
prefer the existing schema when it can *safely* represent the required
concepts — jsonb + an identity-layer join is a safe, if implicit,
representation, matching the identical precedent Phase 8.3A already
established (and shipped) for `team_stats`. Flagged as a disclosed,
non-blocking future improvement in §11, not silently ignored.

**No `player_stats_nfl` (or any sport-specific extension table) was
created.** `TeamStatLine`'s own existing docstring in `app.adapters.
models` already documents this as the intended future path *if* typed,
per-sport columns are ever needed — this pass doesn't need them, and
building one prematurely would violate HQ's own "keep the architecture
sport-agnostic" instruction by baking NFL field names into schema.

## 2. Files/migrations changed

**Migrations: none.**

**New, permanent code:**
- `apps/sports-intel-layer/app/persistence/player_season_stats.py` —
  `PlayerSeasonStatLine`, `PlayerSeasonStatsPersistResult`,
  `PlayerSeasonStatsPersistenceError`, `persist_player_season_stats()`.
- `apps/sports-intel-layer/app/adapters/providers/mysportsfeeds.py`
  (extended, not replaced) — new `MySportsFeedsPlayerSeasonStatsAdapter`
  class + `fetch_player_season_stats()`.
- `apps/sports-intel-layer/tests/test_player_season_stats_persistence.py`
  — 8 tests.
- `apps/sports-intel-layer/tests/adapters/
  test_mysportsfeeds_player_season_stats_adapter.py` — 10 tests, all
  driven by the real committed Phase 8.3C fixture.

**No changes to:** `player_stats.py` (game-scoped sibling, untouched),
`team_stats.py`/`team_season_stats.py` (Phase 8.3A, untouched),
`main.py` (no hook — this pass activates nothing), `production_clients.py`
(no live client builder needed — no provider call is made).

## 3. Canonical stats model

`PlayerSeasonStatLine` (`player_season_stats.py`):

```python
@dataclass
class PlayerSeasonStatLine:
    player: str   # provider-native player identifier
    stats: dict   # opaque, provider-native payload, preserved verbatim
```

Deliberately minimal and sport-agnostic, matching the exact precedent
`TeamStatLine`/`PlayerStatLine` (`app.adapters.models`) and Phase 8.3A's
own `TeamSeasonStatLine` already established: "common cross-sport
fields only... not a typed per-field model." No NFL field name
(`passAttempts`, `snapCounts`, etc.) appears anywhere in this file or
in `persist_player_season_stats()` — the entire `stats` dict is opaque
to the persistence layer, exactly as required.

## 4. MSF adapter mapping

`MySportsFeedsPlayerSeasonStatsAdapter.fetch_player_season_stats(*,
team, season)`:

- `GET /nfl/{season}/player_stats_totals.json?team={team}` — same
  feed/params Phase 8.3C confirmed real and working.
- Parses `data["playerStatsTotals"]`, each entry ->
  `PlayerSeasonStatLine(player=str(entry["player"]["id"]),
  stats=entry["stats"])` — the raw `stats` object (passing, rushing,
  receiving, tackles, interceptions, fumbles, kickoffReturns,
  puntReturns, fieldGoals, punting, kickoffs, extraPointAttempts,
  twoPointAttempts, miscellaneous, snapCounts, gamesPlayed — every
  category Phase 8.3C confirmed real) passed through byte-for-byte,
  never renamed or reshaped.
- Malformed rows (missing `player.id`, non-dict `stats`) are skipped
  and logged, never guessed — same defensive pattern as
  `MySportsFeedsRosterAdapter`.
- `lastUpdatedOn` parsed into `AdapterResponse.provider_reported_at`,
  same convention as every other MySportsFeeds adapter in this
  codebase.
- Same `ProviderAuthError`/`ProviderRateLimitError`/
  `ProviderUnavailableError`/`ProviderDataError` translation as every
  other adapter — a vendor-specific exception never escapes.
- **Not registered against the existing `PlayerStatsAdapter` ABC** —
  that interface's `fetch_player_stats(game_external_id)` contract is
  explicitly game-scoped (its own docstring: "fetch-once-on-final
  intent"). A season-scoped fetch is a different shape, matching how
  Phase 8.3A's team-season-stats parsing was also kept outside the
  game-scoped `TeamStatsAdapter` ABC rather than force-fit into it.

## 5. Identity-resolution behavior

**Read-only against `player_provider_ids`, exactly as HQ instructed —
never joins by name, never auto-creates a player.**
`persist_player_season_stats()` calls the existing, unmodified
`resolve_player_ids()` (`app.persistence.player_identity`), which maps
`provider_player_id -> players.id` via a direct `player_provider_ids`
lookup and returns nothing for an unmapped id — no fuzzy/name matching
exists anywhere in that function or this pass's new code. A
`PlayerSeasonStatLine` whose player has no existing mapping is
appended to `PlayerSeasonStatsPersistResult.unresolved_players` and
skipped; `players`/`player_provider_ids` are never written to by this
module. This matches `persist_player_stats`'s own existing, deliberate
precedent (see that module's docstring) exactly — player identity
creation stays `roster_ingestion.ensure_player()`'s job alone, keeping
"who is this player" and "what did they do this season" as separate
concerns, per this arc's own repeated architecture rule. Proven by test
(`test_unresolved_player_is_reported_not_guessed_or_created`): zero
`POST /rest/v1/players` calls occur even when a stat line's player is
unresolved.

## 6. Provenance/history behavior

**Every prior real observation is preserved untouched — proven, not
just designed.** `persist_player_season_stats()` only ever `INSERT`s
(never `PATCH`/`PUT`), matching `player_stats`'s own DB-level
append-only trigger (`block_snapshot_updates()`, live since
`20260818080000_team_stats_player_stats_append_only.sql`, confirmed by
direct migration read before writing this module). A genuine
correction — the incoming `stats` differing from the latest existing
row for that `(player_id, season_id)` pair — inserts a brand-new row;
the prior row's own content is never read back and rewritten, only
ever superseded by `created_at` ordering. Proven by
`test_genuine_correction_inserts_new_row_preserving_history` (existing
row keeps its recorded value; the new insert carries the corrected
one) and `test_module_never_issues_an_update_to_player_stats`
(structural proof: no PATCH/PUT mock is registered, so respx raises if
the module ever attempted one).

## 7. Idempotency behavior

**Explicitly defined and tested, three distinct outcomes:**
1. First observation for a `(player, season)` pair → always inserts
   (`test_first_fetch_always_inserts`).
2. An identical re-ingestion (same `stats` value already the latest
   row) → inserts nothing (`test_identical_reconciliation_check_
   inserts_nothing`) — a repeated fixture-driven test run, or a future
   repeated real poll, is safe and produces zero duplicate rows.
3. A genuine correction (a different `stats` value) → inserts exactly
   one new row (§6). "Latest" is determined by
   `order=created_at.desc&limit=1`, the same `_latest_row` convention
   every other snapshot-style persistence module in this codebase
   already uses.

## 8. `gamesStarted` handling

**Treated as unreliable, exactly as HQ instructed — preserved raw,
never interpreted.** `stats.miscellaneous.gamesStarted` flows through
`persist_player_season_stats()` completely unfiltered, as part of the
opaque `stats` blob (no field-level logic anywhere touches it) —
matching Phase 8.3C's own real finding that this field returned `0`
for all 43 real players sampled, including obvious starters. The
adapter's own docstring carries an explicit, permanent warning (quoted
in full in §4's own class docstring) that no code in this project may
treat `gamesStarted` as trustworthy participation evidence until it is
independently reconciled against a real, confirmed-working
participation source. `test_stats_dict_is_preserved_verbatim_not_
reshaped` proves the raw value (including `gamesStarted: 0` for Hunter
Henry) survives unchanged from the real fixture through the adapter's
output.

## 9. Tests/full regression

- New tests: **18** (10 adapter, 8 persistence), all passing.
- Adapter tests are driven entirely by the real, committed Phase 8.3C
  fixture (`docs/ops/fixtures/phase-8.3c-msf-player-stats-totals-ne-
  2025-2026-partial-2026-09-08.json`) via `respx` mocking — **zero live
  network calls of any kind**, confirmed by construction (respx
  intercepts every HTTP call in scope; an unmocked request would raise,
  not silently succeed).
- Full `apps/sports-intel-layer` regression suite: **758/758 passed**
  (740 prior + 18 new), zero regressions, zero flakes.

## 10. Multi-sport compatibility

**Genuinely sport-agnostic, verified by inspection, not just claimed.**
Grepped `player_season_stats.py` for any sport-specific term: `"nfl"`
and `"NBA"` appear only in prose docstring commentary explaining the
design intent, never in code logic, field names, or string literals
used for control flow. Every NFL-specific concern (the `/nfl/{season}/
...` URL path, the `team` query param, MySportsFeeds' own field names
inside `stats`) lives exclusively inside
`MySportsFeedsPlayerSeasonStatsAdapter`, the one place HQ's directive
says provider/sport-specific knowledge belongs. A hypothetical future
`SomeProviderNbaPlayerSeasonStatsAdapter` would produce the identical
`PlayerSeasonStatLine(player=..., stats=...)` shape from an NBA
payload, and `persist_player_season_stats()` would not need a single
line changed to accept it — the same `player_stats` table, the same
`season_id`/`player_id` columns, the same identity-resolution and
idempotency logic, regardless of sport.

## 11. Remaining blockers

1. **No provider-name column on `player_stats`/`team_stats`** (§1) —
   disclosed, low-priority, not blocking today (single real provider),
   recommended as a future symmetric migration covering both tables
   together, not built this pass.
2. **Nothing is actually activated in DEV this pass** — this was
   deliberately a build-and-test-against-the-fixture pass, per HQ's own
   objective framing ("Build the provider-neutral persistence path,"
   no "activate"/"persist real rows now" instruction, unlike Phase
   8.3A's explicit activation step). `player_stats` in DEV still holds
   zero season-scoped rows for any player. A future pass, once
   authorized, can activate this exact code against this exact fixture
   with no new provider call.
3. **Only 43 of an estimated 80-90 real NE players are in the
   fixture** (Phase 8.3C's own disclosed truncation) — a future
   activation using this fixture would cover a real but partial roster,
   same disclosure carried forward.
4. **`gamesStarted`'s reliability is still an open question** (§8) —
   not resolved this pass, deliberately left unresolved rather than
   guessed at.

## 12. Recommendation for Phase 8.4 `player_gamelogs` audit

This pass's own real, tested architecture is now the template: before
any new live call, (a) inspect the vendored SDK's feed table for the
exact `player_gamelogs` URL/params shape (mirroring how Phase 8.3C
inspected `player_stats_totals` before calling it), (b) determine
whether `player_stats.game_id` (already real, already non-null-capable,
already exercised by the original game-scoped `persist_player_stats`)
is sufficient to represent a per-game observation, or whether a
distinct `player_gamelogs`-specific shape is needed, and (c) build the
same three-layer separation this pass established — a provider-neutral
`PlayerGameStatLine`-equivalent model, an MSF-specific adapter, and a
persistence function reusing `resolve_player_ids` unchanged — before
any live `player_gamelogs` request is authorized. `player_gamelogs` is
the only path to any of the contextual dimensions this pass's own §10
(season-total boundary) explicitly ruled out: weather/opponent/
teammate/venue-conditioned performance and within-season recency/form
all require game-level, dated observations that `player_stats_totals`
structurally cannot provide.

---

**Capability boundary, stated explicitly per HQ's instruction:** real
season totals (this pass) support player baseline/performance
evaluation, role/usage evidence (via `snapCounts`/`gamesPlayed`), and
season-over-season comparison once a second season is captured. They do
**not** support weather-conditioned, opponent-conditioned, teammate-
conditioned, venue-conditioned, or game-script performance, nor
within-season recency/form — every one of those requires game-level,
dated observations (`player_gamelogs`), not season aggregates.

Zero external provider calls were made this pass. No staging/production
touched. No Phase 8.1/Phase 4/Milestone 5.6/Probability Modeling
changes. No recurring polling activated. No all-team ingestion. No
`player_gamelogs` implementation. All work is local code + tests against
the committed fixture; nothing in this pass required a Railway
deployment.
