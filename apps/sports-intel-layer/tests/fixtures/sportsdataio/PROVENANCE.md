# SportsDataIO fixture provenance

Unlike The Odds API/WeatherAPI/NewsAPI (Phase 3B/3C-i, fixture-first with no
live key), SportsDataIO was **live-validated** during Phase 3C-ii's
investigation: Mac's authenticated Free Trial account, 10 of a 12-call
budget spent across two rounds (2026-08-11/12 — see `PROGRESS.md` for the
full session history, including the stale-Railway-deployment incident and
the endpoint-path corrections against SportsDataIO's own documentation).
Four tiers apply here, one more than 3C-i's three, because live capture
makes a genuine fourth tier possible:

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

## Endpoint paths and auth (CONFIRMED FROM LIVE FREE TRIAL + PROVIDER DOCUMENTATION)

All six paths below were called live and returned 200 with the structures
these fixtures reflect. The Injuries and PlayerGameStatsByWeek paths were
corrected once during this project against SportsDataIO's own
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

- Full status vocabularies for `InjuryReport.status` (entirely scrambled)
  and `ScheduleEntry.status` (only `"Scheduled"`/`null` observed — season
  hasn't started) remain ASSUMED beyond what's directly mapped.
- `players.team_id` roster-history gap and the `depth_chart_snapshots`/
  `game_id` structural mismatch are Milestone F schema questions, not
  touched by this fixture suite or the adapters that consume it.
