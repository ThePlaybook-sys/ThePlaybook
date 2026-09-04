# 2026 Data Preservation Requirement

**UPDATE 2 (2026-09-04, same day): the minimum pre-9/9 implementation is
DONE, in DEV.** `game_events` and `news_article_history` (Volume 3
§4.3/§4.4) are live tables, both migrations applied and verified
(append-only triggers live-proven by real rejected `UPDATE`s;
`news_article_history`'s dedup live-proven by a real rollback-wrapped
insert-twice test). Weather Worker and Injury Worker both now continue
through a bounded 4-hour post-kickoff window instead of stopping solely
at kickoff (Volume 2 §8 v5.4). News Worker now writes first-sighting
history alongside its existing current-state write. **Still NOT done,
by design:** any `game_events` normalization, any real MySportsFeeds
adapter wiring, any in-game Odds/Player Props capture (a separate HQ
decision), and any live invocation against a real game — all deferred
to after the 2026-09-09/10 live-game validation. Full implementation
report: `docs/ops/2026-data-preservation-readiness-plan-2026-09-04.md`
(§9's sequence, steps 1-4 now complete). 654/654 sports-intel-layer
tests passing. DEV only; staging/production untouched.

**UPDATE 1 (2026-09-04, same day): a full readiness plan answering "what
do we do about this" is now available at
`docs/ops/2026-data-preservation-readiness-plan-2026-09-04.md`** —
proposed provider-neutral schema (Volume 3 §4.3 Game Events/PBP, §4.4
News History), a cost-conscious in-game capture strategy per category,
and a recommended pre-9/9 implementation sequence. This document
remains the original audit/risk-identification pass; the readiness plan
was the follow-on design work built on top of it, since implemented per
Update 2 above.

**STATUS: URGENT, TIME-SENSITIVE.** The 2026 NFL regular season opens
2026-09-09 (Seahawks host Patriots, kickoff 2026-09-10T00:20:00Z, per
schedule data already pulled in the NFL provider bake-offs). **This
document was written 2026-09-04 — five days before kickoff.** Every gap
named below becomes permanent and unrecoverable, one game at a time,
starting the moment the season's first game is played, if it isn't
addressed first. This is an audit and a requirement, not an
implementation — no code, migration, or worker has been changed to
produce or act on this document.

**Origin:** recorded as part of the same 2026-09-04 HQ directive that
added Phase 8 (Contextual Performance Intelligence) to
`docs/blueprint/engineering-roadmap-build-order.md` (Volume 4 §8.6).
Phase 8's own purpose — learning how comparable historical/current
context changes expected performance — needs comparable historical
data to exist. **Capture first; Phase 8 may process/reprocess later.**
A context factor never captured cannot be reconstructed after the fact,
no matter how good Phase 8's eventual analysis is.

---

## Method

Direct inspection of the current schema (`docs/blueprint/volume-3-database-architecture.md`)
and the current specialized-worker cadence table (`docs/blueprint/volume-2-system-architecture.md`
§8) — not assumed, not inferred from the Blueprint's original design intent alone, since prior
audits in this project (Phase 7 Milestone 7.0, the NFL provider bake-offs) have repeatedly found
real gaps between what was originally specified and what actually exists or actually runs.

## Findings — what is being preserved today

Real, confirmed, append-only, timestamped history exists for:

| Category | Table | Keyed by | Notes |
|---|---|---|---|
| Odds | `odds_snapshots` | `game_id` + `captured_at` | Append-only, every poll a new row |
| Injuries | `injury_reports` | `game_id` + `captured_at` | Same pattern |
| Weather | `weather_snapshots` | `game_id` + `captured_at` | Same pattern — **pregame only, see gap below** |
| Referee assignments | `referee_assignments` | `game_id` + `captured_at` | Same pattern |
| Lineup / depth chart | `depth_chart_snapshots` | `team_id` + `captured_at` | Team-scoped, not game-scoped; every poll a new row |
| Roster / team membership | `roster_memberships` | `player_id` + `observed_at` | Insert-on-change, historical team assignment |
| Final team/player stats | `team_stats` / `player_stats` | `game_id` + `created_at` | DB-hardened append-only (Phase 3F-3) — but **one row per finalization, not a running history**, see gap below |
| Venue | `games.venue_lat`/`venue_long`/`venue_type` | `games.id` | Static per game, not time-varying |

This is a real, existing strength: several of Phase 8's named context
factors (injuries/availability, lineup/depth-chart changes, teammate
dependency, roster history, pregame weather, venue, home/away) already
have exactly the kind of stable, timestamped record a future contextual
analysis would need. None of this needs to be rebuilt.

## Findings — what is NOT being preserved, and will be lost

### 1. In-game condition changes — nothing captured, for any category

**Odds, Player Props, Injury, and Weather Workers all stop polling a
game at its own kickoff** (`app.workers.windows`'s `Window.STOPPED`
classification, confirmed in Volume 2 §8 for all four workers
independently). Concretely, once a 2026 game kicks off:
- No further odds/line-movement data is captured for that game, ever
  (no in-play/live odds history at all).
- No in-game injury (a player leaving the game, a designation changing
  mid-game) is captured — `injury_reports`' last row for that game is
  whatever existed before kickoff.
- No in-game weather change (a storm arriving in the third quarter, a
  dome roof status change) is captured — `weather_snapshots`' last row
  is the pregame forecast/observation.

**This is the single largest, most time-sensitive gap.** Phase 8's own
purpose statement explicitly names "weather, including changing
in-game conditions where data permits" as a context factor — today,
"where data permits" resolves to "never," for every one of these
categories, for every game played before this changes.

### 2. No play-by-play or game-event data exists anywhere

Confirmed by direct schema search: no table in this project's schema
records plays, drives, scoring timeline, down/distance, formation,
personnel, or any other sub-game-level event. `team_stats`/`player_stats`
are single, final, post-game snapshots (Postgame Ingestion Worker) —
there is no record of *how* a final stat line was produced over the
course of the game. **"Game state/script" (an explicitly named Phase 8
context factor — e.g. "this back's usage collapsed once the team was
down two scores") cannot be reconstructed at any depth, for any game,
past or future, unless this changes.** This is also the same open
question the 2026-09-03 NFL provider bake-offs left unresolved across
every evaluated provider (BALLDONTLIE has none; API-SPORTS has a
coarser `/games/events` scoring-plays feed; MySportsFeeds' PBP endpoint
returned a clean `204` against an unplayed game, still unvalidated
against a real one).

### 3. News has no history at all

Re-confirmed (same finding as Phase 7 Milestone 7.0's own audit,
unchanged since): `daily_game_intelligence.news` is a single overwritten
jsonb column. Once News Worker's next 15-minute cycle overwrites it, the
prior state — including the exact moment a trade, suspension, inactive
designation, or lineup-change story first appeared — is gone. HQ's own
"news is an input to contextual intelligence" instruction (2026-09-04)
depends on being able to say *when* a piece of news became true; today's
architecture cannot answer that question even one cycle later.

### 4. Playing surface is not captured

`games.venue_type` distinguishes `outdoor`/`dome`/`retractable_dome`
only — no column anywhere records surface type (turf vs. grass), a
real, commonly-cited performance-context factor with no schema home
today.

### 5. Final stats' real granularity is unaudited

`team_stats`/`player_stats.stats` jsonb "preserves the complete provider
stat payload" per Volume 3's own v4.12.1 note, but *how complete* that
payload actually is for role/usage-level detail (snap counts, target
share, red-zone touches) depends on which fields the current SportsDataIO
normalization code actually carries through — not independently
re-verified as part of this pass. Flagged as an open question, not a
confirmed gap, since jsonb's flexibility means the data could already be
there; it hasn't been checked field-by-field against a live payload.

---

## Recommended immediate captures (where licensing/provider access permits)

**Not authorized for implementation by this document** — these are the
specific, minimal captures HQ would need to authorize to close the
time-sensitive gaps above before 2026-09-09:

1. **Extend Odds/Injury/Weather Worker polling past kickoff for the
   duration of the game**, at whatever reduced in-game cadence is
   judged sufficient (this document does not propose a number — that is
   implementation work, not an audit finding). Even a coarse in-game
   snapshot (e.g. once per quarter) is strictly better than the current
   zero.
2. **Add a News event history** — even an append-only log of raw News
   Worker responses, before any Phase 8-specific structuring, would
   preserve the timestamp/content information that is otherwise lost on
   the very next overwrite. This is the same gap Phase 7 Milestone 7.0
   already flagged as blocking News from ever being cited as market-
   movement evidence; closing it serves both purposes at once.
3. **Investigate whether any evaluated provider (BALLDONTLIE,
   MySportsFeeds, API-SPORTS, SportsDataIO) can supply real
   play-by-play/game-event data before the season starts** — this is
   the one gap that cannot be closed by MANSA's own capture code alone;
   it depends on the still-open provider question from the NFL
   provider bake-offs and the MySportsFeeds live-game validation gate
   (`docs/ops/nfl-provider-decision-record.md`), which itself cannot
   resolve until a real 2026 game is played. **This creates a real
   tension**: the live-game validation gate needs a played game to test
   against, but by the time it's tested, that specific game's PBP (if
   the answer turns out to be "no provider has it usably") is already
   unrecoverable. Recommend testing PBP availability on the very first
   2026-09-09/10 game specifically, not deferring the check.
4. **Add a `surface` column to `games`** (or extend `venue_type`'s
   vocabulary) — a small, low-risk additive schema change, mirroring
   the precedent already set for `venue_lat`/`venue_long`/`venue_type`
   themselves (Option A, smallest additive change).
5. **Audit `player_stats.stats`'s real field completeness** against a
   live SportsDataIO payload for role/usage-relevant fields, before
   assuming Phase 8 can compute usage-based context from data that may
   not actually be captured today.

None of these are scheduled or authorized by this document. They are
named here so the decision isn't lost between now and 2026-09-09 the
way several other real gaps in this project have been named and tracked
before being acted on (the same discipline `PROGRESS.md`'s own
procurement-checkpoint entries and the provider decision records already
follow).

---

## What this document does NOT do

- Does not implement any capture change.
- Does not modify any worker, cadence, or schema.
- Does not authorize Phase 8 Milestone 8.1+ work.
- Does not resolve the play-by-play provider question — that remains
  gated on the still-open MySportsFeeds live-game validation
  (`docs/ops/nfl-provider-decision-record.md`).

## Decisions HQ needs to make, and by when

1. **Before 2026-09-09**: whether to extend any worker's polling past
   kickoff for the 2026 season, and at what cadence — every day this is
   undecided is a day closer to the first unrecoverable game.
2. **Before 2026-09-09**: whether to add a minimal News history capture
   ahead of any Phase 8-specific design work.
3. **At or immediately after the first 2026-09-09/10 game**: whether to
   use that specific game as the PBP-availability test case referenced
   in item 3 above, given the live-game validation gate's own timing.
4. **Not time-sensitive, but should not be dropped**: the `surface`
   column addition and the `player_stats.stats` completeness audit.
