# MANSA NFL Provider Bake-Off — BALLDONTLIE vs API-SPORTS (2026-09-03)

**Status: diagnostic only. No provider migration was made or proposed as
code. SportsDataIO remains the production provider unchanged.**

## Objective

Determine whether BALLDONTLIE and/or API-SPORTS can replace most/all of
SportsDataIO for MANSA's NFL data needs, via a controlled, DEV-only,
budget-bounded set of live calls against both providers using the
credentials Mac configured in Railway DEV (`BALLDONTLIE_API_KEY`,
`API_SPORTS_NFL_KEY`).

## Method

- Inspected the existing provider-neutral architecture first
  (`apps/sports-intel-layer/app/adapters/base.py`, `models.py`,
  `providers/sportsdataio.py`) to establish the real SportsDataIO
  benchmark and the canonical normalized shapes (`ScheduleEntry`,
  `RosterEntry`, `InjuryReport`, `TeamStatLine`, `PlayerStatLine`, etc.)
  any new adapter would need to map into.
- This workspace's own network egress policy blocks direct HTTPS to
  `api-sports.io`, `balldontlie.io`/`api.balldontlie.io`, and (as
  discovered mid-task) `sportsdata.io`/`api.the-odds-api.com` and even
  this project's own `*.up.railway.app` service domains — so neither
  vendor documentation nor the diagnostic endpoint itself could be
  reached directly from this session. Endpoint shapes were confirmed
  instead from the official `balldontlie` PyPI package's source
  (`nfl/api.py`/`nfl/models.py`, pinned dependency, unrestricted PyPI
  egress) and from public documentation excerpts (WebSearch). Live
  results were retrieved via Railway's own deploy logs
  (`logger.warning`, since this service's root logger defaults to
  WARNING — the same lesson Phase 7.0B Gate B's own discovery probe
  already established) rather than an HTTP response, since no inbound
  call could reach the service either.
- Built a temporary, dev-only diagnostic module
  (`app.diagnostics.nfl_bakeoff`, gated behind `RUN_NFL_BAKEOFF=1`,
  never wired into any permanent route) that made a small, curated set
  of live calls against both providers, logged full results, and was
  **reverted immediately after this report was produced** — the same
  "temporary probe, then revert" discipline already used for Phase
  7.0B's own Gate B discovery probes. `RUN_NFL_BAKEOFF` was set back to
  `0` afterward; `NFL_BAKEOFF_TOKEN`, a leftover unused Railway variable
  from an earlier (abandoned, HTTP-endpoint-based) version of this
  probe, was left in place since there is no Railway MCP tool available
  in this session to delete a variable outright — it is inert dead
  configuration and can be removed by hand whenever convenient.
- Two runs were needed: Run 1 surfaced two bugs in the probe itself
  (BALLDONTLIE's rate limit is 5 requests/**minute**, not the 3-second
  pacing the probe used; and team-ID resolution accidentally ran against
  a log-truncated copy of the teams list, so "team-scoped" calls ran
  unscoped). Run 2 fixed both and used API-SPORTS's confirmed-allowed
  season window. Total: **38 live calls across both providers** (18
  BALLDONTLIE, 20 API-SPORTS) — well under either vendor's daily quota
  (BALLDONTLIE: 5/min, no daily cap observed; API-SPORTS: 100/day, ~93
  remaining after this bake-off).
- No writes were made to any table; no recommendation/business logic
  was touched; `cron-odds-worker` stayed frozen (`SKIPPED` on every
  push, confirmed via Railway deployment status) throughout; staging
  and production were never touched.

## Provider matrix

GREEN = production-quality candidate · YELLOW = usable with
limitations/secondary validation · RED = inadequate · UNKNOWN = needs
further/live-season validation

| Capability | BALLDONTLIE | API-SPORTS | SportsDataIO benchmark | MANSA requirement | Verdict |
|---|---|---|---|---|---|
| Schedules/games | `/nfl/v1/games`: confirmed live for **both** 2026 (in-progress) and 2025 (completed) seasons, no plan restriction observed | `/games`: confirmed live but **only within a 2022–2024 season window on this plan** — 2025 and 2026 both returned `results:0` with an explicit "Free plans do not have access to this season" error | `/Schedules/{season}`: confirmed live, full 9-value status vocabulary | Must reach the **current** season | **GREEN** / **RED for current season** (season-plan-gated) |
| Teams | 32 teams, clean typed fields (conference/division/location/name/abbreviation) | 34 results for one call (2 more than the real 32-team league — a minor, unexplained inconsistency); richer metadata than BALLDONTLIE (coach, owner, stadium, founding year) | Confirmed live | Any | **GREEN** / **GREEN** (season-gated, same restriction as above) |
| Rosters | `/nfl/v1/players/active`: cursor-paginated, rich fields (position/height/weight/jersey/college/experience/age), current | `/players`: full roster incl. practice-squad/IR players, adds `salary`(!) and `experience`; **one of 94 rows in the sample had corrupted/shifted fields** (`age: 241`, `height: "8"`, `weight: "Harvard"` — a college name leaked into the weight field) | Players+DepthCharts merge, live-validated | Needs current | **GREEN** / **YELLOW** (real capability, real row-level corruption observed) |
| Active-player status | Dedicated `/players/active` endpoint — this *is* the active-status signal, not a boolean field | Not directly tested (no dedicated endpoint found; `group` field on `/players` rows, e.g. "Injured Reserve Or O", implies status but wasn't the focus of this pass) | Via DepthCharts merge | Needed | **GREEN** / **UNKNOWN** |
| Injuries | `/nfl/v1/player_injuries`: real, specific, non-scrambled descriptions ("broken nose", Achilles rehab timeline, practice-window guidance) | `/injuries`: equally real and specific, **with expected-return-week detail** ("PUP... Expected Return - Week 6"); requires `id` or `team` param (confirmed) | Descriptions unmapped in SDIO's own free-trial data (100% "Scrambled" placeholder text) | Needed | **GREEN** — both meaningfully better than the SDIO trial baseline |
| Standings | `/nfl/v1/standings`: endpoint confirmed to exist, accepts just `season` — **hit rate-limiting (429) on both attempts, no successful sample captured** | `/standings`: confirmed live, rich (streak, home/road/conference/division splits, points for/against/differential) | Confirmed live | Needed | **UNKNOWN** (real gap in this bake-off, not a provider defect) / **GREEN**, but only within the 2022–2024 window |
| Player stats | `/nfl/v1/stats` (per-game) and `/nfl/v1/season_stats` (season totals): both confirmed live, ~50 typed fields, correct nulls for non-applicable positions | `/players/statistics`: confirmed live, full season totals grouped by category (Passing/Rushing/etc.) — usable but a name/value list schema rather than flat typed fields | Confirmed live (SDIO trial numbers themselves internally inconsistent, per that adapter's own docstring) | Needed | **GREEN** / **GREEN**, season-gated |
| Team stats | **Confirmed absent** — no team-level stats endpoint exists anywhere in the official SDK (`stats`/`season_stats` are both player-scoped only) | `/games/statistics/teams?id=<game>`: confirmed live and genuinely rich — first downs (with passing/rushing/penalty splits, 3rd/4th-down efficiency), total yards/plays, red-zone efficiency, possession time, turnovers, sacks — **arguably richer than SportsDataIO's own TeamGameStats** | Confirmed live (`TeamGameStats`) | Needed | **RED** / **GREEN**, but only within the 2022–2024 window on this plan |
| Advanced stats | `/nfl/v1/advanced_stats/passing`: confirmed live — real next-gen-style metrics (avg air yards, aggressiveness, completion % above expectation) **SportsDataIO does not offer at all** | Not directly tested; no dedicated endpoint found in this vertical | Not offered | Nice to have | **GREEN** (a real BALLDONTLIE-exclusive strength) / **UNKNOWN**, likely absent |
| Play-by-play | **Confirmed absent** from the vendor's own SDK — no endpoint exists | `/games/events`: exists, but returned only **9 events for a full game** — a scoring-play log (TD/FG entries with a running score and a one-line comment), not real per-down play-by-play | Not offered | Nice to have | **RED** / **YELLOW** (real capability, much coarser than true PBP — "scoring summary," not PBP) |
| Final scores/results | Real final scores, per-quarter breakdown, plus a human-readable one-line result summary — **quarter-score nulls observed even on `status: Final` games** (a genuine granularity gap) | Real final scores with a clean two-value status vocabulary (`short`/`long`); preseason and regular-season games are mixed in the same response and need client-side filtering by `stage` | Confirmed live | Needed | **GREEN** (minor gaps) / **GREEN** (needs stage filtering) |
| Historical availability | `seasons[]` accepted arbitrary years; 2025 and 2026 both confirmed live; depth beyond that untested in this pass | **Hard-gated to exactly 2022–2024 on this plan** — both 2025 (too new) and 2020 (too old) were explicitly rejected with the same "plan" error | Multi-season | Needs at least the prior season for Time Machine backtesting | **GREEN** (untested beyond 1 season back) / **YELLOW-RED** — a real 3-year window, not a data gap but a genuine plan-tier limitation |

## Cross-cutting notes

- **BALLDONTLIE rate limit**: 5 requests/minute, confirmed via its own
  `x-ratelimit-limit` header and by triggering real 429s twice in this
  bake-off. Fine for MANSA's actual per-game polling cadence (Volume 2
  §8's adaptive windows are all ≥2 minutes except the already-unreachable
  RAMP_5M tier) — but would matter for any bulk backfill/replay
  operation, which would need a real token-bucket client, not a fixed
  sleep (this bake-off's own probe under-shot the correct pacing on its
  first attempt for exactly this reason).
- **API-SPORTS rate limit**: 10/minute soft, 100/day hard on this key.
  The 100/day cap is the more binding constraint for any real per-game
  polling cadence across a full 16-game NFL Sunday.
- **API-SPORTS's season-plan gate (2022–2024 only) is the single
  largest finding of this bake-off.** It means this specific key's plan
  cannot serve MANSA's actual product need — current, in-progress-season
  data — for schedules, rosters, standings, or player stats **at all**,
  independent of data quality. A plan upgrade would very plausibly fix
  this (the `/leagues` endpoint's own coverage metadata shows the
  underlying data exists for 2025/2026, e.g. `injuries: true` and
  `players: true` for the current season) — but no upgrade was
  authorized or purchased for this bake-off.
- **Team-level stats is the one capability BALLDONTLIE cannot provide in
  any form**, confirmed from its own SDK source rather than a live 404.
  API-SPORTS can provide it, and richly — but only within its 2022–2024
  window on the current plan, which makes it unusable for *current*
  team stats today without a plan change.
- Neither provider's identity fields (team IDs, player IDs, game IDs)
  were mapped into MANSA's canonical `team_provider_ids`/
  `player_provider_ids`/`game_provider_ids` tables — this bake-off made
  zero database writes, per its own diagnostic-only scope.

## Recommendations

1. **Recommended primary provider (for current-season schedules,
   rosters, injuries, player stats, advanced stats): BALLDONTLIE.** It
   is the only one of the two that reaches the current 2026 season and
   the just-completed 2025 season at all on the plan Mac configured, and
   its data quality on every category tested was real, specific, and at
   least as good as (injuries, advanced stats: better than)
   SportsDataIO's own free-trial baseline.

2. **Recommended secondary/fallback: API-SPORTS, scoped narrowly to team
   stats and richer standings/team metadata — contingent on a plan
   upgrade Mac has not authorized.** As configured today it cannot reach
   2025/2026 at all, so it is not currently usable for any live,
   current-season purpose. If and when its plan is upgraded, it closes
   BALLDONTLIE's one real structural gap (team-level box score stats)
   with data that looked genuinely richer than SportsDataIO's own
   `TeamGameStats` in this sample.

3. **Capabilities still requiring another source (SportsDataIO, or a
   later-authorized API-SPORTS plan upgrade):**
   - Team-level game stats for the **current** season (BALLDONTLIE:
     absent entirely; API-SPORTS: present but plan-gated to 2022–2024).
   - Real play-by-play (neither provider offers it — BALLDONTLIE has
     nothing; API-SPORTS's `/games/events` is a coarse scoring-play log,
     not full PBP).
   - Historical depth beyond 3 years on API-SPORTS specifically (not a
     BALLDONTLIE limitation as tested).

4. **Estimated provider architecture** (not built — a direction only):
   keep the existing provider-neutral `ProviderAdapter` pattern
   unchanged. Add `BALLDONTLIE*Adapter` classes for
   `ScheduleAdapter`/`RosterAdapter`/`InjuryAdapter`/`PlayerStatsAdapter`
   (mapping cleanly into the existing normalized models), plus a new,
   explicitly-scoped category for advanced/next-gen-style stats (not a
   forced fit into `PlayerStatLine.stats` — a real blueprint decision
   for Mac, not resolved here). Add an `APISportsTeamStatsAdapter` for
   `TeamStatsAdapter` **only if/when** the plan is upgraded to cover the
   current season; until then it would sit unused, the same "wired but
   deliberately unexercised" pattern this project already uses for
   Master Refresh's own SportsDataIO credential.

5. **Remaining validation required before any real migration work:**
   - A clean, properly-paced BALLDONTLIE `/standings` sample (this
     bake-off never got a successful call through — rate-limited both
     times, not a confirmed defect).
   - A live-fire test with a *fresh* BALLDONTLIE-vs-SportsDataIO
     comparison on the **same real game**, once one exists this season,
     to check for score/player-name/timestamp disagreement — this
     bake-off compared schema/endpoint shape and general data quality,
     not cross-provider agreement on identical events.
   - Whether Mac wants to authorize an API-SPORTS plan upgrade to reach
     the current season (a real cost decision, not this bake-off's to
     make).
   - Real identity-mapping work (`team_provider_ids`/`player_provider_ids`/
     `game_provider_ids` population and a deterministic game-linking
     pass, mirroring the existing Odds Worker's own linking module) —
     zero of this was attempted here.
   - A longer observation window to test freshness/update cadence
     (this bake-off is a single snapshot in time and cannot speak to how
     quickly either provider's data updates after a real play or score
     change).

6. **Does either provider materially reduce the need for SportsDataIO?**
   **Partially, not fully.** BALLDONTLIE looks like a credible
   candidate to replace SportsDataIO for schedules, rosters, injuries,
   and player/advanced stats — it reaches the current season and its
   sample data was as good as or better than SportsDataIO's own
   (unverified, self-admittedly "scrambled") free-trial data on every
   category compared. But **team-level stats for the current season
   remains uncovered by either candidate as configured today** — the one
   provider that can supply it (API-SPORTS) is plan-gated away from the
   current season entirely. SportsDataIO (or a future API-SPORTS plan
   upgrade) would still be needed for that one capability regardless of
   which primary provider MANSA otherwise adopts.

## What was and wasn't changed

- Diagnostic probe code (`app.diagnostics.nfl_bakeoff`, the dev-only
  startup hook in `app.main`, `build_bakeoff_clients()` in
  `production_clients.py`) was built, exercised twice, and **fully
  reverted** — none of it exists in the codebase as of this report.
- `RUN_NFL_BAKEOFF` was set back to `"0"` on `sports-intel-layer`/dev.
  `NFL_BAKEOFF_TOKEN` (an unused leftover from an earlier, abandoned
  version of the probe) remains set but is inert dead configuration;
  no Railway MCP tool in this session can delete a variable outright.
- Neither `BALLDONTLIE_API_KEY` nor `API_SPORTS_NFL_KEY` was ever
  logged, returned, or otherwise surfaced outside the two provider
  clients that used them.
- No production provider selection changed. No recommendation/business
  logic changed. Phase 7 / `cron-odds-worker` untouched throughout
  (confirmed `SKIPPED` on every push made during this bake-off). Staging
  and production untouched.
