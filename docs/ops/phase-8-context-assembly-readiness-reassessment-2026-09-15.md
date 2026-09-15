# Phase 8 Context Assembly Readiness Reassessment (2026-09-15)

**Status: AUDIT ONLY. No new context scoring, no probability-modeling
changes, no provider calls, no schema changes, no model wiring, no
recommendation work.** MANSA HQ directive: "PHASE 8 CONTEXT ASSEMBLY
READINESS REASSESSMENT," following the close of all MSF/postgame
infrastructure work. Builds directly on `docs/ops/phase-8-context-
intelligence-readiness-audit-2026-09-09.md` (the prior baseline) and
`docs/ops/phase-8-context-assembly-integration-design-2026-09-09.md` (the
JOINED/PARTIAL/UNAVAILABLE vocabulary this document reuses) -- every
finding below was re-verified against current live DEV data and current
repository source, not carried forward from either prior document
uncritically. Real time at audit start: 2026-09-15 09:59:54 UTC.

---

## 0. Headline finding, stated up front

**The single most important thing this reassessment found is not in the
directive's own checklist: every one of the 16 real, MSF-confirmed-
complete games persisted so far belongs to the same NFL week (2026-09-10
through 2026-09-15).** No real player anywhere in the database has more
than one real per-game `player_stats` row yet (`SELECT player_id, count(DISTINCT
game_id) ... HAVING count(DISTINCT game_id) > 1` returns **zero rows**,
confirmed live). This means the directive's Section 3 request -- "identify
the best real player for a Context Assembly Proof across 2-3 completed
games" -- **cannot be satisfied with real data today, for any player,
regardless of coverage otherwise.** This is disclosed here in full,
per the blueprint-vs-reality discipline, rather than substituting a
weaker interpretation of "2-3 games" or quietly narrowing scope. Section
3 below names the strongest available single-game candidate and the exact
condition (Week 2 completing, ~2026-09-21/22) that would make a genuine
2-3-game proof possible.

---

## 1. Readiness matrix (rebuilt, live-verified 2026-09-15)

Vocabulary per HQ's directive: **JOINED** (a real row exists for the exact
target entity + timestamp, or the fact is static/time-invariant, and
retrieval code exists), **PARTIAL** (real data exists but with a named
caveat), **UNAVAILABLE** (no real row, no code path, or schema-only).
Current-state data is never counted as historical evidence (games marked
JOINED below rely only on tables whose rows carry an explicit `game_id`
or `captured_at`/`observed_at` anchor, never `daily_game_intelligence`,
which is overwritten-per-refresh and current-only by design).

| # | Dimension | Status | Actual persisted source | Historical/point-in-time capability | Join key | Timestamp semantics | Sample coverage (live, 2026-09-15) | Exact limitation |
|---|---|---|---|---|---|---|---|---|
| 1 | Historical player performance | **JOINED** (single-game only) | `player_stats` (`game_id`-scoped, real MSF box scores) | Yes for a game already captured -- the row IS the historical fact, not a snapshot series, so no point-in-time resolution is needed for it (unlike weather/injuries/depth) | `player_id` + `game_id` | The row has no `captured_at`; it represents the completed game itself, keyed by `game_id` alone | 1,551 real rows, 1,482 distinct players, 16 real completed games (all Week 1, 2026-09-10 through 2026-09-15) | **No player has more than 1 real historical game yet** (verified live, zero exceptions) -- a genuine multi-game trend/form signal does not yet exist for anyone. Separately, one game (SEA@NE) carries a real duplicate-row artifact: 69 rows from a pre-dispatcher diagnostic-era capture (2026-09-10 20:38 UTC) coexist with the real dispatcher-driven capture (2026-09-14 23:02 UTC) for the same players -- `player_stats` has no uniqueness constraint on `(player_id, game_id)`, so a naive reader gets 2 rows for those 93 players. Every other one of the 15 real games is clean (1 row per player, confirmed live). MSF's own payload separately flags `snapCounts`/`miscellaneous.gamesStarted` as unreliable at this tier (observed uniformly zero for real, otherwise-productive players) -- already disclosed in the persisted `stats._unreliable_fields_reason` field itself, not a new finding. |
| 2 | Opponent/matchup | PARTIAL (identity real; ratings unavailable) | Identity: `games.home_team`/`away_team`. Ratings: `matchup_scores`/`offensive_matchup_scores`/`defensive_matchup_scores` | Identity: yes, trivially (every game has a fixed opponent). Ratings: no | `game_id` | Identity: none needed (static per game). Ratings: N/A, no real rows | Identity: 100% of games. Ratings: 1 row each in all three tables, and that row is fixture-linked (`game_id=a5000000-...-000000000003`/`...001`, the seed-fixture UUID pattern, not a real game) | Unchanged since 2026-09-09. Zero real rows, zero reading/writing application code for the ratings tables; opponent identity itself was never in question. |
| 3 | Teammate availability/dependency | **UNAVAILABLE** | -- none -- | No | -- | -- | 0 | Unchanged since 2026-09-09. Still zero code anywhere expressing this concept, not even a stub. Nothing in the MSF/postgame substrate closes this -- `player_stats` records what a player DID, never whether a teammate's absence explains it. |
| 4 | Injuries | **UNAVAILABLE** | `injury_reports` (real, append-only schema) | Partial code exists (`resolve_injury_point_in_time`, built 2026-09-09, unwired) but there is nothing real to resolve | `game_id` + `captured_at` | Point-in-time resolver exists and is correct (event/observed/retrieved timestamps kept distinct) | **1 total row, and it belongs to a fixture game** (`Dallas Cowboys@Baltimore Ravens`, seed UUID), confirmed live -- zero real rows for any of the 16 real games | The MSF/postgame pipeline never touches this table (BALLDONTLIE is the only injuries provider and its billing block was never addressed this session -- out of scope for MSF work, and no provider call was made this pass to re-check it). This dimension is **not** solved by the substrate that changed. |
| 5 | Lineup/depth | PARTIAL (2 of 32 teams, current-only pregame snapshot) | `roster_memberships` (34 real rows) + `depth_chart_snapshots` (4 real rows) -- both team-scoped | Point-in-time resolver exists (`resolve_lineup_point_in_time`, unwired) and both real teams' rows were captured (2026-09-08) before the one game (SEA@NE, 2026-09-10) that could use them, so a point-in-time query against them is genuinely historically valid for that one matchup | `team_id` + `observed_at`/`captured_at` | Real `observed_at`/`captured_at` timestamps exist and predate the only eligible game | Exactly 2 of 32 teams (New England Patriots, Seattle Seahawks) -- unchanged since Phase 8.2 (2026-09-08); no roster/depth-chart activation happened during any MSF/postgame pass | Still no end-dating (can't represent "released"); still never represents active/inactive status for a specific game, only "who the roster/depth chart said as of a capture date." Coverage is exactly the two teams that happen to be in the one game this whole matrix's strongest candidate depends on -- every other real game (all 15 Sunday/MNF games) has **zero** lineup/depth coverage at all. |
| 6 | Weather | PARTIAL (real for a minority of games; historical path built but unwired) | `weather_snapshots` (real, append-only) | Yes -- `resolve_weather_point_in_time` (2026-09-09, unwired) is correct and reusable | `game_id` + `captured_at` | Real, distinct from event/retrieval time | 4 real rows across 4 real games (SEA@NE, PHI@WAS, LAC@ARI, and one pre-existing fixture-adjacent row) -- 12 of the 16 real completed games have **zero** weather rows | Coverage gap is pre-existing (Weather Activation only began 2026-09-07) and untouched by this session's MSF work -- not newly solved or newly broken. |
| 7 | Venue/surface | PARTIAL (leans JOINED for static facts; no surface field) | `venues`/`canonical_venues`, `games.venue_id`/`venue_lat`/`venue_long`/`venue_type` | Yes -- facts are time-invariant | `game_id` -> `venue_id` | N/A (static) | 100% of games have a `venue_id`; real, retrievable | Unchanged since 2026-09-09: no dedicated turf/grass "surface" column exists anywhere; `venue_type` covers indoor/outdoor/dome only. |
| 8 | Home/away | **JOINED** | `games.home_team`/`away_team` | Yes -- static per game, always correct for any past game | `game_id` | N/A (static) | 100% of games (real and fixture alike) | None of substance -- this is the one dimension with no real limitation; it was implicitly real in the 2026-09-09 audit too but not given its own row there. |
| 9 | Rest | PARTIAL (fields real; computation code still missing) | `games.scheduled_start` per team (the same fields the travel path already fetches) | The raw data is historically re-derivable for an arbitrary past game (same underlying query shape as travel's `find_previous_final_game`), but no function computes it | `team_id` + `scheduled_start` | N/A -- would be derived, not stored | N/A -- not computed anywhere | Unchanged since 2026-09-09. Still a code gap layered on a data non-gap; MSF/postgame work never touched `app/features/travel.py` or any rest-computation path (confirmed via `git log --since=2026-09-09 -- apps/ai-orchestrator/` -- only `point_in_time.py` changed in that whole window). |
| 10 | Travel | **JOINED** (real, historical-capable, already wired to the model) | `games` (scheduled_start, venue fields) | Yes -- `find_previous_final_game` takes an explicit `before` timestamp | `team_id` + `scheduled_start` | Real, explicitly historical-safe by construction | Full coverage, any team/date | Unchanged since 2026-09-09: `consecutive_road_games` is still a dataclass field that's never populated. Only dimension besides odds that is both real AND wired into `build_evidence()` today. |
| 11 | Role/usage | PARTIAL (newly real for the single covered game per player; one sub-field explicitly flagged unreliable) | `player_stats.stats` jsonb (`targets`, `receptions`, `rushAttempts`, `snapCounts`, etc.) | Same as Dimension 1 -- the row itself is the historical fact for whichever single game exists | `player_id` + `game_id` | Same caveat as Dimension 1 | Same 1,551 rows / 1,482 players / 16 games as Dimension 1 | This is the same underlying data as Dimension 1 viewed through a "how was this player used" lens rather than "what did they produce" -- separated here because the directive lists them separately. `targets`/`receptions`/`rushAttempts` etc. are real and trustworthy (confirmed non-zero, varied, plausible for real players in Section 3's candidate below); `snapCounts` and `miscellaneous.gamesStarted` are explicitly self-flagged unreliable by the pipeline's own persisted `_unreliable_fields_reason` (observed uniformly zero across a real 69-player payload including players with substantial other production) -- a genuine "how much did they play" signal is not safely available even where "what did they do" is. |
| 12 | Game state/script | **UNAVAILABLE** | `game_events` (real, append-only raw-capture table, MSF's own postgame pipeline writes to it) | No | `game_id` + `provider_event_id` | Schema supports it; never populated | **20 real rows now exist** (up from 0 at the 2026-09-09 audit -- the MSF postgame pipeline does write here), but every typed column (`period`/`clock`/`score_home`/`score_away`/`event_type`) is **still `null` on all 20**, confirmed live -- only an opaque `raw_payload` jsonb blob (the box-score response) is captured | The gating condition named in the 2026-09-09 audit ("the first real completed 2026 NFL game") has resolved 16 times over -- but the blocker was never the absence of a completed game, it was that no worker computes PBP-shaped typed fields from anything. MSF's postgame pipeline uses this table purely as a raw-capture landing zone for box scores, not play-by-play; the typed columns still have no writer. |
| 13 | Odds/market history | **JOINED** (real, historical-capable, already wired) | `odds_snapshots` | Yes -- real since Phase 7 | `game_id` + `captured_at` | Real, distinct concepts, already disciplined (`latest_*`, never `closing_*`) | 1,258 total rows; 189 for the strongest candidate game alone (SEA@NE) | Unchanged since 2026-09-09: no genuine "closing line" marker exists architecturally, self-disclosed in the relevant agent's own code, not merely an oversight. |

---

## 2. New substrate -- which previous blockers are genuinely solved

Going through the directive's explicit list:

- **Permanent MSF player-game persistence**: real and working. **Solves**
  the 2026-09-09 audit's #1-ranked blocker ("per-game player performance
  substrate") -- but only in the narrow sense of "the pipe now carries
  real data when a game completes." It does **not** solve the deeper
  claim that blocker implied (a usable *historical* signal spanning
  multiple games), because every completed game so far is the same NFL
  week. This is the headline finding in Section 0.
- **Automatic postgame enrollment**: real and working (proven this
  session via DEN@KC and NE@SEA, both discussed at length in prior
  reports). Solves the *operational* half of blocker #1 (data won't stop
  flowing as new games complete) but is orthogonal to the *data
  availability* half -- it doesn't create games that haven't been played
  yet.
- **Sunday 13-game ingestion + NE@SEA + SF@LAR + DEN@KC**: together these
  are the entire real substrate audited in Section 1 -- 16 real games, all
  Week 1. Confirmed live, not assumed.
- **Point-in-time resolver** (`app/context_intelligence/point_in_time.py`,
  built 2026-09-09, re-read in full this pass): real, correct, and
  **still completely unwired** -- not called from `engine.py`, any
  dimension module, or `build_evidence()`. It is the correct mechanism
  for weather/injuries/lineup's snapshot-series tables; `player_stats`
  itself doesn't need it (Dimension 1's own note -- a completed game's
  box score isn't a snapshot series to resolve "as of" a timestamp, it
  simply exists once a game is captured).

**Genuinely solved** (narrow, precise claims only):
1. Real per-game player statistical performance exists as data, for the
   first time ever in this project, for 1,482 real players across 16 real
   games -- Dimension 1/11's prior **UNAVAILABLE** verdict is now false as
   a blanket statement (it is JOINED for a covered game/player pair).
2. Real MSF `game_provider_ids` mapping now exists (16 rows) -- the
   2026-09-09 audit's Gate B finding ("no persisted mapping row found")
   is resolved; game/event identity linkage for MSF specifically is
   materially stronger.
3. `game_events` now has real rows (20) rather than zero -- but this
   only partially closes the 2026-09-09 gate ("gated on the first real
   completed 2026 NFL game"); the game existing was never sufficient on
   its own, and the typed-column gap (Dimension 12) remains fully open.

**Explicitly NOT solved** by this substrate, contrary to what a
surface reading of "MSF/postgame infrastructure work is closed" might
suggest:
1. Multi-game historical trend/form data for any player (Section 0).
2. Injuries (BALLDONTLIE billing untouched; zero real rows for any real
   game).
3. Teammate dependency, opponent/matchup ratings, team_performance
   (zero-built, untouched).
4. Lineup/depth breadth (still 2/32 teams; MSF/postgame work never
   touched roster/depth-chart activation).
5. Game state/script typed fields (raw capture now real; typed PBP
   fields still uniformly null).
6. `build_evidence()` wiring (byte-identical to 2026-09-09, confirmed by
   direct re-read -- see Section 5).
7. `data_completeness` field on `ContextualDimensionResult` -- the
   2026-09-09 design doc recommended adding this; it was never built
   (confirmed by direct re-read of `context_intelligence/models.py`).

---

## 3. Strongest real proof candidate

**Recommended candidate: Jaxon Smith-Njigba (Seattle Seahawks, WR),
SEA@NE (2026-09-10), ONE completed game -- not 2-3.**

**Why not Hunter Henry** (the presumptively "default" name per the
directive's own explicit instruction not to force him): both players are
real, both are on a roster/depth-chart-covered team, both played in the
one game with the richest cross-dimensional coverage in the entire
database. But Jaxon Smith-Njigba's real stat line is materially deeper:

| | Hunter Henry (NE, TE) | Jaxon Smith-Njigba (SEA, WR) |
|---|---|---|
| Targets | 3 | 11 |
| Receptions | 3 | 8 |
| Receiving yards | 26 | 122 |
| Receiving TD | 0 | 1 |
| 20+/40+ yard plays | 0 / 0 | 2 / 1 |

Both rows are real, both were confirmed live, both carry the same
NE@SEA-specific duplicate-row caveat (Dimension 1's limitation column --
each player has exactly 2 identical rows, one from the 2026-09-10
diagnostic-era capture and one from the 2026-09-14 real dispatcher
capture, byte-identical stats in both). Smith-Njigba's usage volume
(11 targets, 122 yards, a touchdown) gives a Context Assembly Proof
something substantive to describe across role/usage, performance, and
market-movement dimensions simultaneously -- Henry's 3-target, 26-yard
line is real but too thin to demonstrate what a context package can
actually say about a player.

**Why SEA@NE is the strongest available game, full stop** (not merely
"the only one with roster data"): cross-referencing Section 1's matrix,
it is the **only one of the 16 real games with simultaneous real coverage
across all of**: player performance (162 rows, 93 distinct players),
lineup/depth (both teams, point-in-time-eligible), weather (1 real
snapshot), odds/market (189 real snapshots), and team-level news (this
exact game -- SEA/NE -- was one of the 5 real games already cross-
referenced against real news/market-movement data in the 2026-09-13
"Real History Observation Window" pass, with 0 `UNEXPLAINED_MARKET_
MOVEMENT` results). No other real game in the database has more than 3
of these 5 real, non-fabricated dimensions simultaneously.

**Why 2-3 games is not possible today, restated plainly**: every one of
the 16 real games shares the same kickoff week. The very first moment a
2-3-game proof becomes possible is once a *second* real week of games
completes and is ingested by the same, already-proven automatic
enrollment/dispatch pipeline -- NFL Week 2 would begin roughly
2026-09-17/18, with games completing and auto-enrolling through
2026-09-21/22 given the existing pipeline's own unchanged behavior. No
code change is required for that to happen; it requires only real time
passing and MSF access remaining available long enough to capture it
(see the MSF cancellation finalization already recorded: real access
through 2026-09-17 only -- **Week 2 games will very likely complete
after MSF access has already ended**, which is a real, material
constraint on ever reaching a 2-3-game real proof for any player via
MSF, not merely a timing inconvenience). This is disclosed here as a
direct consequence of the already-recorded provider status, not a new
decision.

---

## 4. Proof path trace -- what MANSA could assemble today for Jaxon Smith-Njigba, SEA@NE, 2026-09-10

For the one real historical game available:

- **Player identity**: JOINED. Real `players` row, real `player_provider_ids`
  row (`mysportsfeeds`, provider ID `79758`, confirmed live).
- **Game identity**: JOINED. Real `games` row, real MSF `game_provider_ids`
  mapping.
- **Historical player performance**: JOINED. 11 targets, 8 receptions, 122
  yards, 1 TD, 2 explosive plays (20+ yards) -- real, persisted, traceable
  to a specific `game_id`. **Caveat carried forward, not silently
  resolved**: 2 identical rows exist for this exact player/game (the
  duplicate-row artifact from Section 1); a real assembly must either
  dedupe (e.g., prefer the later `created_at`, i.e. the real dispatcher
  capture) or explicitly surface both with a note -- fabricating a single
  "clean" answer without disclosing the duplicate would violate the "do
  not fabricate missing context" instruction just as much as inventing
  data would.
- **Role/usage**: PARTIAL. Targets/receptions/yards are trustworthy;
  `snapCounts.offenseSnaps` for this exact player/row is present (45,
  in one of the two duplicate rows; 0 in the other -- itself evidence of
  why the duplicate matters) but the pipeline's own self-disclosed
  `_unreliable_fields_reason` says not to treat `snapCounts` as a
  reliable participation signal at this tier.
- **Opponent/matchup**: PARTIAL. Opponent identity (New England Patriots)
  is real and trivial. No real defensive/matchup rating exists for New
  England -- that half stays UNAVAILABLE.
- **Teammate availability/dependency**: UNAVAILABLE. No code path exists
  to even ask "was Seattle's starting QB (Drew Lock, per the real box
  score) active/healthy," despite Drew Lock's own real stat line existing
  in the same game -- the *data* to describe what actually happened
  exists; the *concept* of dependency/correlation between two players'
  availability does not.
- **Injuries**: UNAVAILABLE. Zero real rows for this or any real game.
  Cannot be assembled at all, not even partially.
- **Lineup/depth**: PARTIAL. Real `roster_memberships` (captured
  2026-09-08, before this game's 2026-09-10 kickoff -- point-in-time
  valid) and real `depth_chart_snapshots` for Seattle (2 rows, both
  pre-kickoff). This tells MANSA Smith-Njigba was on Seattle's roster and
  what the depth chart said days before kickoff -- it does **not** confirm
  he was active/eligible for this specific game (that concept doesn't
  exist anywhere in the schema, per Dimension 5's limitation).
- **Weather**: JOINED. One real `weather_snapshots` row exists for this
  exact game.
- **Venue/surface**: PARTIAL, leans JOINED. Real venue identity/location/
  roof-type facts; no turf/grass field exists.
- **Home/away**: JOINED. Real, trivial (Seattle home, New England away).
- **Rest**: PARTIAL. The raw fields to compute both teams' days-of-rest
  exist (`games.scheduled_start`); no function computes it, so this
  cannot actually be produced today without new code -- would remain a
  documented gap in the assembled package, not a fabricated number.
- **Travel**: JOINED. Real, historically reconstructable, already
  code-complete via `find_previous_final_game`.
- **Game state/script**: UNAVAILABLE. A raw capture exists for this game
  (real box-score payload in `game_events.raw_payload`) but every typed
  field is null -- no score-by-quarter, no play-level detail can be
  produced.
- **Odds/market history**: JOINED. 189 real snapshots for this exact
  game; real line-movement math already exists and is already wired into
  the (separate, fan-out-committee) model path.

**Net**: of the 13 directive dimensions, this proof path would show
**5 JOINED** (player identity/game identity are folded into performance
and matchup above but are real; counting the 13-row matrix directly:
home/away, weather, travel, odds/market, and historical player
performance are cleanly JOINED for this specific player/game), **5
PARTIAL** (opponent/matchup, lineup/depth, venue/surface, rest,
role/usage), and **3 UNAVAILABLE** (teammate dependency, injuries, game
state/script) -- the most complete picture achievable anywhere in the
current database, and still genuinely incomplete, disclosed as such.

---

## 5. `build_evidence()` integration assessment

`apps/ai-orchestrator/app/agents/probability_modeling.py::ProbabilityModelingAgent.
build_evidence()` was re-read in full this pass. **Byte-identical to the
2026-09-09 audit's own quoted body** -- confirmed independently via
`git log --since=2026-09-09 -- apps/ai-orchestrator/`, which shows only
two commits in that entire window, both to `point_in_time.py` (adding the
resolver, then correcting its `completeness` semantics). Nothing in
`probability_modeling.py`, `engine.py`'s wiring, or `unsupported.py`'s
stub set changed. **Not modified by this audit either -- read-only
throughout.**

**Which historical-safe dimensions could be wired now, without new data
work:**
- **Odds/market, travel**: already wired -- no action needed.
- **Weather (historical variant), venue, news**: real, historical-safe,
  `ProvenanceRef`-backed, built since Phase 8.1 -- could be added to
  `build_evidence()` today via the one documented line
  (`"contextual_performance": contextual_intelligence.to_json()`)
  without any new persistence or provider work.
- **Historical player performance (new, as of this session)**: could be
  built as a new, real dimension module (replacing the
  `player_performance` entry in `UNSUPPORTED_DIMENSIONS`) using
  `player_stats` directly, for any of the 16 real games -- the gating
  dependency the 2026-09-09 audit named is now genuinely satisfiable for
  a *single* historical game per player. This would be a **new
  compute function**, not merely flipping a switch -- `unsupported.py`'s
  stub is unconditional and nothing today reads `player_stats` for
  contextual purposes.

**Which remain unsafe to wire:**
- **Injuries**: wiring this today would either wire a dimension that is
  permanently empty for every real game (since 0 real rows exist) or,
  worse, risk a future careless read of the one fixture row as though it
  were real -- unsafe until BALLDONTLIE's billing block is resolved.
- **Lineup/depth (roster_role)**: technically point-in-time-resolvable
  for exactly 2 of 32 teams. Wiring it now would create silently
  asymmetric coverage -- a consumer of `build_evidence()` has no way to
  know "this dimension is real for these 2 teams and structurally absent
  for the other 30" unless `data_completeness` (still unbuilt, see
  below) makes that explicit. Recommend against wiring until either
  broader roster activation happens or the completeness field exists to
  carry the asymmetry honestly.
- **Game state/script, teammate dependency, opponent/matchup ratings,
  team_performance**: no real data exists for any of these; wiring is
  not merely unsafe, it is not possible without new persistence work
  entirely.

**Where provenance must travel with evidence:** every new dimension wired
into `build_evidence()` must carry its own `ProvenanceRef` (table,
source, row_count, earliest_at, latest_at) exactly as the four existing
real Context Intelligence dimensions already do -- this is not a new
requirement, it is the standing discipline this codebase already built
and enforces for weather/market/news/venue. The new `player_performance`
dimension would need the same: a `ProvenanceRef` naming `player_stats`,
`row_count=1` (today, for any single covered player), `earliest_at`/
`latest_at` both equal to that one game's real capture timestamp.

**What would risk look-ahead leakage:** the single largest live risk
identified this pass is the **NE@SEA duplicate-row artifact** (Section 1,
Dimension 1) combined with the fact that `player_stats` carries no
`captured_at`/observation timestamp at all -- unlike weather/injuries/
depth-chart, there is currently no generic way to ask "which of these 2
rows for this player/game is the real one" using the point-in-time
resolver, because that resolver's whole mechanism depends on a
`timestamp_field` this table doesn't have. A future `player_performance`
dimension module would need its own explicit dedup rule (most plausibly:
join on `player_id`+`game_id` and take the single row from `created_at`,
until/unless a uniqueness constraint is added) -- documented here as a
real, specific risk this pass identified live, not a hypothetical. A
second, smaller risk: `game_id`-scoped historical rows are always
strictly in the past by construction (a game must be `confirmed_complete`
before any row exists), so the look-ahead risk is not "seeing a future
game's outcome" -- it is solely the duplicate-row ambiguity above.

**Minimum work required before the first safe Context Intelligence
integration** (documented, NOT built this pass):
1. A real compute function for `player_performance`, replacing its
   `UNSUPPORTED_DIMENSIONS` stub, reading `player_stats` directly with an
   explicit dedup rule for the known duplicate-row case.
2. The `data_completeness: "joined" | "partial" | "unavailable"` field
   the 2026-09-09 design doc recommended for `ContextualDimensionResult`,
   still unbuilt -- needed before wiring any dimension with genuinely
   asymmetric coverage (lineup/depth especially) so a consumer can tell
   "real but narrow" from "fully real."
3. The one documented `build_evidence()` line
   (`"contextual_performance": contextual_intelligence.to_json()`) --
   itself trivial, but per HQ's repeated "Do NOT reopen Phase 4"
   instruction, still requires separate authorization before it is
   written, exactly as the 2026-09-09 audit already concluded.

None of this was built or wired by this pass.

---

## 6. MSF constraint compliance

This audit made **zero MSF (or any other provider) calls** -- every
finding above came from already-persisted DEV data (live read-only SQL
against the existing tables) and already-committed repository source.
The already-recorded provider status (`docs/ops/phase-8-msf-pause-
backlog-safe-provider-state-2026-09-15.md`'s addendum: CANCELED -- ACCESS
THROUGH SEPT 17 -- THEN INTENTIONALLY PAUSED) is treated here strictly as
a forward-looking constraint on *future* data availability (Section 3's
"Week 2 will likely complete after MSF access ends" finding), never as a
reason to discount, downgrade, or omit any of the real evidence this
pass already possesses and confirmed live.

---

## 7. Recommendation for the smallest next implementation pass

**Recommendation: build the `player_performance` context-intelligence
dimension module first, wired nowhere yet (still not `build_evidence()`
itself -- that is a separate, later, Phase-4-reopening authorization).**

Concretely, the smallest real next step is:
1. A new `app/context_intelligence/player_performance.py` compute
   function, following the exact same pure/no-I/O convention as
   `weather.py`/`venue.py`, reading `player_stats` rows already fetched
   by `engine.py`'s "download once" convention, with an explicit,
   disclosed dedup rule for the known NE@SEA duplicate case.
2. Add the `data_completeness` field to `ContextualDimensionResult`
   (2026-09-09 design doc's own recommendation, still outstanding) at
   the same time, since the new dimension is the first one that would
   genuinely need to express "real, but for exactly 1 game" honestly.
3. Replace `player_performance`'s entry in `UNSUPPORTED_DIMENSIONS` with
   the new real compute function, following `engine.py`'s existing
   `SUPPORTED_DIMENSIONS` pattern.

This is deliberately scoped to stop short of `build_evidence()` wiring
and short of any probability-modeling change -- exactly matching this
directive's own guardrails ("No model wiring. No recommendation work.").
It would make the Context Assembly Proof (Section 4) fully real and
buildable end-to-end as a standalone demonstration, using data that
already exists, with zero new provider calls, zero schema changes, and
zero risk to the model or recommendation pipeline -- the honest
foundation Phase 4 reopening would eventually build on, not a
substitute for that authorization.

This document does not implement this recommendation. No code was
written or modified by this pass.
