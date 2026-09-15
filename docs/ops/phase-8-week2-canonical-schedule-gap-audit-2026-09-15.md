# Week 2 Canonical Schedule Gap — Audit

**Date:** 2026-09-15
**Directive:** MANSA HQ — "WEEK 2 CANONICAL SCHEDULE GAP AUDIT"
**Type:** AUDIT ONLY — zero provider calls, zero schedule rows written, no recommendation cycle run
**Root cause:** Master Refresh, the only canonical schedule ingestion path, is **deliberately disabled by a kill-switch env var pending authorization**. It has never run. Every real `games` row in dev was manually seeded.

---

## 1. Root cause

The `cron-master-refresh` service in dev crashes on every scheduled tick. Its
latest run (`548ae973`, 2026-09-15 06:01:51 UTC) logs:

```
cron_dispatch starting target=master-refresh-DISABLED-pending-authorization
cron_dispatch failed target=master-refresh-DISABLED-pending-authorization
  error=unknown CRON_DISPATCH_TARGET='master-refresh-DISABLED-pending-authorization';
  expected one of ['adaptive-weighting','master-refresh','postgame-grading','recommendation-worker']
```

`CRON_DISPATCH_TARGET` was deliberately set to a sentinel value —
`master-refresh-DISABLED-pending-authorization` — which is not a valid target, so
the dispatcher refuses it and exits non-zero. This is an intentional human kill
switch (Master Refresh spends paid SportsDataIO calls), not a bug. It simply
expresses itself as a daily CRASHED deployment rather than a clean no-op.

The full chain:

1. Master Refresh is the **only** path that creates canonical `games` rows from a
   real provider Schedule (`app.master_refresh.run` →
   `app.persistence.schedule.persist_schedule_entries`).
2. It is disabled, so it has never run — **`master_refresh_runs` is empty (0 rows)**.
3. Therefore no `games` row was ever created by the real Schedule path. Confirmed
   directly: **all 19 real games are `manual_seed = true`.**
4. Week 2 was never manually seeded, and the automated path that would have created
   it is off.
5. Even if it ran, `WINDOW_DAYS = 7` means it persists only
   `[today, today + 7)` — it was never going to bulk-backfill past or future weeks.

The service is also deployed from a stale branch (`claude/new-session-fqsad5`, not
`dev`) — a secondary drift worth noting but not the cause.

---

## 2. Exact Week 2 canonical coverage in dev

**Zero. Weeks 2, 3 and 4 do not exist at all.**

| week | games | kickoff range | status | manual_seed |
|---|---|---|---|---|
| (null, legacy fixtures) | 4 | 2026-08-04 → 08-16 | final/live/scheduled | false |
| 1 | **16** | 2026-09-10 → 09-15 | live/scheduled | **true** |
| **2 (Sep 17–21)** | **0** | — | — | — |
| 3, 4 | **0** | — | — | — |
| 5 | **3** | 2026-10-11 20:25 | scheduled | **true** |

Provider identity mappings on those rows: `balldontlie` 16 (week 1),
`mysportsfeeds` 16 (week 1), `the_odds_api` 12 (weeks 1 and 5).

**Related gap, same root cause:** Week 1's games are still `live`/`scheduled`, never
`final` — only 1 game in the entire database has `status='final'`. So Week 1 has no
gradeable outcomes either, independent of the Week 2 question.

---

## 3. Available existing data that could recover Week 2

**None.** Every candidate source was checked:

| Source | Contents | Can recover Week 2? |
|---|---|---|
| Adapter cache (`CachingAdapter`, `_SCHEDULE_TTL_SECONDS = 86400`) | backed by **`InMemoryCacheBackend()`** — process-local, dies with the process | **No** — nothing is persisted anywhere |
| `game_events.raw_payload` | 20 MSF postgame captures across 16 games | **No** — Week 1 only, postgame stats, no schedule |
| `news_article_history` | news articles | No |
| `daily_game_intelligence` | 17 rows, keyed to existing games | No |
| `game_provider_ids` | mappings for already-existing games only | No |
| `odds_snapshots` | 1,258 rows, all attached to 6 existing games; **0 orphans** | No |

There is no persisted raw schedule payload anywhere in the system. The season
schedule is fetched, filtered to a 7-day window, and only the window is persisted —
the unfiltered response is never stored.

**Team identity is NOT a blocker:** all **32/32** teams exist with **32/32**
`sportsdataio` provider mappings. Whenever a Week 2 schedule is ingested, its teams
will resolve. (`the_odds_api` team mappings are 17/32 — relevant later for odds
linking, not for schedule ingestion.)

---

## 4. Would the missing schedule prevent Odds Worker observations attaching?

**Yes, completely.** `app.workers.odds_worker` derives its poll set from
`list_games_in_window(...)` over the `games` table, then filters to `due_games`. A
game with no `games` row is never considered, never polled, and no odds can attach
to it — `odds_snapshots.game_id` references `games(id)`, and dev currently has **0
orphan odds rows**, confirming odds only ever exist against an existing game row.

This is exactly why the three Week 5 games carry zero odds despite existing: they are
outside the poll window, not missing identity.

So the ordering is strict: **canonical games must exist before any odds can be
observed, and odds must exist before any candidate can be generated.**

---

## 5. Is a provider call actually required?

**Yes.** There is no persisted artifact from which Week 2 can be reconstructed, and
the directive rightly forbids inventing matchups or hardcoding the schedule. The only
legitimate source of canonical Week 2 games is a real Schedule call.

### Smallest authorized call

**Re-enable the existing Master Refresh path** — no new code, no new integration:

- Set `CRON_DISPATCH_TARGET` back to `master-refresh` on `cron-master-refresh` (dev),
  or invoke the existing endpoint `POST /v1/internal/master-refresh/run` on
  `sports-intel-layer` directly with the internal token.
- Provider cost: **1 SportsDataIO Schedule call** (full season, then 24h-cached),
  plus up to ~32 SportsDataIO roster calls — one per team in the slate. Roster
  fetches are **non-blocking**: a roster failure never blocks schedule persistence.
- **The timing is currently favourable.** `WINDOW_DAYS = 7` and today is 2026-09-15,
  so the window is `[Sep 15, Sep 22)` — which covers **Week 2 (Sep 17–21) exactly**.
  A run today ingests Week 2 canonically. That alignment does not persist: run it
  after Sep 22 and Week 2 falls out of the window permanently.

No smaller path exists today — there is no schedule-only endpoint, and the roster
step is bundled into the same orchestration.

---

## 6. Exact next step to one legitimate pre-kickoff calibration prediction

Each step is separately authorizable; none is taken in this pass.

1. **Re-enable Master Refresh and run it (today, while the window covers Week 2).**
   → ~1 schedule + ≤32 roster SportsDataIO calls. Expected result: 16 canonical Week 2
   `games` rows with `manual_seed = false`, real `game_provider_ids`, real
   `scheduled_start`.
2. **Let the Odds Worker poll a Week 2 game.** With canonical rows present, the game
   enters `due_games` on its kickoff-proximity cadence and odds attach. → paid Odds
   API call, credit-ledger guarded.
3. **Run one recommendation cycle before kickoff** (~30 LLM calls for a fully-priced
   game; fewer if scoped). This produces the frozen `modeled_probability` with
   `predicted_at < scheduled_start` — satisfying the calibration eligibility contract.
4. **Wait for the game to finish.** Not skippable; the waiting is what makes the
   observation legitimate.
5. **Postgame ingestion must set the game `final` with scores.** Note the Week 1
   evidence above: games are currently stuck at `live`/`scheduled`, so this step needs
   verification — it is a real, separate risk, not an assumption.
6. **Grade it** with the existing postgame grading worker, then read the ledger back
   and confirm one `SettledPrediction` with `calibration_exclusion_reason is None`.

**Critical-path blocker today: step 1.** Everything downstream already exists in code
and needs no further development.

---

## 7. Findings for follow-up (not acted on)

- `cron-master-refresh` is deployed from stale branch `claude/new-session-fqsad5`
  rather than `dev`. Several other cron services share this drift
  (`cron-postgame-grading`, `cron-recommendation-worker`, `cron-adaptive-weighting`).
- The disabled-cron failure mode is a daily CRASHED deployment. A clean "disabled"
  no-op would be quieter and would not look like a real failure in dashboards.
- Week 1 games never reached `final` status — postgame ingestion appears not to have
  completed for them, which independently blocks grading even for games that already
  have odds and could otherwise be graded.
