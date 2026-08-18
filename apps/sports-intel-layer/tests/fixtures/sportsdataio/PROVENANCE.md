# SportsDataIO fixture provenance

Unlike The Odds API/WeatherAPI/NewsAPI (Phase 3B/3C-i, fixture-first with no
live key), SportsDataIO was **live-validated** during Phase 3C-ii's
investigation: Mac's authenticated Free Trial account, 10 of a 12-call
budget spent across two rounds (2026-08-11/12 — see `PROGRESS.md` for the
full session history, including the stale-Railway-deployment incident and
the endpoint-path corrections against SportsDataIO's own documentation). An
11th call was spent 2026-08-18 on a single-purpose, single-endpoint capture
of `/v3/nfl/scores/json/Teams` (12/12 budget: 11 used, 1 remaining, final
call intentionally not authorized) — see this file's own section below and
`PROGRESS.md` for that round's full evidence trail. Four tiers apply here,
one more than 3C-i's three, because live capture makes a genuine fourth
tier possible:

- **CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE** — the field names, types,
  and nesting below were directly observed in a real 200 response. The
  *values* in scrambled/perturbed fields (documented per-fixture) are
  **not** production-representative — structure confirmed, content is not.
- **CONFIRMED FROM PROVIDER DOCUMENTATION** — Mac manually verified this
  against SportsDataIO's own authenticated documentation (endpoint paths,
  the `Ocp-Apim-Subscription-Key` auth header, season/week parameter
  format), not inferred from a search snippet.
- **ASSUMED** — not directly observed or documented; a reasonable
  inference not independently verified this session.
- **DEFERRED PRODUCTION VERIFICATION** — cannot be resolved by Free Trial
  data at all, scrambled or not: real (non-trial) data accuracy, production
  freshness/latency, real rate limits/quotas, SLA, commercial licensing
  behavior, production-scale throughput, actual commercial cost. Tracked
  centrally in `PROGRESS.md`'s DEFERRED — FINANCIAL/EXTERNAL DEPENDENCY
  checklist, not just here.

## A note on scrambled values

SportsDataIO's Free Trial scrambles specific fields, confirmed by direct
inspection of the full captures, not assumed:
- Rosters (`/Players/{team}`): every string-valued injury/depth field
  (`InjuryStatus`, `InjuryBodyPart`, `InjuryPractice`,
  `InjuryPracticeDescription`, `DepthPosition`, `DepthPositionCategory`,
  `CurrentStatus`) is literally `"Scrambled"` in all 94 captured rows.
  `DepthOrder` (numeric) is real for ~66% of rows, `null` for the rest —
  not itself scrambled, but also not this project's source of truth for
  depth rank (see below).
- Injuries (`/stats/json/Injuries/{season}/{week}`): `Status`, `BodyPart`,
  `Practice`, `PracticeDescription` are `"Scrambled"` in all 294 captured
  rows — **even on the dedicated, authoritative endpoint**. Only
  `DeclaredInactive` (a real boolean) and identity/context fields
  (`PlayerID`, `Name`, `Team`, `Opponent`, `Week`, `Season`) are real.
- PlayerStats (`/stats/json/PlayerGameStatsByWeek/{season}/{week}`): same
  injury-field scrambling as Rosters. Counting stats are visibly
  perturbed too — fractional values for fields that must be integers in
  reality (e.g. `PassingAttempts: 53.6`).
- TeamStats (`/scores/json/TeamGameStats/{season}/{week}`): every field
  *looks* like a clean int/float, but cross-checked across all 32 real
  rows, `Score` never equals the sum of `ScoreQuarter1-4`+`ScoreOvertime`
  (32/32 mismatches) and `CompletionPercentage` doesn't match
  `PassingCompletions`/`PassingAttempts` in 29/32 — scrambled via
  independent per-field perturbation, not visibly-fractional counts like
  PlayerStats. **Do not write a test asserting these numbers reconcile.**
- DepthCharts (`/DepthCharts`) and Schedules (`/Schedules/{season}`) were
  **not** observed to be scrambled — all 2,186 DepthCharts entries (32
  teams) and all 304 Schedules rows carried plausible, internally
  consistent real values. This is the concrete evidence behind the
  source-of-truth decision below.
- Teams (`/scores/json/Teams`, captured 2026-08-18 as its own single-purpose
  round): only `UpcomingOpponent` is scrambled (literally `"Scrambled"` in
  all 32 rows). Every identity/context field — `Key`, `TeamID`, `PlayerID`,
  `City`, `Name`, `FullName`, `Conference`, `Division`, `GlobalTeamID`,
  `StadiumDetails`, coaching staff names — is real and distinct across all
  32 rows, cross-checked against this project's own `teams` table (see
  below), not merely assumed real from shape alone.

## Source-of-truth decision (Mac, 2026-08-12), reflected in these fixtures

Depth-chart position/order comes from `/DepthCharts` — **not** Rosters'
own (scrambled) depth fields. Injury status/details come from the
dedicated `/stats/json/Injuries/{season}/{week}` — **not** Rosters' or
PlayerStats' overlapping (also scrambled) injury fields. These fixtures
and the adapters that consume them enforce this; nothing here promotes an
overlapping field into a competing source of truth.

## Fixture-by-fixture

| File | Scenario | Tier |
|---|---|---|
| `rosters_normal.json` | 2 real KC players — one with a real `DepthOrder`, one `null` | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE (values partly scrambled, see above) |
| `depth_charts_normal.json` | 2 full real team entries (Offense/Defense/SpecialTeams) — not scrambled | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE |
| `schedules_normal.json` | 3 real 2026REG Week 1 games, all `"Scheduled"` | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE |
| `schedules_unrecognized_status.json` | Synthetic — real game shape, `Status: "InProgress"` (never observed live) | N/A — synthetic, proves the adapter raises rather than guessing an unobserved status |
| `team_stats_week_bulk_normal.json` | 4 real rows, 2 games (`202510122` ARI/NO, `202510102` ATL/TB), 2025REG Week 1 | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE (values scrambled, see above) |
| `player_stats_week_bulk_normal.json` | 2 real rows, 2 different games — one with a real nested `ScoringDetails` array, one without | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE (values scrambled, see above) |
| `injuries_normal.json` | 3 real rows, 3 different teams | CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE (`Status`/body-part/practice fields scrambled) |
| `roster_malformed.json` | Synthetic — missing `PlayerID` | N/A — synthetic defect-injection fixture |
| `depth_charts_malformed.json` | Synthetic — an Offense entry missing `PlayerID` | N/A — synthetic defect-injection fixture |
| `schedules_malformed.json` | Synthetic — missing `GameKey` | N/A — synthetic defect-injection fixture |
| `team_stats_malformed.json` | Synthetic — missing `GameKey` | N/A — synthetic defect-injection fixture |
| `player_stats_malformed.json` | Synthetic — missing `PlayerID` | N/A — synthetic defect-injection fixture |
| `injuries_malformed.json` | Synthetic — missing `PlayerID` | N/A — synthetic defect-injection fixture |
| `teams_active_normal.json` | All 32 current NFL teams, real and complete (not a sample like the other fixtures above — the full universe is the point of this capture) | CONFIRMED FROM LIVE FREE TRIAL (identity fields only — `Key`/`FullName`/`TeamID`/etc.; `UpcomingOpponent` scrambled, see above) |

## Team identity verification (2026-08-18, single-endpoint round)

`teams_active_normal.json` was captured specifically to independently
verify SportsDataIO's own team-identifier field (`Key`, e.g. `"KC"`) for
all 32 current NFL teams before extending `team_provider_ids` coverage
beyond the 13 teams 3E-4A had fixture-confirmed. Deterministic
reconciliation (exact string match on `FullName` against this project's
`teams.name`, zero fuzzy matching) against the live dev `teams` table:

- **32/32 canonical teams reconciled, zero conflicts.** Every `teams.name`
  value matched exactly one `FullName` in the capture; no orphans on either
  side.
- **All 13 previously-confirmed `sportsdataio` mappings (ARI, ATL, BAL,
  BUF, CAR, CHI, KC, LAR, NE, NO, SF, SEA, TB) matched the live `Key`
  exactly.** No drift.
- **Dallas Cowboys / Philadelphia Eagles resolved:** the 3E-3 database rows
  (`DAL`, `PHI`) flagged in 3E-4A as inferred-not-fixture-confirmed are now
  **CONFIRMED CORRECT** — the live capture's `Key` for both teams matches
  the already-applied rows exactly. `TEAM_BACKFILL` (the Python source of
  truth) restores both entries with this citation.
- **`team_provider_ids` sportsdataio coverage taken to 32/32** — the
  remaining 17 teams (CIN, CLE, DEN, DET, GB, HOU, IND, JAX, LAC, LV, MIA,
  MIN, NYG, NYJ, PIT, TEN, WAS) added, each citing this fixture directly.
  `the_odds_api` coverage is unchanged at 6/32 — this round captured no
  Odds API evidence.

## Endpoint paths and auth (CONFIRMED FROM LIVE FREE TRIAL + PROVIDER DOCUMENTATION)

All seven paths below were called live and returned 200 with the
structures these fixtures reflect. The Injuries and PlayerGameStatsByWeek
paths were corrected once during this project against SportsDataIO's own
documentation (Mac, 2026-08-12) — the original assumed paths 404'd for
reasons unrelated to Free Trial access (wrong category segment, wrong
endpoint name), not access restrictions:

```
GET /v3/nfl/scores/json/Players/{team}
GET /v3/nfl/scores/json/DepthCharts
GET /v3/nfl/scores/json/Schedules/{season}
GET /v3/nfl/stats/json/Injuries/{season}/{week}
GET /v3/nfl/scores/json/TeamGameStats/{season}/{week}
GET /v3/nfl/stats/json/PlayerGameStatsByWeek/{season}/{week}
GET /v3/nfl/scores/json/Teams
```

Auth: `Ocp-Apim-Subscription-Key` request header — CONFIRMED, proven
working against all six categories, never a URL query parameter.

## Open decision, not resolved in fixtures or adapter code

`InjuryReport.description`'s intended source field remains genuinely
ambiguous (`BodyPart` vs `Practice` vs `PracticeDescription`, all
scrambled, no disambiguating content, and no field-level spec found in
`models.py`/`base.py`/the blueprint volumes). The adapter leaves it `None`
rather than guessing — see `app/adapters/providers/sportsdataio.py`'s
module docstring and PROGRESS.md for the reported alternatives.

## Remaining gaps, not solved by these fixtures

- Full status vocabulary for `InjuryReport.status` (entirely scrambled)
  remains ASSUMED beyond what's directly mapped.
- `players.team_id` roster-history gap has been closed (Phase 3F-1,
  `roster_memberships`); the `depth_chart_snapshots`/`game_id` structural
  mismatch has also been closed (Phase 3F-1, corrected to `team_id`-keyed).

## Game status vocabulary — CONFIRMED FROM PROVIDER DOCUMENTATION (2026-08-18)

Mac reviewed SportsDataIO's own provider documentation (not inferred from
a live capture) and confirmed the full `ScheduleEntry.status`/`Games.Status`
vocabulary: `Scheduled`, `InProgress`, `Final`, `F/OT`, `Suspended`,
`Postponed`, `Delayed`, `Canceled`, `Forfeit` — 9 values. This **upgrades**
`"Final"` from ASSUMED/DEFERRED LIVE VERIFICATION (3E-8) to **CONFIRMED
FROM PROVIDER DOCUMENTATION** — no live call was needed or spent to make
this determination; documentation review is a separate, valid provenance
tier from a live capture, and Mac's own review satisfies it here.

**FIXED (2026-08-18, same day, Mac's explicit approval).** `_SCHEDULE_STATUS_MAP`
(`app/adapters/providers/sportsdataio.py`) now maps all 9 documented
values to this project's existing 5-value internal vocabulary
(`games.status`, confirmed sufficient by inspection, not widened):
`Scheduled`→`scheduled`, `InProgress`→`live`, `Final`→`final`,
`F/OT`→`final` (a completed overtime game — the same terminal state as
Final, this is what makes Postgame Worker's game-final detection trigger
for an overtime game at all), `Postponed`→`postponed`,
`Canceled`→`canceled`, `Delayed`→`scheduled` (hasn't started, still
expected to be played), `Suspended`→`live` (play began, temporarily
halted), `Forfeit`→`final` (a completed result).

**Row isolation, the deliberate resilience fix for the availability gap
the map's earlier incompleteness caused.** `fetch_schedule` no longer
lets one row's normalization failure (an unrecognized status, or any
other per-row malformation) abort the entire batch — each row is
normalized inside its own try/except, a failing row is logged
(`_logger.warning`, includes the raw `GameKey`/`Status`) and skipped,
every other valid row in the same response still becomes a
`ScheduleEntry`. HTTP failure, invalid top-level JSON, or a non-array
payload still fail the whole call, unchanged. Live-regression-tested:
`Final`/`F/OT` both reach Postgame Ingestion identically; a mixed batch
(valid + `InProgress` + a genuinely unrecognized status) no longer fails
Master Refresh or Postgame Worker.

## NFL rescheduling behavior — CONFIRMED FROM PROVIDER DOCUMENTATION (2026-08-18)

- Rescheduled within the same game week: SportsDataIO keeps the same
  `GameID` and updates the existing game record in place.
- Rescheduled into a different game week: the original game transitions to
  `Postponed` (status) and a **new** game record with a **new** `GameID`
  is created for the rescheduled game.

Cross-checked against this project's own game-identity architecture
(`game_provider_ids`, `app.persistence.schedule.persist_schedule_entries`):
the same-week case is already correctly handled by the existing
upsert-by-`provider_game_id` logic (any Schedule field change, including a
time shift within the week, PATCHes the existing linked row — no special
case needed). The different-week case is also architecturally correct
by construction (a new `GameID` naturally resolves to no existing
`game_provider_ids` mapping, so a new `games` row is created, exactly as
SportsDataIO's own model intends) **provided `Postponed` is a recognized
status** — which depends on the same `_SCHEDULE_STATUS_MAP` gap above, not
a second, independent issue. No architecture change required beyond that
one shared fix.

## Timezone — CONFIRMED FROM PROVIDER DOCUMENTATION (2026-08-18)

SportsDataIO's NFL API times are Eastern Time (EST/EDT), with DST
transitions handled by SportsDataIO itself. **No conflict with this
project's UTC-normalization architecture**, confirmed by direct
inspection: `SportsDataIOScheduleAdapter.fetch_schedule` and
`_parse_timestamp_utc` exclusively read the `DateTimeUTC` field (already
provider-converted to UTC) — no code anywhere in this codebase reads the
raw Eastern `DateTime` field. `_parse_timestamp_utc`'s own existing
comment already flags that `DateTimeUTC` carries no explicit UTC offset
marker in the payload despite being UTC by name, which is exactly why
tzinfo is attached explicitly rather than trusted from the string. This
confirmation explains *why* that convention is safe; it changes nothing.

## Free Trial scrambling — reaffirmed (2026-08-18)

SportsDataIO's own documentation confirms Free Trial responses may
contain scrambled data, matching this project's own independent
cross-checks (see "A note on scrambled values" above). Trial captures
remain valid evidence for endpoint/schema **shape** — never for
production-accurate **statistical values**. No change to this discipline.

## NFL Timeframes endpoint + maintenance windows — recorded for future use, not integrated

SportsDataIO documents an NFL Timeframes endpoint (season/week resolution
metadata) and stated maintenance windows: first and third Wednesday of
each month, 4 AM–10 AM Eastern. Recorded here as CONFIRMED FROM PROVIDER
DOCUMENTATION for future operational use (e.g. Railway scheduling should
eventually avoid these windows) — **not integrated into current scope**,
per explicit instruction not to expand scope solely to wire this up. This
project's own season resolution (`app.persistence.seasons.
fetch_current_season_string`) remains the current mechanism; Timeframes is
not consumed anywhere in this codebase.

## Row isolation, Roster/DepthCharts/TeamStats/PlayerStats (2026-08-18, Data Dictionary reconciliation corrective pass)

Found and fixed in the same sweep as the Schedule status fix above.
`SportsDataIORosterAdapter.fetch_roster`, `_get_depth_chart_lookup`,
`SportsDataIOTeamStatsAdapter.fetch_team_stats`, and
`SportsDataIOPlayerStatsAdapter.fetch_player_stats` all wrapped their entire
row-building loop in one try/except, so one malformed row aborted the whole
call:

- **Roster**: one malformed player row took down that team's entire roster
  (~53 players). Fixed: each player row is isolated (logged, skipped),
  other valid players in the same team's roster still come back.
- **DepthCharts**: one malformed depth-chart entry took down the whole
  league-wide depth-chart lookup (shared, bulk-cached, used by every team's
  roster fetch that cycle). Fixed: each entry is isolated; other teams'
  depth ranks are unaffected by one team's bad entry.
- **TeamStats/PlayerStats**: `rows` is the whole week's bulk payload, shared
  across every game that week via `_WeeklyBulkCacheMixin` — a malformed row
  belonging to a *different* game (or a different player, for PlayerStats)
  could already take down the specific game being fetched, purely from
  filtering the shared bulk list down to the requested `GameKey`. Fixed:
  the GameKey-filtering step and the per-row model-building step are both
  isolated (logged, skipped) instead of one try/except around the whole
  thing.

**Unchanged, per explicit instruction:** HTTP failure / invalid top-level
JSON / non-array payload still fail the whole call (via `_get`/
`_parse_json_array`, before any of these loops start). The DepthCharts
*call itself* failing outright (a transport/request-level failure, not a
malformed row within a successful response) still propagates and fails
`fetch_roster` unchanged — that boundary is a deliberate, separate decision
(this class's own module docstring), not touched by this fix. No enum
vocabulary was expanded and no schema was changed as part of this pass.
