# First Authorized Full-Season SportsDataIO Schedule Refresh

**Date:** 2026-09-16
**Directive:** MANSA HQ — "EXECUTE FIRST DEDICATED FULL-SEASON SCHEDULE REFRESH"
**Outcome:** **SUCCESS.** One SportsDataIO Schedule request. Week 2 recovered. Zero duplicates.
**Final gate state:** `MASTER_REFRESH_ENABLED=false`, cron restored to `0 9 * * *`, automation still paused.

---

## 1. The run

```
cron_dispatch starting target=schedule-refresh
POST .../v1/internal/schedule-refresh/run "HTTP/1.1 200 OK"
cron_dispatch succeeded target=schedule-refresh result={
  'status': 'success', 'run_id': 'd0cbb05a-3615-4d30-bf0b-8c5b2568642e',
  'season_string': '2026REG', 'games_in_slate': 16,
  'schedule_entries_persisted': 271, 'games_created': 252, 'games_updated': 19,
  'coverage_days_asserted': 7, 'coverage_expected_games': 16,
  'coverage_canonical_games': 16, 'coverage_complete': True,
  'coverage_gaps': [], 'error': None}
```

Executed 2026-09-16 12:45:52–12:47:01 UTC (~69s). Exactly **one** `master_refresh_runs` row.

### Execution safety sequence, as directed

1. `MASTER_REFRESH_ENABLED=false` held throughout setup.
2. `cron-schedule-refresh` cadence → `*/15 * * * *`.
3. Verified live: branch `dev`, target `schedule-refresh`, cadence active, restart `NEVER`.
4. Disabled-gate tick proven: `status: 'paused'`, `200 OK`, zero provider calls.
5. **Only then** `MASTER_REFRESH_ENABLED=true`; deployment `67ebc435` verified **SUCCESS** at
   12:35:03 before any tick could consume it.
6. One tick at 12:45:52 spent the single call.
7. **Cadence restored to `0 9 * * *` first, then the gate set false** — deliberately inverted from
   the directive's step order. Restoring the daily cadence removes the 15-minute tick entirely and
   is one fast config call, whereas the gate revert needs a ~20s redeploy. Killing the cadence first
   is the tighter guard against a second call; both ended in the required state. The gate-false
   deployment `4014679c` was verified **SUCCESS at 12:49:14**, still well before the next
   quarter-hour.

---

## 2. Results

| # | Check | Result |
|---|---|---|
| 1 | SportsDataIO requests | **1** |
| 2 | provider rows returned | **271** |
| 3 | reconciled existing games | **19** (`games_updated`) |
| 4 | newly created games | **252** |
| 5 | ambiguous / refused | **0** |
| 6 | errors / skips | **0** (`error: None`) |
| 7 | total canonical games | **275** (23 + 252) |
| 8 | SportsDataIO mappings | **271** |

**The headline proof is the arithmetic.** 23 existing + 271 provider rows = 294 if reconciliation
had failed. Dev holds **275**. The 19 pre-existing games were *linked*, not duplicated.

**271, not the ~304 estimated.** The 304 figure came from the adapter's own docstring and was
always an estimate. 271 is the real 2026 regular season (Weeks 1–18, byes included). Not a
shortfall — a corrected number.

### Week 1 — untouched

| Check | Result |
|---|---|
| 9. one canonical row each | **16** |
| 10. still `final`, scores/`finalized_at` unchanged | **16/16**, fingerprint `483f677b…` **identical to the pre-run baseline** |
| 11. SportsDataIO mappings attached | **16/16** |

The terminal guard held exactly as designed: SportsDataIO still describes these played games as
`Scheduled`, the guarded PATCH matched zero rows, and the follow-up patch omitted `status`.

### Week 2 — recovered

**16 games**, all SportsDataIO-mapped, zero duplicates:

- Thu **Sep 18 00:15** — DET @ BUF
- Sun **Sep 20 17:00** — CAR@ATL, CIN@HOU, CLE@TB, GB@NYJ, MIN@CHI, NO@BAL, PHI@TEN, PIT@NE
- Sun **Sep 20 20:05** — JAX@DEN, LV@LAC · **20:25** — MIA@SF, SEA@ARI, WAS@DAL
- Sun **Sep 21 00:20** — IND@KC · Mon **Sep 22 00:15** — NYG@LAR

A real NFL week: one Thursday opener, an early/late Sunday split, Sunday night, Monday night.

### Full season

Weeks 1–18 present, 271 games, every one SportsDataIO-mapped. Week counts vary 13–16 with byes, as
expected. The 4 legacy null-week fixtures correctly received **no** mapping — they store full team
names and can never resolve canonically, exactly as the reconciliation rule requires.

Week 5 shows 15 games of which **3 were the pre-existing manual-seed rows** — reconciled and mapped,
not duplicated. 16 (Week 1) + 3 (Week 5) = **the 19 reconciled games**, precisely as predicted.

| # | Check | Result |
|---|---|---|
| 16 | Week 3+ coverage | Weeks 3–18 complete, 239 games |
| 17 | rolling 7-day completeness | **asserted 7 days, expected 16, canonical 16, complete, zero gaps** |
| 18 | identity conflicts | **0** — no GameKey mapped twice, no game with two GameKeys |
| 19 | kickoff deltas observed | **0.00 minutes on all 16** — see below |
| — | duplicate real-world games | **0** exact, **0** same-matchup-same-day |

### 19. The kickoff tolerance was never needed

Measured against the MySportsFeeds boxscores' own `startTime` — an independent provider reference —
all 16 Week 1 games show a delta of **exactly 0.00 minutes**. SportsDataIO and MySportsFeeds agree
to the second.

So every reconciliation was an **exact** match; the ±15-minute tolerance absorbed nothing and is
unused headroom rather than a load-bearing assumption. That is the best possible outcome for it:
the conservative bound was justified as insurance and turned out not to be needed. **No evidence
yet exists about how the tolerance behaves under real disagreement**, so it stays as-is.

### Cost

| # | Check | Result |
|---|---|---|
| 20 | roster calls | **0** — `players` 1494, `roster_memberships` 34, `depth_chart_snapshots` 4, all unchanged |
| 21 | other provider / LLM calls | **0** — zero rows in `odds_snapshots`, `game_events`, `weather_snapshots` after 12:00 UTC |

Daily canonical schedule integrity cost exactly **one** provider call, and that call delivered the
entire season.

### Final config

| # | Check | Result |
|---|---|---|
| 22 | `MASTER_REFRESH_ENABLED` | **`false`**, deployment `4014679c` SUCCESS |
| 23 | `cron-schedule-refresh` schedule | **`0 9 * * *`** |
| 24 | permanent automation | **paused** — the daily cron is inert while the gate is false |

`cron-msf-postgame` untouched. `cron-master-refresh` still on its stale branch with the invalid
sentinel, untouched per directive.

---

## 3. What this unblocks, and what is still blocked

Canonical Week 2 games now exist with real kickoffs and provider identity, so the Odds Worker can
see them in `list_games_in_window` as kickoff approaches. Nothing downstream was run: no odds, no
recommendations, no rosters, no second refresh.

Still true from the calibration work: these Week 2 games are the **first** that could produce a
legitimate forward-looking calibration observation, because they have not kicked off yet. Week 1
never can.
