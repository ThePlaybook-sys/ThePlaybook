# MANSA News Cadence Architecture Audit (2026-09-04)

**Planning/audit only. No code changed, no News Worker rewrite, no
production schedule locked.** HQ directed this audit after the
2026-09-03 GNews Essential validation flagged the News Worker's current
design (up to 32 independent team queries every 15 minutes, no
stop-at-kickoff — Volume 2 §8, `app/workers/news_worker.py`) as **not
an accepted production requirement**, only the design this project
happened to build first. This document proposes a more efficient
centralized/adaptive strategy and recalculates GNews Essential's real
capacity fit against it — it does not implement anything.

---

## The problem with the current design, restated precisely

`news_worker.py`'s own confirmed architecture: flat 900-second (15-min)
polling, one call per due team, up to 32 teams, no ramp tiers, **no
stop-at-kickoff** (a deliberate departure from Weather/Odds/Player
Props, since a team's news relevance doesn't end at its own kickoff).
Worst-case — and, in-season, close to typical-case, since most/all 32
teams have a game inside the 7-day candidate window at once — volume is
**32 × 96 cycles/day = up to 3,072 calls/day**. This was a correct
derivation of what the *existing* design produces; it was never a
requirement that MANSA's news coverage has to cost that much.

## Redesign principle

**Query breadth over query count, classify after ingestion, escalate
to targeted queries only when justified.** Concretely, four changes,
addressed one at a time below against HQ's own named techniques:

### 1. Broader NFL queries instead of 32 independent team queries

Replace the 32 per-team `"{team} NFL"` queries with a small, fixed set
of broad, high-signal category queries covering the whole league at
once — the same category shape the 2026-09-03 GNews validation already
tested and found effective: general league activity, injuries, trades,
suspensions, roster/depth-chart, coaching. **This is the single
largest volume reduction** — it converts the fetch cost from *O(number
of teams)* to *O(number of categories)*, independent of how many teams
are actually in-season/active. Six categories vs. 32 teams is
already a >5x reduction before any cadence change at all.

### 2. Entity/team classification after ingestion

A broad query's results aren't team-attributed the way a team-scoped
query's results are (`related_teams=[team]` today, per
`NewsAPINewsAdapter`'s existing contract). Closing that gap is
application code, not a provider call: classify each ingested article
against the already-existing `teams`/`players` tables (name/alias
matching against title+description, the same "raw fact →
deterministic feature" principle Volume 2 §1.1 already establishes for
every other category) to determine which team(s), if any, an article
is actually about, before it's written anywhere. An article matching no
resolvable team is handled the same way News Worker already handles an
unscoped/unresolved result today (excluded from game-keyed
persistence, per the worker's own existing "true league-wide news is
out of scope for this worker's game-keyed target" finding) — this
redesign doesn't change that boundary, it changes how many provider
calls it takes to reach it.

### 3. Deduplication

Already partially solved and should stay solved the same way: GNews's
own single-call de-duplication tested clean (0 duplicate URLs within a
call, 2026-09-03 validation) and `news_worker.py` already de-duplicates
by URL per game (`_dedupe_by_url`) before writing. Broader queries make
*cross-query* duplication more likely (the same trade story could now
surface under both a "trade" query and a "roster" query), so the
existing URL-based dedup step becomes more valuable under this
redesign, not less — no new mechanism needed, just confirmation it
still runs across the now-broader result set before persistence.

### 4. Caching

No change needed to the mechanism — `CachingAdapter`/Redis, already
used with `ttl_seconds` matching the poll interval, continues to apply
under whatever interval the adaptive cadence below actually lands on.
Broader queries with a longer baseline interval mean fewer total cache
entries churned per day, a secondary efficiency gain.

### 5. Query batching where the provider supports it — UNVERIFIED, not assumed

GNews's `/search` endpoint takes one `q` string per call; the
2026-09-03 validation did not test whether `q`'s own syntax supports
combining categories in one call (e.g. a boolean-OR-style query
merging "trade", "suspension", and "injury" into a single request).
**This is a real, additional potential reduction on top of the
category-breadth change above, but it is unverified** — flagged as a
follow-up check, not assumed to work, before it's relied on in any
volume estimate.

### 6. Adaptive/game-aware cadence — reuse, don't reinvent

**Recommend extending the existing shared window-classification
discipline (`app.workers.windows`) rather than building a fourth,
competing classifier.** This project already has two precedents for
exactly this shape: Odds/Player Props' kickoff-proximity ramp
(`classify_window`) and Injury Worker's day-of-week-anchored extension
(`classify_injury_window` — INFREQUENT / ACTIVE_WEEK / FINAL_RAMP /
INACTIVE_LIST / STOPPED). News's own real volatility pattern (bursty
around game days and specific league-calendar events, not uniformly
distributed through the week) is architecturally closer to Injury
Worker's shape than to a flat cadence — a News-specific extension
(e.g. `classify_news_window`) mirroring Injury Worker's own "extension
of the shared policy, not a competing one" discipline is the
recommended shape, without this document locking its exact tiers or
intervals.

### 7. Targeted team refresh only when justified

Keep a narrow, genuinely-scoped team query available as an escalation,
not the default: fired only when (a) a broad-category article's
classification confidence is too low to resolve which team it concerns
and a targeted follow-up would clarify, or (b) a specific team is
inside a currently-elevated high-value window (that team's own game
day, a confirmed major injury/trade story already touching that team).
This preserves precision exactly where it's actually needed instead of
paying for it uniformly across all 32 teams every cycle.

---

## Planning cadence assumption (NOT locked — a direction, per HQ's explicit instruction)

| Window | Trigger | Illustrative cadence (not authorized) |
|---|---|---|
| Baseline | Normal day, no game, no high-value event | ~2 refreshes/day (morning + late-afternoon), broad categories only |
| Game-day | Thu/Sun/Mon during season (the current slate's own active window) | Hourly-order cadence across the day's coverage window, broad categories |
| High-value window | Roster cuts, trade deadline, major injury periods, similar league-calendar events | Elevated cadence for the bounded duration of the window only, broad categories, escalating to targeted team queries where a specific team is directly implicated |
| Targeted team refresh | Escalation only (see §7 above) | Bounded number of teams, bounded duration, not a standing per-team cadence |

No exact numbers here are a commitment — they exist only to make the
volume recalculation below concrete enough to check against GNews's
real limits, per HQ's own "do not lock exact production schedules yet"
instruction.

---

## Recalculated GNews Essential request volume under this design

Using the illustrative cadence above, ~6 broad category queries per
refresh (the six named earlier), and a 3-game-day/week NFL slate
pattern:

- **Baseline days (4/week):** 2 refreshes × 6 queries = **12 calls/day**.
- **Game days (3/week):** an hourly-order cadence across a ~12-hour
  slate-coverage window ≈ 12 refreshes × 6 queries = **72 calls/day**.
- **High-value window (bounded, e.g. a roster-cut week or trade
  deadline day):** even at an aggressive 24/7 hourly cadence for that
  bounded period, 24 refreshes × 6 queries = **144 calls/day** — still
  well under quota, and only for the days the window is actually open.
- **Targeted team-refresh escalation:** a handful of extra calls
  (illustratively, ≤20-30/day even on a very active day) layered on
  top of any of the above.

**Weekly total under this design: roughly 4×12 + 3×72 ≈ 264 calls/week
in a normal week (≈38 calls/day average), rising to perhaps 150-200
calls on the single busiest combined game-day-plus-high-value-window
day** — nowhere close to GNews Essential's 1,000 req/day quota, and two
full orders of magnitude below the current design's ~3,072/day
worst-case.

## Does 1,000 req/day remain a real blocker?

**No — not under a properly designed architecture.** The original
2026-09-03 validation report's capacity concern was real and correctly
derived, but it was a property of the *32-team/15-minute-flat/no-ramp*
design specifically, not an inherent cost of covering NFL news well.
Under the redesign above, even a deliberately generous, non-optimized
estimate lands one to two orders of magnitude under Essential's quota,
with headroom to spare for the unverified query-batching improvement
in §5 above, which was not even counted toward this estimate.

**This does NOT resolve GNews as the selected provider.** The 2026-09-03
validation's other two items were about *freshness/full-content*, not
volume — and **CORRECTED 2026-09-04 (HQ clarification): that validation
actually ran on GNews's Free plan, not Essential**, so neither is a
"blocker" in the sense of a paid tier failing a test:
1. **Real-time entitlement on a commercially-usable tier remains
   UNTESTED** — the 12-hour-delay notice and 17-34-hour-old freshest
   articles observed were expected Free-plan behavior, not evidence
   Essential (or any paid tier) is broken.
2. **`expand=content` on a paid tier remains UNTESTED** — it had no
   effect on the Free plan, exactly as documented (paid-only feature).

**Both remain explicitly OPEN, now correctly understood as "never
tested" rather than "tested and failing"** — this cadence redesign does
not touch, test, or resolve either, and neither should be treated as
answered by a favorable volume recalculation. HQ's current decision
(2026-09-04): GNews remains MANSA's development provider; both items
above are now items 2-3 of the 6-item production/beta gate in
`docs/ops/news-provider-decision-record.md`, updated alongside this
audit to carry this forward.

---

## What this document does NOT do

- Does not rewrite `app.workers.news_worker` or any adapter.
- Does not lock any exact schedule, interval, or window boundary.
- Does not select or reject GNews (or any provider) — it answers only
  the capacity question, leaving the freshness/provisioning question
  open per HQ's explicit instruction.
- Does not change any cron schedule, subscription, or migration.

## Decisions HQ needs to make

1. Whether to authorize a News Worker redesign along these lines at
   all (broad-category-first, classify-after-ingestion, adaptive
   cadence reusing/extending `app.workers.windows`) as a real future
   milestone — not scheduled or authorized by this document.
2. Whether to verify GNews's `q`-syntax batching capability (§5) before
   or as part of that redesign.
3. Whether/when to resolve the still-open real-time-entitlement and
   `expand=content` questions (a direct GNews support inquiry, per the
   2026-09-03 validation report's own recommendation) — independent of
   this document, and still the actual gate on any GNews production
   decision.
4. Exact cadence tiers/intervals for baseline/game-day/high-value
   windows, and the precise definition of a "high-value window" trigger
   (roster-cut dates, trade-deadline date, and any others) — explicitly
   deferred, not decided here.
