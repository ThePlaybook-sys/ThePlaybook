# Phase 8.4 — Player Gamelogs Audit (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.4 — PLAYER GAMELOGS AUDIT"
(2026-09-08). **AUDIT / DESIGN ONLY — no provider calls, no persistence
changes, no migrations.** Determines the provider-neutral design and the
likely real MySportsFeeds path for game-level player performance before
any future live call.

---

## 1. Existing game-scoped architecture

**What already exists (real, working, unmodified this pass):**

| Component | State |
|---|---|
| `player_stats` schema | `id, player_id (not null), game_id (nullable), stats (jsonb), created_at, season_id (nullable)` — game-scoped rows are fully supported today, unchanged since Phase 3E-8 |
| `PlayerStatsAdapter` ABC (`app.adapters.base`) | Exists, game-scoped by explicit design: `fetch_player_stats(game_external_id) -> AdapterResponse[list[PlayerStatLine]]`, docstring states "fetch-once-on-final intent," not a bulk/season fetch |
| `PlayerStatLine` model (`app.adapters.models`) | `game_external_id, player_external_id, player_name, team, stats: dict` — already game-scoped, provider-neutral, matches the exact shape a gamelog row would need |
| Game-scoped persistence (`app.persistence.player_stats`) | `persist_player_stats()` — real, working, `(game_id, player_id)`-keyed idempotent-correction writer. Hardcoded `_PROVIDER_NAME = "sportsdataio"` (pre-existing gap, same one `roster_ingestion.py`/`team_stats.py` had before their own Phase 8.2/8.3A generalizations — not fixed this pass, audit only) |
| Canonical games identity (`games` table + `game_identity.py`) | `games(id, external_provider_id, sport_id, league_id, season_id, sport, home_team, away_team, scheduled_start, stadium, status, final_score, season_type, week, venue_*, finalized_at, manual_seed, ...)`. `game_provider_ids(game_id, provider_name, provider_game_id)` + `resolve_game_ids()`/`link_provider_id()` — real, working, provider-neutral, read-only resolution (never guesses), exactly mirroring `player_identity.py`/`team_identity.py` |
| `player_provider_ids` | Real, working — `(player_id, provider_name, provider_player_id)`, `resolve_player_ids()` read-only, unchanged since Phase 8.3D |
| Team/provider identity | `team_provider_ids` real, working, 12 real `mysportsfeeds` rows exist (2 from Phase 8.2, 10 seeded Phase 8.3A) |
| Phase 8.1 contextual engine expectations | `app.context_intelligence.engine.build_contextual_intelligence` (ai-orchestrator) composes 10 dimensions per call; `player_performance` is currently one of six fixed `insufficient_evidence=True` stubs (`unsupported.py`). `ContextualDimensionResult.sample_size`/`provenance`/`facts` are explicitly designed around "real comparable historical data points" — i.e. multiple real, dated, game-scoped observations per player, which season-aggregate data structurally cannot supply (Phase 8.3D §10's own boundary). **Not modified this pass, per explicit guardrail.** |

**What is missing:**
1. A real MySportsFeeds player-gamelogs adapter/persistence path — never
   built, never called (confirmed: `grep` for `player_gamelogs`/
   `gamelog` across `app/adapters/` and `app/persistence/` returns
   nothing outside SDK-table references already surveyed in the
   2026-09-08 Player/Team Performance Data Audit).
2. Any real captured `player_gamelogs` payload of any kind — the SDK
   feed key has existed in this project's vendored copy since the very
   first bake-off, and has never once been called (re-confirmed this
   pass, same finding as every prior Phase 8.3 audit).
3. `player_stats.py`'s own generalization to a real `provider_name`
   parameter (still hardcoded to `sportsdataio`) — same disclosed,
   unfixed gap `team_stats.py` had before Phase 8.3A.

**Stale reference found, not fixed (out of scope):** `unsupported.py`'s
own `player_performance`/`roster_role`/`team_performance`/`depth_lineup`
reason text still cites the Phase 8.0.5 closeout's "fixture/seed-only"
characterization, which Phase 8.2/8.3A have since made partially
inaccurate (real `roster_memberships`, real `team_stats` rows now
exist). Flagged per this project's own "disclose drift rather than
silently improvise" discipline — not touched, per this pass's explicit
"No Phase 8.1 logic changes" guardrail.

## 2. Likely MySportsFeeds endpoint/path

From the vendored `mysportsfeeds-node` SDK's own feed table
(`API_v2_0.js`, re-inspected this pass, zero live calls):

```
seasonal_player_gamelogs: { season: true, endpoint: 'player_gamelogs' }
daily_player_gamelogs:    { season: true, path: [{key:'date', value:'date'}], endpoint: 'player_gamelogs' }
weekly_player_gamelogs:   { season: true, path: [{key:'week', value:'week'}], endpoint: 'player_gamelogs' }
```

**Likely real endpoint: `GET /nfl/{season}/player_gamelogs.json`**
(`seasonal_player_gamelogs`) — no mandatory path segment, same shape
family as `seasonal_player_stats`/`seasonal_team_stats`, both already
confirmed real (Phase 8.3A/8.3C). Base URL and Basic-auth scheme are
the same already-confirmed-real values (`https://api.mysportsfeeds.com/
v2.1/pull`, `password="MYSPORTSFEEDS"` literal) — no new provenance
question there.

**A real, disclosed risk, not a guess dressed as fact:**
`seasonal_team_gamelogs` — the exact same "season: true, no path"
declared shape, same `_gamelogs` endpoint family — was attempted twice
in the original 2026-09-03 bake-off and returned `400` both times,
including once with a `team` filter added, and remains explicitly
unresolved (HQ has separately, repeatedly barred retrying it). This
does **not** prove `player_gamelogs` will also fail — it is a sibling
endpoint, not the same one — but the shared family/shape is a real
signal worth carrying into risk assessment, not something to ignore.

## 3. Confirmed vs. unknown request parameters

| Detail | Classification | Basis |
|---|---|---|
| Feed key `seasonal_player_gamelogs` → endpoint `player_gamelogs` | **Confirmed by code** | `API_v2_0.js` feed table |
| Base URL, Basic auth scheme | **Confirmed by code/docs**, already live-proven for sibling endpoints | Same value as every real MSF call this project has made |
| No mandatory path segment for the seasonal variant | **Confirmed by code** | Same `feeds` table entry |
| A `player` filter param, by exact name, is valid for this exact feed key | **Confirmed by docs** — stronger provenance than Phase 8.3C's `team` filter | SDK README's own v2.0 usage example is for `seasonal_player_gamelogs` by name: `msf.getData('nba', '2016-2017-regular', 'seasonal_player_gamelogs', 'json', {player: 'stephen-curry'})` |
| Exact NFL player identifier format for the `player` param (numeric MSF id vs. a name-slug like `'stephen-curry'`) | **Unknown** | The only documented example uses an NBA name-slug; every real NFL identifier this project has ever resolved against MySportsFeeds (rosters, lineup, player_stats_totals) has used the numeric `player.id`, never a slug — genuinely untested which this feed expects |
| Whether a `team` filter (Phase 8.3C's own confirmed-working pattern) also works on this feed | **Unknown** — not documented for this specific feed key, only for the sibling `player_stats_totals`-family endpoint by a weaker (v1.x ancestor) analogy | Disclosed, not assumed |
| Response shape (per-row fields, whether a row carries a nested `game` object, a `date`, week number, opponent, or some combination) | **Unknown** — no real payload has ever been observed | Nothing to infer from; `game_boxscore`/`game_playbyplay`/`game_lineup` (the other real per-game MSF feeds this project has captured) all carry a `game.id` numeric field, which is a plausible analogy, not confirmed for this feed |
| Whether the seasonal variant returns one row per game (a true "log") or an aggregate | **Strongly implied "one row per game"** by the feed's own name and its `daily`/`weekly` siblings' existence (which would be redundant if the seasonal variant weren't already game-by-game) | Not confirmed |
| Pagination behavior for a full-season, single-player result set | **Unknown** | Never tested |

No parameter is invented or assumed usable beyond what's listed above as
confirmed/strongly implied.

## 4. Canonical model

**Smallest provider-neutral game-level contract**, extending the exact
pattern Phase 8.3D already established for season-scoped stats — no new
architecture invented, the same three-layer separation applied one level
deeper:

```python
@dataclass
class PlayerGameStatLine:
    player: str              # provider-native player identifier
    game: str                # provider-native game identifier
    stats: dict               # opaque, provider-native payload
```

This is deliberately **not** a new model — it is `PlayerStatLine`
(`app.adapters.models`), which already has exactly this shape
(`game_external_id, player_external_id, ..., team, stats`) and an
existing, real, working persistence path
(`app.persistence.player_stats.persist_player_stats`, `(game_id,
player_id)`-keyed idempotent-correction writer, DB-level append-only
via `block_snapshot_updates()`). **The canonical persistence
architecture for game-level player stats already exists and needs zero
new code** — only a new MySportsFeeds *adapter* producing real
`PlayerStatLine` objects from `player_gamelogs.json`'s real (currently
unknown) shape, matching this whole arc's own repeated "MySportsFeeds
is an adapter, not the canonical model" instruction.

Mapped against HQ's seven required properties, all already satisfied by
the existing `player_stats` table + `PlayerStatLine` model + existing
identity-resolution modules:

| Requirement | Existing mechanism |
|---|---|
| Canonical player_id | `player_id`, resolved via `resolve_player_ids()` |
| Canonical game_id | `game_id`, resolved via `resolve_game_ids()` |
| Team context | `PlayerStatLine.team` (adapter-supplied, not persisted as its own column today — same as the game-scoped path already in production) |
| Provider identity | Same disclosed gap as Phase 8.3D §1/§11 — see §9 below |
| Observed/captured time | `created_at` (auto-set) |
| Opaque sport-specific stats payload | `stats` jsonb, unconstrained |
| Correction/history behavior | The existing `_latest_player_stats_row` (game_id-keyed) + DB-level append-only trigger — already real, already tested, already in production for the game-scoped path |

No migration is anticipated for the canonical model itself.

## 5. Player/game identity resolution

**Player side: fully solved, reuse verbatim.** `resolve_player_ids()`
(unchanged since Phase 3E-8/8.3D) maps `provider_player_id ->
players.id` via `player_provider_ids`, read-only, no name-based
matching anywhere. A gamelog row's player id resolves through the exact
same mechanism Phase 8.3D's season-scoped path already uses.

**Game side: mechanism exists (`resolve_game_ids()`/`game_provider_ids`,
unmodified), but the exact per-row provider game identifier this feed
supplies is genuinely unknown (§3).** Two resolution paths, both
supportable by existing code with zero new persistence logic, chosen
based on what the real payload turns out to contain:

- **If a row carries a numeric `game.id`** (matching the pattern
  `lineup.json`/`game_boxscore`/`game_playbyplay` already use): resolve
  directly via `resolve_game_ids(provider_name="mysportsfeeds",
  provider_game_ids=[str(row["game"]["id"])])` — identical to how
  `player_stats.py`'s existing game-scoped path already resolves
  `PlayerStatLine.game_external_id` today. No ambiguity.
- **If a row instead only carries a date + week + opponent** (no
  explicit game id): a genuine ambiguity case. Fail-safe behavior,
  matching this project's own "never guess" convention used everywhere
  else: such a row would need to correlate against `games` by
  `(scheduled_start date, home_team, away_team)` — a real join, not a
  direct id lookup — and **any row that cannot be resolved to exactly
  one `games` row unambiguously must be reported as unresolved, never
  guessed to the nearest match.** This exact fallback pattern is not
  yet built anywhere in this codebase (every existing `resolve_*_ids`
  function is a direct id-to-id lookup) — if the real payload turns out
  to need it, it is new, disclosed design work for a future
  implementation pass, not assumed solved today.

**No name-based joins are proposed anywhere in this design**, matching
HQ's explicit instruction.

## 6. Contextual dimensions unlocked

Once real game-level player stats exist (not before — Phase 8.3D's own
season-total boundary still holds until this is built):

| Dimension | Becomes possible? |
|---|---|
| Weather-conditioned performance | **Yes** — a per-game player stat row joined to that same game's real `weather_snapshots` row (already real, Phase 8.0.5) |
| Opponent-conditioned performance | **Yes** — join on the game's own `home_team`/`away_team` |
| Venue-conditioned performance | **Yes** — join via the game's existing `venue_id`/venue context (already real, Phase 8.0.5) |
| Teammate-conditioned performance | **Yes**, partially — requires cross-referencing multiple players' rows for the same game, plus real roster/lineup context (Phase 8.2) for who else was actually on the field; the stat rows alone give co-occurrence, not on-field overlap without lineup data |
| Recency/form | **Yes** — the entire point of a dated, per-game series; impossible from season totals alone (Phase 8.3D §10) |
| Usage changes | **Yes** — per-game `snapCounts`/`gamesPlayed`-equivalent fields (if present, see §7) compared week-over-week |
| Lineup/role × production | **Partially** — needs both this feed's real stats AND Phase 8.2's real depth/lineup data joined together; neither alone is sufficient |
| Market/context comparisons | **Yes**, in combination with Phase 8.1's already-real `market`/`weather`/`venue` dimensions once `player_performance` stops being a fixed stub |

**Still requires other, separately-blocked data even after this feed is
real:**
- **Injuries** — real per-game player performance still can't be
  correctly contextualized against "was this player actually healthy
  that week" without real injury data, which remains BALLDONTLIE-
  blocked (unpaid invoice, per the existing `unsupported.py` entry, not
  touched this pass).
- **PBP/game state** — situational context (score differential,
  time-of-game, game script) needs `game_events`/play-by-play, which
  remains raw-capture-only and deferred to the 2026-09-09/10 live-game
  validation window (existing, unmodified `unsupported.py` entry).
- **Richer matchup/coverage data** — e.g. which specific defender
  covered a receiver — is not part of any MySportsFeeds feed this
  project has inspected; would need a materially different, unaudited
  data source.

## 7. Expected participation/usage coverage

**Do not claim support beyond what's confirmed.** No real
`player_gamelogs` payload has ever been observed, so nothing here is
"confirmed" — everything is either a documented schema signal or an
analogy to the sibling `player_stats_totals` feed (Phase 8.3C's own
real, confirmed per-player fields: `gamesPlayed`, `snapCounts.
{offenseSnaps,defenseSnaps,specialTeamSnaps}`, `miscellaneous.
gamesStarted`).

| Field | Classification |
|---|---|
| Games played (as a per-game log, this would be implicit — one row per game played) | **Strongly implied** by the feed being a "log" |
| Started | **Unknown** — `player_stats_totals`'s own `gamesStarted` was present but uniformly zero for all 43 real players sampled (Phase 8.3C); whether a per-game log carries a more granular/reliable started flag is untested |
| Offense/defense/special-teams snaps | **Unknown** — plausible by analogy to `player_stats_totals`'s real, confirmed `snapCounts` block (same provider, same stat family, same season), but per-game granularity for this specific field has never been observed |
| Targets/carries/routes/usage proxies | **Unknown** for routes specifically (never seen in any real MySportsFeeds capture this project has made, season or otherwise) — targets and carries are plausible by analogy to `player_stats_totals`'s real `receiving.targets`/`rushing.rushAttempts` fields, again untested at per-game granularity |

## 8. Execution safety for a future live diagnostic

Any future Phase 8.4B live call must reuse this project's now-proven
mechanism exactly, per HQ's explicit instruction — no new framework:

1. **`activation_run_markers`**, reused verbatim (Phase 8.3A/B/C's own
   mechanism), with a new dedicated `run_key`
   (e.g. `phase-8.4b-player-gamelogs-diagnostic-<date>`) — never a
   second idempotency table.
2. **Exception-safe end to end**, matching Phase 8.3C's own fix (built
   after Phase 8.3B's uncaught timeout crashed application startup):
   every network call (the marker claim and the live MSF request) wrapped
   in `try/except`, returning a structured result rather than raising;
   the `main.py` startup hook itself adds one more outer guard so a
   diagnostic failure of any kind can never crash startup or fail the
   healthcheck.
3. **120-second timeout as the default starting point**, not 30s — Phase
   8.3B/8.3C's own real lesson, applied proactively this time rather
   than rediscovered.
4. **Exact once-only behavior across Railway redeploys** is already
   proven, not just designed — Phase 8.3A and Phase 8.3B both actually
   raced two overlapping containers for the same run_key in production
   and the guard held both times (one clean skip, zero duplicate calls
   or writes). No deployment-flag-only safety: the flag
   (`RUN_MSF_*_DIAGNOSTIC=1`) only decides whether the hook runs at
   all; the marker decides whether it's allowed to make the live call,
   and that's the layer that actually prevented duplication in both
   real incidents.

## 9. `provider_name` schema debt

**Assessment: not yet important enough to fix before game-level
persistence — same conclusion as Phase 8.3D §1/§11, re-examined and
reconfirmed, not just carried forward unexamined.** The condition that
would make this urgent (two different providers concurrently writing
real player-stats rows into the same `player_stats` table, for
overlapping players/games/seasons, with no column-level way to tell
which wrote a given row) does not exist today: `sportsdataio`'s
game-scoped path and a future `mysportsfeeds` game-scoped path would
both write into the same table, but only one provider has ever had real
data flowing through it at a time in this project's actual history, and
`player_provider_ids` already durably records which provider identified
which player. Building game-level `player_gamelogs` persistence does
not change this calculus — it's the same table, same gap, same
non-urgency.

**If HQ decides this is worth fixing before game-level persistence
anyway** (e.g. to make historical provenance queryable directly, not
just inferable), the smallest symmetric migration would be:

```sql
alter table team_stats add column provider_name text;
alter table player_stats add column provider_name text;
```

Nullable (backward-compatible with every existing row, matching this
project's own established "widen, never break existing rows"
convention), backfillable later by joining each row's `team_id`/
`player_id` against `team_provider_ids`/`player_provider_ids` for rows
where exactly one provider mapping exists (ambiguous for a
multi-provider player/team, which would need to stay null rather than
guessed). **Not applied this pass** — audit only, per explicit
guardrail.

## 10. Raw capture policy for the eventual live call

**Recommended: chunked logging, reusing the exact existing
`logger.warning()` mechanism — no new infrastructure.** Phase 8.3C's
real failure was a single `json.dumps()` call producing one log message
that Railway truncated at exactly 80KB (81,920 characters). The fix:
split the serialized JSON into fixed-size chunks well under that limit
(e.g. 70,000 characters, leaving headroom for the log-line prefix) and
log each chunk with an explicit sequence marker:

```
MSF_PLAYER_GAMELOGS_RAW_CHUNK 1/4 <chunk text>
MSF_PLAYER_GAMELOGS_RAW_CHUNK 2/4 <chunk text>
...
```

reassembled afterward by concatenating chunks in order when reading the
Railway deploy log — the exact recovery technique already proven this
session (Phase 8.3C's own balanced-brace partial-JSON recovery), just
applied proactively via chunking instead of reactively via partial
recovery.

**Considered and not recommended for a single diagnostic pass:** a
dedicated raw-capture table matching `game_events.raw_payload`'s own
pattern (append-only, `raw_payload jsonb not null`, RLS + public-read
policy). This is a real, existing, repo-compatible mechanism — but it's
scoped to per-event PBP data (`sequence_number`, `period`, `clock`),
not a general-purpose diagnostic-payload store, and using it for this
purpose would mean either misusing its schema or adding a new
migration — both out of scope for a single audit-authorized diagnostic.
Chunked logging achieves the same durability goal (a human/future
session can reconstruct the full payload from the deploy log) with zero
schema change and zero new persistence code, matching HQ's own
preference ordering ("prefer direct safe file capture, chunked
logging, or another existing mechanism").

**No secrets risk**: the payload is real vendor player-performance
data, the same category already committed as a fixture in Phase 8.3C
with no issue — this recommendation carries the same "no secrets"
property, verified the same way (grep before commit) before any future
chunk-derived fixture is committed.

---

## Recommendation for Phase 8.4B (exactly one narrow live diagnostic)

**One `GET /nfl/2025-2026-regular/player_gamelogs.json?player=9999`**
(Hunter Henry, MSF numeric id `9999`, the single most cross-verified
real identity in this entire project — confirmed consistent across
`players.json`, `lineup.json`, and `player_stats_totals.json` across
three separate Phase 8.2/8.3 passes) — a single-*player* filter, not
Phase 8.3C's team-wide filter, because:

1. It directly tests the one **documented** filter parameter for this
   exact feed key (§3) rather than a weaker cross-family analogy.
2. It minimizes payload size (one player's full-season game log, at
   most 17 rows, versus a whole team's roster) — directly reduces both
   the Railway-truncation risk (§10 fixes it regardless, but a smaller
   payload is still safer) and the blast radius of an unexpected result.
3. It answers every currently-UNKNOWN item in §3/§7 in one shot: whether
   `player` is the right param name for NFL and what value format it
   expects (try the numeric id first, since that's this project's own
   established real-identifier convention, not the documented NBA
   slug), the real per-row shape (game id field vs. date/week/opponent),
   and real participation/usage field presence — using the same
   "prefer a request that answers the most unknowns in one call"
   principle Phase 8.3B/8.3C's own directives already established.
4. If it fails (400/timeout/empty), per HQ's own recurring "no repeated
   probing" discipline this project has followed all session, the
   fallback investigation (documented pagination, alternate scoping,
   provider behavior) happens in the NEXT authorized pass, not by
   silently retrying within the same one.

No provider call was made this pass. No persistence code, migration, or
Phase 8.1 logic was changed. All findings above are classified exactly
per HQ's confirmed/strongly-implied/unknown framework — nothing is
presented as more certain than its actual evidence supports.
