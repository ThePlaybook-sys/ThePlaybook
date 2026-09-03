# MANSA NFL Provider Gap Test — MySportsFeeds (2026-09-03)

**Status: diagnostic only. No provider migration was made or proposed as
code. No subscription was purchased or changed by this session. SportsDataIO
remains the production provider unchanged.**

## Objective

Determine whether MySportsFeeds (subscription under evaluation: NFL,
Commercial Near-Realtime, CORE + STATS + DETAILS, 14-day trial) can fill
the gaps found in the earlier BALLDONTLIE/API-SPORTS bake-off
(`docs/ops/nfl-provider-bakeoff-2026-09-03.md`): current-season team
statistics, play-by-play, box scores, and lineups.

## Method

- Re-read the prior bake-off report and the existing provider-neutral
  architecture (`app/adapters/base.py`, `models.py`) before making any
  call. Confirmed the current `DataCategory` enum has **no category at
  all** for play-by-play, lineups, or box-score-level detail — only
  `TEAM_STATS`/`PLAYER_STATS` (aggregate-shaped) exist today. This is an
  architecture finding, not something this diagnostic pass changed.
- **A credential gap was found and corrected before any live call was
  made:** `sports-intel-layer`/dev had no `MYSPORTSFEEDS_API_KEY` (or any
  similarly-named variable) at the start of this task, despite the task
  description stating MySportsFeeds was already configured. Flagged to
  Mac directly rather than guessing a variable name or proceeding on an
  unverified assumption; Mac set `MYSPORTSFEEDS_API_KEY` while the
  non-live parts of this test (architecture review, endpoint research)
  continued in parallel. Confirmed present before any call was made.
- This workspace's own egress policy blocks direct HTTPS to
  `mysportsfeeds.com`/`api.mysportsfeeds.com` (confirmed the same way as
  every vendor domain in the prior bake-off). Endpoint paths, the auth
  scheme, and the season-string convention were instead confirmed from
  the **official `mysportsfeeds-node` npm package** (published and
  maintained by MySportsFeeds' own team) — `lib/API_v2_1.js`/
  `API_v2_0.js`/`API_v1_0.js` — not guessed.
- Built a temporary, dev-only diagnostic module
  (`app.diagnostics.msf_bakeoff`, gated behind `RUN_MSF_BAKEOFF=1`, never
  wired into any permanent route), same "startup hook + `logger.warning`
  retrieval" shape as the prior bake-off's own probe (this service's own
  public Railway domain is also unreachable from this session, so no
  inbound HTTP call could exercise a normal endpoint either). **Reverted
  immediately after this report was produced** — none of it exists in
  the codebase now. `RUN_MSF_BAKEOFF` was set back to `0`.
- **Two runs, 22 total live calls.** Run 1 (12 calls) surfaced two real
  issues: `week/1/games.json` for a **prior** season returned 403 even
  though `standings.json` for that same season succeeded (no game ID
  could be resolved, so box score/PBP/lineup were never meaningfully
  exercised), and `team_gamelogs.json` needed a `team` filter param the
  bundled feed-definition table doesn't list as required. Run 2 (10
  calls) added a whole-season schedule fallback (also 403 — confirming a
  genuine plan restriction on prior-season game listings, not a URL bug)
  and, when that also failed, fell back to the **current season's own
  already-known, not-yet-played game** for box score/PBP/lineup — a
  real and reportable result even though the game hasn't happened yet.
- No writes were made to any table; no recommendation/business logic was
  touched; `cron-odds-worker` stayed frozen (`SKIPPED` on every push,
  confirmed via Railway deployment status) throughout; staging and
  production were never touched; SportsDataIO's reserved trial call was
  never spent (this test made zero SportsDataIO calls).

## Findings by objective

### 1. Current-season NFL team statistics — **GREEN**

`/nfl/{season}/team_stats_totals.json` for the current 2026-2027 season
responded `200` with a fully-structured, deeply-typed schema —
`passing`/`rushing`/`receiving`/`tackles`/`interceptions`/`fumbles`/
`kickoffReturns`/`puntReturns`/`fieldGoals`, each with named numeric
fields (not a name/value list like API-SPORTS's `players/statistics`).
Every value was correctly `0` (season hasn't started — **correct
behavior, not a bug**: the endpoint exists and responds validly for the
current season today, rather than erroring the way API-SPORTS's
season-gated plan did for 2025/2026, or the way BALLDONTLIE has no
team-stats endpoint at all). Confirmed the same schema is genuinely
populated with real numbers on a completed season: the `standings.json`
call for the prior (2025) season returned the identical `stats` block
fully populated (e.g., Cardinals: 649 pass attempts, 4,363 gross passing
yards, 92.8 QB rating, 17 games played) — internally plausible, not
SportsDataIO-trial-style scrambled. **This directly closes the gap
neither BALLDONTLIE nor a season-appropriate API-SPORTS call could close
for the current season.**

`seasonal_team_gamelogs` (per-game team stats across a season, a finer
granularity than the season-total endpoint above) could not be
confirmed working — `400` in both attempts, including after adding a
`team` filter param per the SDK's own README usage pattern. The
season-total endpoint above was confirmed working as an alternative;
this is a real, unresolved gap in this session, not a claim that the
feed doesn't exist.

### 2. Play-by-play — **UNKNOWN (endpoint exists, real data not observed)**

`/nfl/{season}/games/{id}/playbyplay.json` responded `204 No Content`
for the one game this test could reach — a game scheduled for
2026-09-10 that had not yet been played at test time (2026-09-03). A
clean `204` (not an error) for an unplayed game is itself a real, useful
status-semantics finding — but it means **this test never observed an
actual play-by-play payload**, because no historical game was reachable
on this plan (see below) and the current season hadn't started yet.
Genuinely testing completeness/granularity here requires a follow-up
pass after 2026-09-10, once a real game has been played.

### 3. Box scores / game-detail data — **UNKNOWN (same constraint as PBP)**

`/nfl/{season}/games/{id}/boxscore.json` also responded `204 No Content`
for the same unplayed game — same honest limitation as play-by-play
above. Not tested against real game data in this session.

### 4. Lineups — **GREEN**

`/nfl/{season}/games/{id}/lineup.json` responded `200` with real,
substantive content **even for a game 7 days out**: full game context
(venue, broadcasters, a genuine weather **forecast** — wind speed/
direction, temperature, humidity, precipitation type — which could
independently feed MANSA's existing `WeatherAdapter`/`DataCategory.
WEATHER` category, a bonus finding beyond this test's four objectives),
plus `teamLineups[].expected.lineupPositions[]` — real depth-chart-level
detail (e.g., `"Offense-RB-1"`, `"Defense-DE-1"`) with a named player
where confirmed and an honest `null` where not yet announced (correctly
following this project's own null-not-neutral convention, not guessing
a starter). This is real, useful pre-game lineup data neither
BALLDONTLIE nor API-SPORTS offered at all.

## Cross-cutting findings

- **A genuine, reproducible plan restriction on prior-season game
  listings**, distinct from — and narrower than — API-SPORTS's blanket
  season gate: `week/N/games.json` AND the whole-season `games.json`
  both returned `403` for the 2025 season on this specific plan, while
  `standings.json` for that exact same season succeeded with full,
  real data. This is an inconsistent-looking but real access boundary,
  not a bug in this test's own requests (confirmed by trying two
  genuinely different feeds, not retrying the same one). **Practical
  effect: this plan cannot list or browse prior-season games at all**,
  which blocked a clean box-score/PBP/lineup test against real,
  completed-game data in this session.
- **Injuries** (`/nfl/injuries.json`): rich player bio data (height/
  weight/birthdate/age/birth city/country/college/rookie flag), but two
  of three sampled players had `currentInjury.description: "unknown"`
  rather than a real body-part/injury type — a real, partial data-gap,
  less severe than SportsDataIO's own 100%-scrambled trial descriptions
  but not fully reliable either.
- **`latest_updates`** (unique to MySportsFeeds among the three
  providers tested): a genuinely useful corrections/freshness feed — 120
  named sub-feeds (e.g., "Cumulative Player Stats v1.2", "Seasonal
  Games", "Weekly Games"), each carrying its own `lastUpdatedOn`
  timestamp. All were `null` in this sample (nothing has been fetched
  for the new season yet), but the mechanism itself is exactly the kind
  of corrections/staleness signal neither BALLDONTLIE nor API-SPORTS
  exposed.
- **Response headers carry real caching/freshness signal**: every
  successful response included `cache-control: no-transform,
  max-age=10800` (3-hour edge cache) and `x-cache: HIT/MISS` with hit
  counts — useful operational detail (this data is CDN-cached upstream
  for 3 hours regardless of subscription tier), but also means **the
  Near-Realtime tier's actual value cannot be assessed from response
  headers alone** — a 3-hour edge-cache TTL applies independent of
  whatever the underlying near-realtime-vs-delayed processing pipeline
  does.
- **Near-Realtime vs. 3-/5-/10-minute delayed tier: could not be
  empirically evaluated at all.** No NFL game was in progress at test
  time (2026 season kicks off 2026-09-09, six days after this test) —
  there was no live data to compare freshness against, on any tier.
  **This test cannot recommend the expensive Near-Realtime tier over a
  cheaper delayed tier**, because no evidence either way was collected.
  A real answer requires observing this same subscription during an
  actual live game and comparing its update latency against what a
  delayed tier's documented SLA promises — not done here.
- **Stable IDs**: MySportsFeeds' own numeric IDs (team `id`, player
  `id`, game `id`) are internally consistent across every feed sampled
  (e.g., team id 79 = SEA appeared identically in the schedule and
  lineup responses) — no identity-mapping work was attempted (no writes
  were made), but the raw IDs themselves show no inconsistency.
- **Pagination**: not observed to be needed or offered in this sample —
  every response was a single JSON object with an array-shaped payload
  (`games`, `teamStatsTotals`, `players`, `feedUpdates`), no `page`/
  `cursor` parameter appeared in any response's own structure. Not
  confirmed whether very large requests (e.g., a full season's play-by-
  play) would need one.
- **Compatibility with MANSA's canonical models**: `team_stats_totals`
  maps cleanly into the existing `TeamStatLine.stats: dict` shape (a
  provider-neutral dict field, by design). Lineups, box scores, and
  play-by-play have **no corresponding `DataCategory` or normalized
  model today** — `RosterEntry`/`ScheduleEntry`/`TeamStatLine`/
  `PlayerStatLine` don't fit lineup-position or play-level granularity.
  Building adapters for these would require new categories and models,
  a real architecture decision for Mac, not something this diagnostic
  pass resolved.

## Updated provider matrix (adds MySportsFeeds; BALLDONTLIE/API-SPORTS
rows carry forward unchanged from the 2026-09-03 bake-off)

GREEN = production-quality candidate · YELLOW = usable with
limitations/secondary validation · RED = inadequate · UNKNOWN = needs
further/live-season validation

| Capability | BALLDONTLIE | API-SPORTS | MySportsFeeds | SportsDataIO benchmark | MANSA requirement | Verdict |
|---|---|---|---|---|---|---|
| Team stats (current season) | **RED** — no endpoint exists in the official SDK | **RED** for current season — plan-gated to 2022–2024 | **GREEN** — real, deeply-typed schema, confirmed populated on a completed season and correctly zeroed (not erroring) for the in-progress one | Confirmed live | Needed | **MySportsFeeds is the only GREEN of the three for this specific gap** |
| Play-by-play | **RED** — no endpoint exists | **YELLOW** — `/games/events` exists but is a coarse scoring-summary, not real PBP | **UNKNOWN** — endpoint exists, returns clean `204` for an unplayed game, but no real payload was ever observed (no reachable historical or live game) | Not offered | Nice to have | Needs a post-2026-09-10 follow-up test to resolve |
| Box scores / game detail | n/a (not a named gap for BALLDONTLIE, no dedicated endpoint found) | Partially covered by `/games/statistics/teams` (GREEN within its 2022–2024 window) | **UNKNOWN** — same `204`-for-unplayed-game constraint as PBP above | Confirmed live | Needed | Needs the same follow-up test |
| Lineups | Not offered | Not tested | **GREEN** — real depth-chart-level "expected" lineup, correctly null where unconfirmed, plus a bonus weather forecast | Not confirmed offered | "Where useful" | MySportsFeeds is the clear leader here |
| Historical game listings | GREEN (2025 confirmed live) | YELLOW-RED — hard 2022–2024 window | **RED for this plan** — prior-season game lists return 403 on two different feeds, even though prior-season standings succeed | Multi-season | Needed for Time Machine backtesting | A genuine, plan-specific restriction |
| Standings | UNKNOWN (rate-limited both bake-off attempts) | GREEN within 2022–2024 | **GREEN** — real, fully-populated prior-season data, plausible internally | Confirmed live | Needed | MySportsFeeds and API-SPORTS both usable; BALLDONTLIE unconfirmed |
| Injuries | GREEN — specific, real descriptions | GREEN — specific, with expected-return-week detail | **YELLOW** — rich player bio data, but 2 of 3 sampled injury descriptions were literally `"unknown"` | Descriptions unmapped/scrambled in SDIO's own trial | Needed | All three beat the SDIO trial baseline; MySportsFeeds' text quality is the weakest of the three live-tested |
| Corrections / freshness signal | Not offered | Not offered | **GREEN** — unique `latest_updates` feed with 120 named sub-feed timestamps | Not offered | Nice to have | MySportsFeeds-exclusive strength |
| Near-Realtime tier value vs. cheaper delayed tiers | n/a | n/a | **UNKNOWN — genuinely untested**, no live game existed at test time | n/a | Don't overpay | Cannot recommend the expensive tier without live-game evidence |

## Recommendations

1. **MySportsFeeds materially closes the current-season team-stats gap**
   that neither BALLDONTLIE nor a currently-usable API-SPORTS call could
   close. Recommend it as the team-stats source in any future provider
   stack, contingent on the remaining validation below.

2. **Do not decide the Near-Realtime vs. delayed-tier question from this
   test.** No evidence was collected either way — the 2026 season hadn't
   started. **Recommendation: do not pay for Near-Realtime yet.** Run a
   short, cheap follow-up comparison once real games exist (after
   2026-09-09) — even the free/lowest tier would answer whether
   MySportsFeeds' actual data-arrival latency matters for MANSA's real
   polling cadence (Volume 2 §8's windows are ≥2 minutes outside the
   already-unreachable RAMP_5M tier) before paying for the fastest tier.

3. **Play-by-play and box-score completeness remain genuinely unresolved
   for MySportsFeeds** — not because the endpoints don't exist (they
   returned clean, well-formed `204`s, a good sign), but because no
   playable/played game was reachable in this session. **A follow-up
   test after a real 2026 game is played is required** before drawing
   any conclusion about PBP/box-score granularity.

4. **The cheapest credible MANSA NFL provider stack, based on
   everything tested across both diagnostic passes, is a composite —
   no single provider (including SportsDataIO) covers every category
   MANSA needs on its own:**
   - **BALLDONTLIE** for current-season schedules, rosters, injuries,
     player stats, and advanced/next-gen stats (free/low tier already
     reaches the current season, per the 2026-09-03 bake-off).
   - **MySportsFeeds** for current-season team stats and lineups
     specifically — the two capabilities BALLDONTLIE cannot provide at
     all — **at whatever tier the follow-up freshness test in
     recommendation 2 justifies**, not necessarily Near-Realtime.
   - **Play-by-play and box scores remain an open question** for both
     BALLDONTLIE (confirmed absent) and MySportsFeeds (unresolved,
     pending a real game) — SportsDataIO or a future live MySportsFeeds
     re-test would need to fill this if MANSA actually needs full PBP.
   - **API-SPORTS's role narrows further** after this test: its one
     unique strength from the 2026-09-03 bake-off (rich current-season
     team stats) is now matched or exceeded by MySportsFeeds without
     API-SPORTS's 2022–2024 plan restriction — it may no longer be worth
     a paid-plan upgrade unless a specific gap emerges that neither
     BALLDONTLIE nor MySportsFeeds covers.

5. **Architecture work required before any of this can be wired for
   real (not started here):** `DataCategory` has no category for
   lineups, box scores, or play-by-play today — new categories and
   normalized models would need to be designed (a real product/schema
   decision for Mac), not force-fit into `TeamStatLine`/`PlayerStatLine`.

6. **Remaining validation required before any migration work:**
   - A live, post-2026-09-09 re-test of play-by-play and box scores
     against an actual played game.
   - A live-game freshness comparison to answer the Near-Realtime
     question for real.
   - Resolving `seasonal_team_gamelogs`'s correct required parameters
     (per-game team stats across a season — a finer granularity than
     the season-total endpoint that was confirmed working).
   - Confirming with MySportsFeeds (support or docs, once reachable)
     whether the prior-season game-listing 403 is an expected CORE/
     STATS/DETAILS plan boundary or a trial-specific restriction that
     would lift on a paid plan.
   - Real identity-mapping work (`team_provider_ids`/`player_provider_ids`/
     `game_provider_ids`) — zero attempted here, same as the prior
     bake-off.

## What was and wasn't changed

- Diagnostic probe code (`app.diagnostics.msf_bakeoff`, the dev-only
  startup hook in `app.main`, `build_msf_bakeoff_client()` in
  `production_clients.py`) was built, exercised twice, and **fully
  reverted** — none of it exists in the codebase as of this report.
- `RUN_MSF_BAKEOFF` was set back to `"0"` on `sports-intel-layer`/dev.
- `MYSPORTSFEEDS_API_KEY` was never logged, returned, or otherwise
  surfaced outside the one client that used it.
- No production provider selection changed. No recommendation/business
  logic changed. No subscription purchased or changed by this session.
  Phase 7 / `cron-odds-worker` untouched throughout (confirmed `SKIPPED`
  on every push made during this test). Staging and production
  untouched. SportsDataIO's reserved trial call was never spent (zero
  SportsDataIO calls were made in this test).
