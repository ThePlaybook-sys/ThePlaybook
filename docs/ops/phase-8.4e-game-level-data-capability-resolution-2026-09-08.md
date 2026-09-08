# Phase 8.4E — Game-Level Data Capability Resolution (2026-09-08)

MANSA HQ directive: "MANSA PHASE 8.4E — GAME-LEVEL DATA CAPABILITY
RESOLUTION." Phase 8.4D accepted and closed; `_gamelogs` not to be
probed again. **Zero provider calls this pass.** Pure audit: existing
account/subscription evidence, vendored SDK/docs, captured responses,
repo code, and current Supabase table state (reading MANSA's own
database is not a provider call).

## 1. MSF entitlement verdict

**Split verdict — do not treat MySportsFeeds as one monolithic
capability.**

- **General NFL CORE+STATS+DETAILS entitlement: STRONGLY SUPPORTED.**
  The account is confirmed on "NFL, Commercial Near-Realtime, CORE +
  STATS + DETAILS" (14-day trial, per the original 2026-09-03 bake-off
  report's own stated subscription line) and has real, live `200`
  responses across a wide spread of feeds since then: `team_stats_totals`
  (Phase 8.3A), `player_stats_totals` (Phase 8.3C), `standings`,
  `injuries`, `latest_updates` (2026-09-03), and — critically for this
  audit — `games/{id}/lineup.json` (2026-09-03, real data for a game
  7 days out) and `players.json` (Phase 8.2, 34/34 lineup-ID
  cross-match). This is not a trial that only serves toy/sandbox data;
  it serves real DETAILS-tier per-game data today.
- **`_gamelogs`-family entitlement (`seasonal_player_gamelogs`,
  `seasonal_team_gamelogs`): CONFIRMED NOT WORKING**, per Phase 8.4D's
  own closed finding — 4/4 independent real requests failed with a
  fast (`~0.2–0.35s`), zero-byte `400` across two endpoints and three
  parameter shapes (none, slug, numeric id). Per HQ's own instruction,
  this is closed and not re-litigated here.
- **New structural finding this pass, from the vendored
  `mysportsfeeds-node` SDK's own feed table
  (`API_v2_0.js`)**: `game_boxscore`, `game_playbyplay`, and
  `game_lineup` are a **structurally different request shape** than
  `_gamelogs` — each requires a mandatory `path` segment
  (`games/{gameId}/`), i.e. `GET /nfl/{season}/games/{id}/boxscore.json`,
  not a bare season-level feed. `game_lineup` using this exact shape
  already returned a real `200`. `game_boxscore`/`game_playbyplay`
  using this exact shape already returned a clean `204 No Content` (not
  `400`, not `403`) for a real, valid, not-yet-played game
  (2026-09-03) — meaning the *request itself* was accepted as
  well-formed and entitled; there was simply no content yet because the
  game hadn't been played. **This is the single most important finding
  of this audit**: the per-game, path-scoped MSF endpoints have a
  materially better-evidenced entitlement/contract status than the
  bare `_gamelogs` feeds ever did, and were never implicated in
  Phase 8.4B/C/D's own failure pattern.

## 2. Alternate MSF capabilities (not called this pass)

| Feed | Shape | Evidence | Fit for player→game→stats |
|---|---|---|---|
| `game_boxscore` | `GET /nfl/{season}/games/{id}/boxscore.json` | Real `204` for an unplayed game (2026-09-03) — request accepted, no payload observed yet | **Best-evidenced candidate.** Never tested against a played game. |
| `game_playbyplay` | `GET /nfl/{season}/games/{id}/playbyplay.json` | Same `204` result, same caveat | Finer-grained (per-play) than needed for a stat line; heavier to parse; same untested-on-real-game status |
| `game_lineup` | `GET /nfl/{season}/games/{id}/lineup.json` | Real `200`, real data, twice cross-verified (2026-09-03 call, Phase 8.2's 34/34 ID match) | Pre-game *expected* participation/depth, not a final stat line — useful as a participation/usage signal, not a substitute for actual performance |
| `seasonal_player_stats` (`player_stats_totals`) | Season aggregate, no path | Real `200`, 43 real players (Phase 8.3C) | **Wrong granularity** — season totals only, cannot answer "how did he do in THIS game" |
| `seasonal_player_gamelogs` / `_team_gamelogs` (+ daily/weekly variants) | Bare season feed, no path | **CONFIRMED 400, closed per HQ** | Ruled out — not to be probed again |

**A real, disclosed constraint on all path-scoped feeds**: `games.json`
and `week/N/games.json` for a **prior** season both returned `403` on
this plan (2026-09-03), while `standings.json` for that same prior
season succeeded. This means MSF's own game-listing feed cannot
discover **historical (past-season)** game IDs on this plan — the one
real game ID this project has ever exercised against `game_lineup`
(163541, NE @ SEA) came from the **current** 2026-2027 season's
schedule, not a completed past game. Practical effect: even if
`game_boxscore`/`game_playbyplay` prove out, MSF alone cannot supply
**backtesting-depth historical** per-game data — only current-season
games going forward, and only once each has actually been played
(season kicked off 2026-09-09).

## 3. Alternate-provider capabilities (BALLDONTLIE; no calls made)

**`/nfl/v1/stats` (per-game) and `/nfl/v1/season_stats` (season
totals)** — both confirmed **live** in the original 2026-09-03
bake-off: `/nfl/v1/stats` is explicitly per-game, ~50 typed fields,
correct nulls for non-applicable positions. This is, structurally, the
**closest direct match** to what HQ is asking for — a real, already-
evidenced per-game player stat line, from an already-authorized
provider, with no new architecture needed to discover it (unlike MSF's
`_gamelogs`, this was never shown to fail).

**However — a real, currently-open blocker directly affects this
finding's usability today, and must not be glossed over**: the
account's **Sep 5 invoice is open/unpaid**, so paid GOAT-tier
entitlement is **not currently confirmed active** (established across
Phase 8.0.5's closeout and Phase 8.2's roster audit). Every BALLDONTLIE
endpoint tested **since** that billing issue was discovered has come
back blocked: `player_injuries` (ALL-STAR/GOAT-tier) → real `401`;
`/players`/`/players/active` (GOAT-tier) → classified
UNCONFIRMED/likely-blocked, same root cause. `/nfl/v1/stats` itself has
**not been re-tested since the billing issue emerged** — its
2026-09-03 GREEN result predates the Sep 5 invoice going unpaid, so its
**current** live status is honestly **UNKNOWN-pending-billing**, not a
confirmed-still-working GREEN. `/nfl/v1/games` (schedule) remains
confirmed working today because it is Free-tier — this is a real,
useful signal: the block is specifically paid-tier-scoped, not
account-wide.

**API-SPORTS**: has team-level per-game stats (`/games/statistics/teams`),
not player-level, and is plan-gated to the 2022–2024 window on the
current key — doesn't reach any season MANSA actually needs. Not a
candidate for this specific gap.

**SportsDataIO**: the reserved trial call remains unspent, out of
scope per this pass's own guardrail (no purchases, no spend
authorized here).

## 4. Context join readiness

Real current Supabase state (read this pass, not recalled from memory):
`players` 40, `player_provider_ids` 34 (all `mysportsfeeds`, including
Hunter Henry's real id `9999`), `roster_memberships` 34,
`depth_chart_snapshots` 4, `player_stats` 2 (both **fixture-pattern
IDs**, game-scoped, not real — confirmed by inspecting the rows
directly), `team_stats` 14, `games` 12, `venues` 5, `weather_snapshots`
4, `odds_snapshots` 272, `news_article_history` 121, `injury_reports`
1 (fixture-only).

| Dimension | Status | Exact reason |
|---|---|---|
| Canonical player identity | **READY** | 40 real players, 34 real `mysportsfeeds` provider IDs incl. Hunter Henry (9999), cross-verified 34/34 against `lineup.json` (Phase 8.2) |
| Canonical game (current season, going forward) | **PARTIAL** | `games`/`game_provider_ids` real but small (12/17 rows); current-season discovery works (BALLDONTLIE `games` free-tier, MSF current-season schedule) |
| Canonical game (historical/past seasons) | **BLOCKED** | MSF prior-season game-listing returns `403` on this plan; no alternate historical game-ID source has been exercised yet |
| Opponent / home-away | **READY** (wherever a game row exists) | Derivable directly from `games`' own team columns |
| Venue | **PARTIAL** | 5 real venues captured; not yet at league-wide coverage |
| Weather | **PARTIAL** | 4 real rows only (WeatherAPI + the `lineup.json` bonus forecast finding); no real historical-game weather at scale |
| Lineup / depth role | **PARTIAL** | 4 real rows, from a single MSF `lineup.json` call; BALLDONTLIE has **no depth/rank field at all** (confirmed absent from its own SDK) |
| Injuries / teammate availability | **BLOCKED** | `injury_reports` is 1 fixture row; BALLDONTLIE's adapter is complete but blocked (Sep 5 invoice); MSF `injuries.json` worked once but was never activated as a recurring real pipeline |
| News | **READY** (for its own coverage window) | 121 real GNews rows already flowing (Phase 8.0.5 Pass 2) |
| Odds / market context | **READY** | 272 real odds rows, live Phase 7 odds worker |
| **Player performance (the actual per-game stat line)** | **BLOCKED — the central gap this entire Phase 8.4 arc exists to close** | `player_stats` holds only 2 fixture-pattern rows; zero real per-game stat lines exist for any player, Hunter Henry included |

## 5–6. Hunter Henry minimum-data model

To eventually answer *"how has Hunter Henry performed historically
under conditions similar to this upcoming game?"*, MANSA needs, per
historical game (not calculated this pass — inventory only):

- **Performance**: targets, receptions, yards, TDs, and (if available)
  air yards/YAC-style detail — **BLOCKED**, no real source yet.
- **Usage**: snap count/percentage (offense), route participation if
  obtainable — **BLOCKED** for game-level (season-level snap counts
  were real in Phase 8.3C, but not per-game).
- **Opponent** — READY once a real game row exists.
- **Venue** — PARTIAL (5 real venues so far).
- **Weather** — PARTIAL (4 real rows, forecast-only so far, not
  historical actuals for played games).
- **Lineup/depth role that game** — PARTIAL (1 real snapshot type
  proven, `lineup.json`, pre-game expected only).
- **Teammates/QB availability** — BLOCKED (injuries blocked; roster
  membership alone doesn't capture per-game availability).
- **Recency** (weeks since, rest days) — derivable once real game
  dates exist; not blocked structurally, just has no real data yet.
- **Sample size** — cannot be assessed until real per-game rows exist
  for Hunter Henry specifically.
- **Similarity definition** — explicitly NOT designed this pass, per
  HQ's own instruction ("do not calculate contextual intelligence
  yet").
- **Uncertainty / confounders** — every dimension above is either
  PARTIAL or BLOCKED except identity, opponent-once-a-game-exists,
  odds, and news; any contextual claim built today would be
  substantially unsupported.

**Bottom line: nothing in sections 5–6 is buildable yet.** The gating
dependency for all of it is the same one row in section 4:
game-level player performance.

## 7. Blockers

1. **BALLDONTLIE's Sep 5 invoice is open/unpaid** — blocks
   `/nfl/v1/stats` (unconfirmed-but-likely, per the same-tier pattern
   as rosters/injuries), `/players`/`/players/active`, `player_injuries`,
   and presumably `advanced_stats`. This is a billing action for Mac,
   not resolvable from any session.
2. **MSF `_gamelogs` family is closed/unusable** (Phase 8.4D, not
   reopened here).
3. **MSF cannot list historical (past-season) games on this plan**
   (`403`) — blocks discovering historical game IDs for
   `game_boxscore`/`game_playbyplay`/`game_lineup` beyond the current
   season.
4. **No NFL game has been played yet as of this pass** (season kicked
   off 2026-09-09, one day after this audit) — `game_boxscore`/
   `game_playbyplay` have literally never been tested against real
   played-game content; only the clean-`204`-for-unplayed-game result
   exists.
5. **No `DataCategory`/canonical model exists today** for box-score or
   play-by-play-level granularity — `TeamStatLine`/`PlayerStatLine`
   don't fit that shape; this is a real architecture decision, not
   solved by this audit.
6. **MSF's trial is time-boxed**, ~through 2026-09-17 (Phase 8.2's own
   finding) — a real clock on when any further MSF diagnostic remains
   free to run.

## 8. Exact recommended next pass

**Recommended primary path: D — Hybrid provider strategy.** Neither
already-authorized source alone closes this gap cheaply and reliably
today; each has a real, different blocker, and each unblocks a
different, larger set of capabilities than "game-level stats" alone:

1. **First, and cheapest: resolve the BALLDONTLIE Sep 5 invoice.**
   This is not a new purchase — it's paying down a bill already
   incurred against an already-provisioned GOAT-tier subscription.
   Paying it would very plausibly unblock `/nfl/v1/stats`,
   `/players`/`/players/active`, **and** `player_injuries`
   simultaneously — three real gaps (player performance, roster/
   identity redundancy, injuries) closed by one billing action, not
   three separate technical passes. This is Mac's action, outside any
   session's ability to perform.
2. **Once resolved: one authorized diagnostic call** confirming
   `/nfl/v1/stats` still returns real per-game data post-payment
   (its GREEN result predates the billing gap and needs
   re-confirmation, not blind trust).
3. **In parallel, after 2026-09-10** (once a real 2026 game has
   actually been played): **one authorized diagnostic call to MSF
   `game_boxscore`** for the one already-known real game ID (163541,
   NE @ SEA, or whichever real game has by then completed) — the
   evidence-supported alternate MSF path this audit identified, which
   HQ's guardrail did **not** rule out (only `_gamelogs` was ruled
   out). This tests the single highest-confidence remaining MSF
   avenue while the trial window is still open.
4. **Only after real payload evidence exists from whichever path (or
   both) succeeds**, design the `DataCategory`/canonical-model
   extension needed to actually persist per-game player
   participation/box-score data — a real architecture decision for
   Mac, not something to force into `PlayerStatLine.stats` blindly.

No code, schema, or persistence work is proposed to start yet — every
one of the four steps above is either a billing action or a single
future authorized diagnostic call, exactly matching this pass's own
zero-provider-call, zero-implementation guardrails.

## What was and wasn't done this pass

Zero provider calls (MySportsFeeds, BALLDONTLIE, SportsDataIO, or any
other vendor). Zero purchases. Zero schema changes. Zero ingestion
implementation. No Phase 8.1 engine changes. No Phase 4/5.6 changes.
Staging/production untouched. Phase 7 observation undisturbed. The
only actions taken were reading already-committed repo files/reports,
the vendored MySportsFeeds SDK tarball already cached in this
session's scratchpad from a prior pass, and read-only `SELECT` queries
against MANSA's own DEV Supabase database (not a provider call).
