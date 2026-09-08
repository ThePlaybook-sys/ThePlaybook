# Phase 8.3 — Player / Team Performance Data Audit (2026-09-08)

**Status: AUDIT ONLY. Zero new provider calls of any kind — every
finding below comes from re-reading already-captured real evidence
(the 2026-09-03 gap test's own raw capture files) and static code/SDK
inspection. No stats persisted. No schema applied. No external
activation. No recurring polling. No BALLDONTLIE. No SportsDataIO. No
purchases. No Probability Modeling integration. No Phase 8.1 logic
changes. No Phase 4. No Milestone 5.6. No Phase 7.2/7.3. No
staging/prod.**

---

## 1. Confirmed stats feeds

Re-read directly from the 2026-09-03 gap test's own raw capture files
(`scratchpad/bakeoff/msf_run{1,2}_parsed.json`, 22 real live calls made
that day, none repeated here) and the vendored `mysportsfeeds-node`
SDK's own feed table (`API_v2_0.js`, zero live calls needed to read it).

| Feed key (SDK) | Endpoint | Scope | Real call made? | Verdict |
|---|---|---|---|---|
| `seasonal_team_stats` | `team_stats_totals.json` | season, team | **Yes** — current season (correctly zeroed pre-kickoff) AND prior season via an identical `stats` block inside `standings.json` (fully populated, internally plausible) | **CONFIRMED REAL** |
| `seasonal_standings` | `standings.json` | season, team | **Yes** — prior season, 200, real W/L/points data | **CONFIRMED REAL** |
| `{daily,weekly,seasonal}_team_gamelogs` | `team_gamelogs.json` | per-game/week, team | **Yes**, twice — both `400`, including after adding the SDK's own documented `team` filter param | **ATTEMPTED, UNRESOLVED** — not a confirmed absence, a real unresolved parameter/plan question |
| `game_boxscore` | `boxscore.json` | per-game | **Yes** — `204 No Content` for an unplayed game | **UNKNOWN** — endpoint real, no actual payload ever observed |
| `game_playbyplay` | `playbyplay.json` | per-game | **Yes** — same `204` constraint | **UNKNOWN** — same as above |
| `seasonal_player_stats` | `player_stats_totals.json` | season, player | **No** — never called by any pass in this project | **SCHEMA/SDK ONLY** |
| `{daily,weekly,seasonal}_player_gamelogs` | `player_gamelogs.json` | per-game/week, player | **No** — never called | **SCHEMA/SDK ONLY** |
| `players` | `players.json` | league-wide, player identity | Yes (Phase 8.2, twice) | Confirmed real, but **carries zero performance/stat fields** — identity/bio only (position, team, draft, `externalMappings`) — not a stats source |
| `lineup.json` (game-scoped) | — | per-game | Yes (2026-09-03 + Phase 8.2 reuse) | Confirmed real — role/depth only, no performance numbers |

**No player-level performance feed of any kind has ever been called
against this project's real MySportsFeeds trial.** Everything real and
CONFIRMED so far is TEAM-level and SEASON-aggregate. This is the
single most important finding of this audit — per HQ's own "do not
treat SDK presence as proof of live availability," the real,
confirmed-working player-stats picture is currently **empty**, not
merely incomplete.

## 2. Player field matrix

| Field | Status | Source |
|---|---|---|
| Player identity | **CONFIRMED REAL** | `players.json` (Phase 8.2) |
| Game identity | **CONFIRMED REAL** (for the one real tracked game) | `lineup.json`'s `game.id` |
| Team | **CONFIRMED REAL** | `players.json` `currentTeam` |
| Position | **CONFIRMED REAL** | `players.json` `primaryPosition` |
| Started/played | **MISSING** | No participation-confirmation feed has ever returned real data — `lineup.json`'s "expected" lineup is pre-game projection, not confirmed participation; `boxscore.json` (the real source for this) only ever returned `204` |
| Snaps/usage (per player) | **UNKNOWN** | Never tested. A team-level `snapCounts` category exists and is real (see §3) — whether an equivalent per-player breakdown exists in `player_stats_totals`/`player_gamelogs` is unconfirmed |
| Targets/receptions/yards/TDs | **SCHEMA/SDK ONLY** | The real team-level `receiving` category (§3) strongly suggests an analogous player-level category exists in `player_stats_totals`, by MSF's own consistent schema pattern — but this is an inference from a sibling endpoint, not a confirmed player-level field. Never verified live. |
| Carries/rushing | **SCHEMA/SDK ONLY** | Same reasoning as above, via the real team-level `rushing` category |
| Passing | **SCHEMA/SDK ONLY** | Same reasoning, via the real team-level `passing` category |
| Defensive statistics | **SCHEMA/SDK ONLY** | Same reasoning, via the real team-level `tackles`/`interceptions`/`fumbles` categories |
| Other role-relevant metrics | **UNKNOWN** | Not testable without a real call |

## 3. Team field matrix

Every category below is **CONFIRMED REAL** — read directly from the
2026-09-03 capture's real `team_stats_totals`/`standings` response
(Arizona Cardinals, 2025 season, 17 games played, fully populated, not
scrambled/placeholder). **Season-aggregate scope, not per-game** (see
the schema-compatibility note in §4).

| Category | Real confirmed fields (sample) |
|---|---|
| `standings` | `wins`, `losses`, `ties`, `otWins`, `otLosses`, `winPct`, `pointsFor`, `pointsAgainst`, `pointDifferential` — a real score/result proxy, **season total, not per-game** |
| `passing` | `passAttempts`, `passCompletions`, `passPct`, `passGrossYards`, `passNetYards`, `passTD`, `passInt`, `passSacks`, `qbRating`, plus 8 more |
| `rushing` | `rushAttempts`, `rushYards`, `rushAverage`, `rushTD`, `rush1stDowns`, plus 5 more |
| `receiving` | `receptions`, `recYards`, `recTD`, `rec1stDowns`, plus 5 more |
| `tackles` | `tackleSolo`, `tackleTotal`, `tackleAst`, `sacks`, `sackYds`, `tacklesForLoss` |
| `interceptions` (defensive) | `interceptions`, `intTD`, `intYds`, `passesDefended`, `stuffs`, `safeties`, plus 4 more |
| `fumbles` | `fumbles`, `fumLost`, `fumForced`, `fumOppRec`, `fumTD`, plus 3 more |
| `kickoffReturns` / `puntReturns` | Return yardage/average/TD/long, both sides |
| `fieldGoals` | `fgMade`/`fgAtt`/`fgPct` overall and broken out by distance bucket (1-19, 20-29, 30-39, 40-49, 50+) |
| `extraPointAttempt` / `twoPointAttempts` | XP and 2-pt conversion attempts/makes |
| `punting` / `kickoffs` | Full special-teams volume/average stats |
| `miscellaneous` | `firstDownsTotal`/`Pass`/`Rush`/`Penalty`, `thirdDowns`/`thirdDownsAtt`/`Pct`, `fourthDowns...`, `penalties`, `penaltyYds`, **`offensePlays`, `offenseYds`, `offenseAvgYds`** (a real pace/volume proxy — HQ's "possession/pace/play-volume proxies" ask), `totalTD` |
| `snapCounts` | **`offenseSnaps`, `defenseSnaps`, `specialTeamSnaps`** — a real, confirmed usage/participation proxy, at the team level (season total) |

**Turnovers**: no single `turnoverMargin` field exists, but it is
directly derivable, honestly, from already-real fields: giveaways =
`fumbles.fumLost` + `interceptions.interceptions` (interceptions
thrown, tracked under the team's own defensive-stats block is actually
interceptions the team's DEFENSE recorded — **a real ambiguity worth
flagging**: this `interceptions` category's `interceptions` field
almost certainly represents defensive takeaways, not the team's own
QB's interceptions thrown, which live under `passing.passInt` instead.
Computing a real turnover margin correctly would need
`passing.passInt` + `fumbles.fumLost` (giveaways) vs.
`interceptions.interceptions` + a fumble-recovery-of-opponent figure
(takeaways) — not attempted here, flagged as a real design question for
whoever eventually builds this, not resolved by this audit.

## 4. Canonical schema compatibility

**A real, disclosed mismatch — not silently worked around.**
`player_stats`/`team_stats` both declare `game_id uuid not null
references games(id)` (confirmed via direct migration read,
`20260807211306_sports_data_tables.sql`) — every row is mandatorily
game-scoped. **The one real, confirmed MySportsFeeds stats source
(`team_stats_totals`/`standings`) is season-aggregate, not per-game.**
There is currently no way to persist a real season-total row into
`team_stats` without either (a) violating the schema by inventing a
fake `game_id`, which would misrepresent a season aggregate as a
single game's stats — never acceptable — or (b) a real, small schema
change.

**Smallest proposed change (not applied, per guardrail):** make
`game_id` nullable on both `player_stats` and `team_stats`, add a
nullable `season_id uuid references seasons(id)` column (reusing the
already-existing, already provider-neutral `seasons` table — no new
concept invented), and a check constraint requiring at least one of
`game_id`/`season_id` to be set on every row. This is the same
"smallest change, reuse an existing canonical concept" pattern every
prior Phase 8.2 schema decision in this arc has followed (e.g., the
`mysportsfeeds` provider-identity widening) — not a redesign, not
NFL-specific (`seasons` is already sport-agnostic).

`player_stats_nfl`'s existing 5 typed columns
(`passing_yards`/`receiving_yards`/`rushing_yards`/`interceptions`/
`sacks`) are narrower than the real confirmed team-level category
structure — not a blocking gap, since the parent `player_stats.stats
jsonb` is already flexible/lossless and can carry everything the typed
extension doesn't; widening the typed extension later is optional, not
required to activate real data. **No `team_stats_nfl` extension table
exists at all** — not needed either, for the same reason.

## 5. Historical depth available

**Asymmetric, real, and only partially tested.** Season-aggregate data
(`team_stats_totals`/`standings`) reaches back at least **one full
prior season** (2025) with real, fully-populated numbers — confirmed
live. **Game-level browsing of that same prior season is blocked**:
both `week/N/games.json` and the whole-season `games.json` returned
`403` for 2025 on this plan, while `standings.json` for the identical
season succeeded — a real, reproducible plan boundary, not a bug.
**Nothing beyond one prior season (2024, 2023, ...) has ever been
tested** — genuinely unknown whether the season-aggregate access
extends further back; would require a new, real call to determine
(not made here, per guardrail).

**Practical implication for comparable-sample viability:** if Phase 8.3
ever needs game-by-game historical samples (the shape most contextual
comparisons actually need — "how did this team perform in comparable
games"), the current real evidence suggests **that specific access is
blocked on this plan** for at least the one tested prior season. Season
totals alone support only season-level, not game-level, comparability.

## 6. Phase 8 dimensions unlocked by stats

None are unlocked to "supported" by this audit alone (no data was
persisted this pass, per guardrail) — this section states what
*would* become possible once the smallest schema change (§4) and a
real activation pass land, not what exists today.

| Comparison | Possible once team season-stats are activated? |
|---|---|
| Team performance × opponent (season-level) | **Yes** — real `standings`/`passing`/`rushing`/etc. season totals per team support season-level team-vs-team comparison |
| Team performance × pace/volume | **Yes** — `offensePlays`/`offenseYds`/`snapCounts` give a real proxy |
| Player performance × anything | **No** — zero player-level performance data has ever been confirmed real (§1/§2); this axis stays fully insufficient-evidence regardless of the schema fix |
| Player performance × weather / lineup-role / teammates / opponent / venue / market / recency | **Still fully impossible** — every one of these needs real player-level performance numbers as the base fact being explained; none exist |
| Team performance × weather / venue / market (season-level only) | **Partially possible** — the season-total shape can't be matched to a single game's weather/venue/market conditions, only to a team's overall season profile, which weakens the contextual claim considerably |

**What remains impossible without injuries/PBP/game-state/additional
participation data, stated plainly:** per-game team performance (blocked
by the `team_gamelogs` 400s and the `boxscore`/`playbyplay` `204`s),
any real player-level performance number at all, and therefore the full
"player × weather × lineup-role × teammates × opponent × venue ×
market × recency" comparison HQ described as the ultimate goal — none
of its terms have real player-level data behind them yet.

## 7. Remaining evidence gaps

1. **Player-level stats feeds (`player_stats_totals`,
   `player_gamelogs`) have never been called.** The single highest-value
   next diagnostic, per HQ's own stated end goal.
2. `team_gamelogs` (per-game team stats) is real-but-broken on this
   plan (`400` twice) — the actual required parameter shape is
   unresolved, not confirmed absent.
3. `boxscore`/`playbyplay` real payload shape is still unobserved (only
   `204`s, always against an unplayed game). The tracked NE @ SEA game
   (163541) kicks off 2026-09-10 -- two days from today (2026-09-08).
   Once that game has actually been played, a fresh, legitimate re-test
   of `boxscore`/`playbyplay` against it becomes possible, which wasn't
   true at the time of the original 2026-09-03 capture.
4. Historical depth beyond one prior season is completely untested.
5. The real turnover-margin ambiguity in §3 (giveaways vs. takeaways
   field mapping) is unresolved.

## 8. Smallest execution-safety fix

**Smallest durable once-only mechanism, proposed only, not built (per
guardrail):** a single new table, e.g. `activation_run_markers(id,
run_key text unique, completed_at timestamptz default now())`. Any
future one-shot activation hook first attempts an `INSERT ... ON
CONFLICT (run_key) DO NOTHING RETURNING id` with a hardcoded, pass-specific
`run_key` (e.g. `"phase-8.3-team-stats-activation-2026-XX-XX"`); if the
insert returns no row (conflict), the hook logs a skip and returns
immediately without doing any real work. This directly closes the exact
race both prior Phase 8.2 activation passes hit: two overlapping
containers both reading `RUN_X=1` at boot can no longer both proceed,
because only the first one to reach the atomic insert wins — the second
observes the conflict and no-ops, deterministically, without depending
on how fast a human polls Railway's deployment API. Smallest possible
shape: one table, one unique column, one guarded insert per hook — not
a job queue, not a general scheduler, not built this pass.

## 9. Duplicate-snapshot analytical treatment

**The 4 existing `depth_chart_snapshots` rows stay exactly as they
are — nothing deleted, nothing rewritten.** Per HQ's own framing, the
duplicate pair (2 rows per team, byte-identical content, ~30 seconds
apart) should be classified as **duplicate-execution provenance**, not
two independent real observations 30 seconds apart — the underlying
real-world lineup evidence did not change between the two writes; only
the accidental double-fire produced two rows for what is, analytically,
one logical observation.

**Recommended read-side treatment for any future analytical
consumer:** when reading `depth_chart_snapshots` for a team, de-duplicate
by `(team_id, depth_chart_data)` content-equality within a short time
window (e.g., rows for the same team whose entire `depth_chart_data`
value is identical and whose `captured_at` values fall within a few
minutes of each other) and treat them as one logical snapshot, keeping
only the earliest `captured_at` as that observation's real timestamp.
This is a read-query convention to document and apply at query time,
not a schema change or a data mutation — the append-only table itself
stays untouched, matching this table's own "never mutate, never delete"
design philosophy.

## 10. Recommended Phase 8.3 implementation pass

In order, smallest-first, each gated on the previous:

1. **Apply the smallest schema change from §4** (nullable `game_id`,
   new nullable `season_id` on `player_stats`/`team_stats`) — a real,
   small, disclosed migration, not a redesign.
2. **Build the season-aggregate team-stats persistence path** reusing
   the exact same read-only identity-resolution pattern this whole
   Phase 8.2 arc already established (`team_identity.resolve_team_ids`,
   no new player/roster writes) — activate using the exact real,
   already-captured `team_stats_totals`/`standings` payload for the
   teams already tracked (Cardinals from the existing capture, plus
   NE/SEA if a fresh minimal call is authorized), applying the §8
   once-only marker from the very first activation to avoid repeating
   this pass's own disclosed duplicate-row incident.
3. **Only then, one narrow, authorized diagnostic call** against
   `seasonal_player_stats` (`player_stats_totals.json`) for a small,
   already-identity-resolved player set (e.g., the same 34 NE/SEA
   players) — the single highest-value unresolved question this audit
   surfaced, and the one genuinely new live call this whole plan would
   need.
4. Player-level activation, `team_gamelogs`/`boxscore`/`playbyplay`
   re-testing (now that the 2026 season has begun), and any Phase 8.1
   dimension-logic work all stay explicitly out of scope for the very
   next pass — each is its own follow-on, not bundled in.

---

**Guardrails held throughout:** audit only; zero provider calls of any
kind (every finding traces to the 2026-09-03 capture's own raw JSON
files or static SDK/schema reads); no stats persisted; no schema
applied; no external activation; no recurring polling; no BALLDONTLIE;
no SportsDataIO; no purchases; no Probability Modeling integration; no
Phase 8.1 logic changes; no Phase 4/Milestone 5.6/Phase 7.2-7.3; no
staging/prod; no invented fields or capabilities anywhere in this
report — every "CONFIRMED REAL" claim traces to a specific real
captured value, and every inference is explicitly labeled as such.
