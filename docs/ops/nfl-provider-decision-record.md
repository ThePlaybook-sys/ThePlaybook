# MANSA NFL Provider Decision Record

**Living document — updated as each provider diagnostic pass closes.
Not a build spec: no provider migration has been made or authorized as
of the most recent entry below. SportsDataIO remains the production
provider unchanged throughout everything on this page.**

Source reports, in order:
1. `docs/ops/nfl-provider-bakeoff-2026-09-03.md` — BALLDONTLIE vs
   API-SPORTS vs the SportsDataIO benchmark.
2. `docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md` —
   MySportsFeeds against the gaps the first bake-off left open.

---

## Current working hypothesis (2026-09-03, NOT YET CONFIRMED)

**MySportsFeeds Live, with a 10-minute delay, is the current preferred
production-cost hypothesis for whatever slice of MANSA's NFL data
MySportsFeeds ends up covering** (current-season team stats and
lineups, per the 2026-09-03 gap test) — **not** the Near-Realtime tier
Mac's trial subscription is currently on.

**Reasoning:**
- Team stats and lineup/depth-chart data do not need sub-minute
  freshness the way an in-play odds line does.
- Normalized provider responses get persisted in Postgres and cached in
  Redis (Volume 2's own already-established architecture) — MANSA reads
  its own cache/DB, not the provider, on every user-facing request.
- Provider calls are shared centrally across every subscriber via the
  existing worker/cron-dispatch pattern, never repeated per-user — so
  the real cost driver is polling cadence, not concurrent user count.
- Paying for freshness MANSA's own product doesn't materially use (no
  category identified so far needs sub-10-minute team-stat or lineup
  data) is waste, not safety margin.

**This hypothesis is explicitly NOT confirmed** — see the gate below.
Until it clears, it is a cost *direction* to plan around, not a
decision to act on. No subscription has been downgraded, upgraded, or
changed as a result of recording it here.

---

## GATE: MySportsFeeds 2026 Live-Game Validation

**STATUS: 🔴 BLOCKED — PENDING THE FIRST COMPLETED 2026 NFL
REGULAR-SEASON GAME.**

The 2026 NFL regular season opens 2026-09-09 (Seahawks host the
Patriots, Lumen Field, kickoff 8:20 PM ET / 2026-09-10T00:20:00Z per the
schedule data both prior diagnostic passes already pulled) — the
earliest a completed 2026 regular-season game can exist is late that
night / early 2026-09-10. **This gate cannot open before then**, and
should be treated as blocked regardless of how much other MANSA work
happens in the meantime.

### Purpose

Validate the MySportsFeeds capabilities the 2026-09-03 gap test could
not resolve, because no playable or played 2026 game existed at test
time — every play-by-play/box-score call that pass made returned a
clean `204 No Content` against a scheduled-but-unplayed game, which
proved the endpoints exist and behave sensibly pre-kickoff but proved
nothing about real in-game or post-game data quality.

### When the gate opens: what to run

A small, controlled, **DEV-only** validation against one completed 2026
NFL regular-season game, following the same "temporary probe, dev-only
startup hook + `logger.warning` retrieval, then full revert" discipline
both prior passes established (this workspace's own egress policy still
blocks direct HTTPS to `api.mysportsfeeds.com` and to this project's own
Railway domains — that has not changed and should be re-confirmed, not
assumed, before reusing the pattern).

Validate:
1. **Play-by-play availability** — does `/games/{id}/playbyplay.json`
   now return real content (not `204`) for a completed game?
2. **Play-by-play completeness and granularity** — every play, or a
   subset (scoring plays only, the way API-SPORTS's `/games/events`
   turned out to be)? Down/distance/yard-line detail present?
3. **Detailed box-score quality** — field completeness, null patterns,
   whether it matches or exceeds SportsDataIO's own `TeamGameStats`
   granularity (red zone, possession time, 3rd/4th-down efficiency,
   etc. — the bar API-SPORTS's `/games/statistics/teams` already met in
   the first bake-off).
4. **Final-score/status/correction semantics** — does `playedStatus`
   transition cleanly (`UNPLAYED` → `LIVE`/`IN_PROGRESS` →
   `COMPLETED`/`FINAL`, exact vocabulary TBD)? Does `latest_updates`
   (confirmed rich in the prior pass, 120 named sub-feeds) show a real,
   non-null `lastUpdatedOn` once the game has actually been played and
   graded? Any evidence of a post-game correction (a stat revised after
   initial posting)?
5. **Stable team/player/game identifiers** — do the same numeric IDs
   observed in the pre-game lineup response (e.g., team id 79 = SEA)
   still resolve consistently in the post-game box score/PBP for the
   same game?
6. **Timestamps and freshness** — compare `lastUpdatedOn` against real
   wall-clock game events, if the live-freshness test below is run
   during the game itself.
7. **Compatibility with MANSA's canonical models** — confirm (or
   revise) the 2026-09-03 gap test's finding that `DataCategory` has no
   category yet for play-by-play, lineups, or box-score-level detail;
   note whatever new category/model shape a real payload implies, as a
   proposal for Mac, not a change made unilaterally.
8. **Whether any material SportsDataIO capability remains uncovered**
   after seeing real MySportsFeeds game data — the honest answer may
   still be "yes, X" and that's a valid outcome.

**Also perform a live-game freshness test if at all possible** —
compare MySportsFeeds' actual data-arrival latency during a real,
in-progress game against what the cheaper 10-minute-delay tier's own
documented SLA would have provided, to determine whether MANSA
materially needs Near-Realtime or whether the working cost hypothesis
above holds. If the trial has already lapsed or is Near-Realtime-only,
say so plainly rather than fabricating a delayed-tier comparison — this
may itself require a small, explicitly-authorized second trial/tier
change, which is a real cost/product decision for Mac, not something to
assume permission for here.

### Do NOT, at gate-open time or during validation:
- Migrate providers.
- Change any subscription or tier (including reverting Near-Realtime to
  a delayed tier based on this gate's own findings — report the
  recommendation, let Mac decide and act on the subscription).
- Touch staging or production.
- Unfreeze `cron-odds-worker` or any other frozen/unrelated cron work.
- Spend SportsDataIO's one reserved trial call.
- Leave the diagnostic probe in the codebase afterward — revert it, per
  the established discipline, once the report is written.

### Closing the gate

Update this record's "Current working hypothesis" section above with
the real result (confirmed / revised / rejected, with reasoning), add a
dated entry to `PROGRESS.md` following the same convention as the two
entries already there for this provider work, and produce a dated
report file (`docs/ops/nfl-provider-live-game-validation-<date>.md`)
following the same structure as the two prior reports. Only then does
this gate change from 🔴 BLOCKED to 🟢 CLEARED (or ⚠️ CLEARED WITH
CAVEATS, if some of the eight validation items above still can't be
fully resolved from one game).

---

## Provider-role summary as of 2026-09-03 (carried forward from both
prior reports — see them for full detail and evidence)

| Role | Current candidate | Confidence |
|---|---|---|
| Current-season schedules, rosters, injuries, player/advanced stats | BALLDONTLIE | Confirmed live, real data, both bake-off passes |
| Current-season team stats | MySportsFeeds | Confirmed live, real schema; per-game granularity (`team_gamelogs`) still unresolved |
| Lineups | MySportsFeeds | Confirmed live, real pre-game depth-chart data |
| Play-by-play | **Unresolved — this gate exists to resolve it** | Endpoint exists (MySportsFeeds), coarse alternative exists (API-SPORTS `/games/events`), neither confirmed sufficient |
| Box scores / game detail | **Unresolved — this gate exists to resolve it** | Same as above |
| Historical/backtest depth (Time Machine) | BALLDONTLIE (current season back at least 1 year confirmed); API-SPORTS (2022–2024 only); MySportsFeeds prior-season game listings 403'd on this plan | Genuinely mixed, no single clean answer yet |
