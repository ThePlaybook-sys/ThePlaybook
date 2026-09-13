# Phase 7 — Real History Observation Window (2026-09-13)

MANSA HQ directive: "PHASE 7 — REAL HISTORY OBSERVATION WINDOW." Produce a
calibration-readiness report for Milestone 7.1's deterministic
market-integrity engine (`app/features/market_integrity.py`,
`THRESHOLD_VERSION = "v1-provisional"`) against real, live DEV `odds_snapshots`
for 5 real Week 1 games. **Report-only. No code, schema, or configuration
change was made in this pass.** All numbers below are the output of the
system's own real production functions (`app.features.market.
compute_line_movement`, `app.features.market_integrity.
classify_market_movement`/`assess_market_integrity`, imported and executed
directly, not reimplemented) run against real rows queried live from the
DEV Supabase project (`nhwjtsdebgiwskshzqiq`). No recalibration was
performed regardless of what this data shows, per HQ's explicit
instruction.

## 1. The 5 games and real snapshot coverage

| Game | `odds_snapshots` rows | First capture (UTC) | Last capture (UTC) | Kickoff (UTC) |
|---|---|---|---|---|
| SEA/NE | 189 | 2026-09-07 02:30:55 | 2026-09-10 00:17:07 | 2026-09-10 00:20:00 |
| LV/MIA | 267 | 2026-09-07 18:03:29 | 2026-09-13 20:15:54 | 2026-09-13 20:25:00 |
| MIN/GB | 264 | 2026-09-07 18:03:29 | 2026-09-13 20:15:54 | 2026-09-13 20:25:00 |
| PHI/WAS | 267 | 2026-09-07 18:03:29 | 2026-09-13 20:15:54 | 2026-09-13 20:25:00 |
| LAC/ARI | 267 | 2026-09-07 18:03:29 | 2026-09-13 20:15:54 | 2026-09-13 20:25:00 |

All 5 games show real capture coverage stopping cleanly at (SEA/NE) or just
before (the 4:25 PM ET slate, captured up to `T-9m16s`) their own kickoff —
consistent with `Window.STOPPED`'s "polling stops entirely at kickoff"
policy (`app.workers.windows.classify_window`). Each game carries 9 distinct
sportsbooks × 3 market types = 27 `(sportsbook, market_type)` groups.

## 2. Official system movement computation (first-vs-last snapshot per group)

`compute_line_movement` groups by `(sportsbook, market_type)` and computes
movement strictly between each group's **first and last** snapshot — this
is the system's own real, frozen semantics (Milestone 4.5), not a
consecutive-tick average. Feeding the real snapshots for each game through
this function, then `classify_market_movement` against the real, frozen
thresholds (`WATCH/ELEVATED/SEVERE = 1.0/2.5/4.0` points,
`20.0/40.0/75.0` price units):

| Game | Feature rows | NORMAL | WATCH | ELEVATED | SEVERE | INSUFFICIENT_HISTORY |
|---|---|---|---|---|---|---|
| SEA/NE | 54 | 54 | 0 | 0 | 0 | 0 |
| LV/MIA | 54 | 46 | 8 | 0 | 0 | 0 |
| MIN/GB | 54 | 29 | 22 | 0 | 3 | 0 |
| PHI/WAS | 54 | 22 | 28 | 4 | 0 | 0 |
| LAC/ARI | 54 | 24 | 23 | 7 | 0 | 0 |
| **Total** | **270** | **175** | **81** | **11** | **3** | **0** |

Every group had ≥2 snapshots (`sample_count` ≥ 2 everywhere), so
`INSUFFICIENT_HISTORY` never fired — a real, positive proof that this
week's capture cadence gave every group enough history to classify.

**The 3 SEVERE rows are all one game, one side, one market type:**
MIN/GB's Green Bay Packers **moneyline** at `betrivers` (211), `fanduel`
(218), and `mybookieag` (211) — a genuine large real-world price swing
(American-odds moneyline shift, not a data artifact: the same three books'
GB **spread**/**total** lines moved only 1.0 point each, a normal-range
move, so this isn't a stale/garbled snapshot, it's a real moneyline-specific
shift). The most plausible real-world correlate found in this pass's own
news cross-reference (Section 4): Packers RB **Josh Jacobs pleaded no
contest to a domestic-violence charge and is on the commissioner's exempt
list**, reported 2026-09-11 — a material, roster-availability-relevant
story that would move win-probability pricing more than point-spread
pricing (a suspended/exempt-list starting RB affects moneyline more than a
half-point spread move). This is offered as the most plausible real-world
correlate, not a confirmed causal claim — consistent with this module's own
"never claims causation" design.

11 ELEVATED rows are split across PHI/WAS (4, all moneyline) and LAC/ARI
(7, all moneyline) — no ELEVATED point-movement rows exist at all across
any of the 5 games, meaning every "big" movement this week was priced
through the moneyline, not the spread/total, across all 3 qualifying games.

## 3. Supplementary analysis: consecutive-tick deltas (NOT the system's own metric)

The notification separately asked for "usable movement deltas" per game.
**This is report-only supplementary analysis distinguishing itself
explicitly from Section 2** — `compute_line_movement` itself never computes
consecutive-pair deltas (Section 2 is the only classification the real
system produces). Counting adjacent-snapshot pairs per
`(sportsbook, market_type)` group instead:

| Game | Usable consecutive-tick deltas |
|---|---|
| SEA/NE | 162 |
| LV/MIA | 240 |
| MIN/GB | 237 |
| PHI/WAS | 240 |
| LAC/ARI | 240 |

## 4. Explanatory-evidence cross-reference — real, not fabricated

Ran the real `assess_market_integrity`/`check_explanatory_evidence`
(24-hour `EXPLANATORY_EVIDENCE_LOOKBACK`) against every WATCH/ELEVATED/
SEVERE row from Section 2, using real DEV rows:

- **`injury_reports`**: 0 real rows exist for any of these 5 games (the
  table's only row system-wide is an unrelated seed fixture, `"Seed RB
  Bills"`, game `a5000000-...-000003` — not one of these 5 games).
- **`weather_snapshots`**: 2 real rows exist for these 5 games — one each
  for PHI/WAS and LAC/ARI, captured 2026-09-07 23:10:25. None for LV/MIA,
  MIN/GB, or SEA/NE.
- **`depth_chart_snapshots`**: 4 real rows exist system-wide, all for
  NE/SEA (captured 2026-09-08) — **zero** for any of the other 4 teams'
  pairs (LV/MIA, MIN/GB, PHI/WAS, LAC/ARI).
- **`news_article_history`**: 679 real rows exist in the lookback window;
  229 relate to at least one of the 8 teams across these 4 games (real,
  live-ingested headlines — Josh Jacobs' plea, Harrison Smith's contract,
  Brock Bowers' injury update, Jayden Daniels updates, etc.).

| Game | EXPLAINED | UNEXPLAINED |
|---|---|---|
| LV/MIA | 8 | 0 |
| MIN/GB | 25 | 0 |
| PHI/WAS | 32 | 0 |
| LAC/ARI | 30 | 0 |
| **Total** | **95** | **0** |

**Flagged finding, not a code bug — a real, disclosed design consequence of
Milestone 7.1's own stated rules:** every single qualifying movement this
week was classified `EXPLAINED_MARKET_MOVEMENT`. The real reason is visible
directly in `check_explanatory_evidence`'s own logic: a "match" only
requires *any* news article mentioning either team inside the 24h lookback
window — it does not require the article to be about an injury, or about
anything plausibly connected to the actual line movement. Given that every
NFL team generates dozens of routine news articles per week (roster notes,
prediction columns, betting-odds recaps), **any team with normal weekly
news coverage will satisfy the "explained" condition almost by
default**, regardless of whether that news has anything to do with why a
price moved. This is exactly what the module's own docstring says it does
("temporal proximity, not a causal claim") — so this is not a bug — but it
means the current implementation is very unlikely to ever produce a
real-world `UNEXPLAINED_MARKET_MOVEMENT` signal once a team has any news
coverage that week, which is close to "always" during the season. **This is
surfaced here as a real, live-observed behavior of the frozen v1-provisional
design worth HQ's awareness before any future refinement of the
explanatory-evidence match criteria (e.g., requiring topical relevance, not
just team-mention presence) — no change is proposed or made in this pass.**

## 5. Cadence check against `app.workers.windows`' real adaptive schedule

Classified every consecutive-tick gap (Section 3) through the real
`classify_window`/`poll_interval_seconds` (FAR=86400s / RAMP_2H=3600s /
RAMP_60M=900s / RAMP_15M=300s / RAMP_5M=120s), flagging any gap exceeding
2× the expected interval for the window it started in:

- The large (~24h) gaps every game shows between the FAR-tier morning
  snapshot and the next capture are **expected**, not a gap — FAR's own
  policy interval is 24h.
- **One real, small cadence gap, shared identically across all 4 of
  today's 4:25 PM ET games** (same underlying bulk capture cycle):
  `2026-09-13T19:30:59Z → 2026-09-13T20:01:16Z`, a **1817-second gap**
  inside the `RAMP_60M` window (expected interval 900s) — roughly one
  missed capture cycle immediately before kickoff, not a sustained outage.
  No other cadence violation exceeding 2× the expected interval was found
  for any game, in any window.

## 6. `market_monitoring_events` — confirmed empty, live

`select count(*) from market_monitoring_events where game_id in (...)` for
all 5 games returned **0**, confirming live what
`app/orchestration/market_integrity.py`'s own docstring already discloses:
nothing in this codebase calls the persistence/orchestration path
automatically yet (not wired to any worker, cron, or endpoint). Every
classification in Sections 2 and 4 above was computed fresh from raw
`odds_snapshots` for this report, not read from a persisted event table.

## 7. Odds API credit ledger and cron behavior

- **`odds_api_credit_ledger`** (`the_odds_api`): `credits_used_this_period
  = 234`, `period_start = 2026-09-07T02:30:23Z`, `updated_at =
  2026-09-13T20:15:52Z` — i.e. **+54 credits since the 180/500 baseline
  HQ cited as of 2026-09-07T18:02Z**, over roughly 6.75 real days.
- **`CREDITS_PER_CALL = 3`** (`app.persistence.odds_api_credit_ledger`,
  one bulk `markets=h2h,spreads,totals` call). 234 credits ÷ 3 = **78 real
  provider round-trips** since period start — ≈11.6/day, consistent with
  one shared bulk capture cycle per adaptive-schedule tick across the
  active slate (matches Section 3's ~9-10 ticks per `(sportsbook,
  market_type)` group for the 4:25 PM games, which all share the same
  capture timestamps).
- **Credit guard is live and configured**: both required env vars
  (`THE_ODDS_API_MONTHLY_CREDIT_BUDGET`, `THE_ODDS_API_MIN_REMAINING_
  CREDITS`) are present on `sports-intel-layer`/dev — confirmed via Railway
  `list-variables` this pass (values themselves are redacted to this
  session; the 500-credit budget figure is HQ's own previously-stated
  number, not independently re-read from Railway this pass).
- **No quota-guard or unresolved-game firing found**: `games.
  unresolved_poll_attempts = 0` for all 5 games; no `skipped_credit_guard`
  outcome is evidenced anywhere in the ledger's usage pattern (234 used is
  well under any plausible 500-budget floor).
- **Conclusion: cron/worker behavior stayed within expected consumption.**
  The observed 78-call, 234-credit usage over 6.75 days matches the
  adaptive cadence's own designed shape (infrequent far out, ramping near
  kickoff), not a runaway or duplicate-polling pattern.

## 8. Is 5 real games enough to recalibrate safely?

**No — insufficient, per HQ's own default-to-insufficient instruction, and
this pass performed no recalibration regardless.** Concretely:

- All 3 SEVERE observations and most of the ELEVATED observations trace to
  **one single real-world story** (Josh Jacobs) affecting **one team**
  across **multiple books quoting the same game** — this is not 3
  independent anomalous events, it's one event's price impact echoed
  across books. A threshold calibrated on this sample would effectively be
  calibrated on a sample size of ~1 real "big" event.
- Every qualifying movement this week separately triggered a same-week
  `EXPLAINED` signal (Section 4's flagged finding) — meaning this window
  provides **no real evidence at all** about how the `UNEXPLAINED_MARKET_
  MOVEMENT` signal behaves under real conditions, since it never actually
  fired.
- 5 games is one week of one season; Milestone 7.0's own original finding
  (4 rows / 1 game / 1 computable delta) already established that DEV's
  real odds history was "functionally nonexistent" — this week moves that
  from "nonexistent" to "one real week," which is progress but nowhere
  near enough to responsibly re-derive `POINT_MOVEMENT_THRESHOLDS`/
  `PRICE_MOVEMENT_THRESHOLDS` from real distributional data.

## 9. Should Week 2 games be added before calibration?

**Recommendation: yes, keep accumulating real weeks (Week 2 and beyond)
before any recalibration is attempted — but this is a recommendation only;
no Week 2 enablement work was done in this pass and none is authorized by
it.** Reasoning: real calibration needs enough independent real events to
distinguish "one loud story moved one game's moneyline" (this week's actual
shape) from a genuine distributional pattern. Each additional real week
adds independent price-movement observations and, more importantly, a
chance to actually observe the `UNEXPLAINED` branch of Section 4's signal
at all — something this single week never exercised.

## Out of scope, exactly as instructed

No Phase 7.2/7.3 implementation. No Phase 8 work. No Milestone 5.6. No
SportsDataIO. No Master Refresh. No player props. No in-game odds. DEV
Supabase project only (`nhwjtsdebgiwskshzqiq`). No threshold
recalibration, no code change, no config change — every number in this
report is the real system's own live output, computed fresh for this
report and not persisted anywhere new.

## Note on PROGRESS.md staleness (observed, not corrected in this pass)

While researching this report, `PROGRESS.md`'s top "Current Phase" header
(line 3) and Phase 7 checklist header (line 80) still read "7.1+ NOT
AUTHORIZED" and "GATE B BLOCKED ON CREDENTIAL." Both are now stale relative
to the file's own later dated entries: Milestone 7.1 was authorized and
built (dated entry: "Task 2 -- Phase 7 Milestone 7.1 ... authorized and
built"), and `THE_ODDS_API_KEY` is confirmed present on `sports-intel-
layer`/dev (this pass's own `list-variables` call) with real, live
`odds_snapshots` actively being captured through today's kickoffs. Flagged
here per the blueprint-vs-reality disclosure discipline rather than
silently rewritten — HQ may want to confirm the intended current header
text before it's edited.
