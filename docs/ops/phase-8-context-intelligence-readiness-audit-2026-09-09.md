# Phase 8 Context Intelligence Readiness Audit (2026-09-09)

**Status: AUDIT ONLY. No implementation, no provider calls, no DB writes, no
schema changes, no worker activation.** HQ directive: "MANSA SPORTS
INTELLIGENCE — PHASE 8 CONTEXT INTELLIGENCE READINESS AUDIT." Produced by
tracing current repository source directly (migrations, application code,
prior docs/ops audits used only as corroborating evidence, re-verified
against current code rather than trusted blindly) plus four parallel
read-only research passes. This document is the durable record; the chat
STOP AND REPORT is the executive summary of the same findings.

---

## 1. Primary question

**"If MANSA were asked today to build a trustworthy historical context
package for one NFL player for one historical game, what exact evidence can
the existing system assemble, what can it only partially assemble, and what
is still unavailable?"**

### Can assemble today (for a game with real captured data)
- Game identity: opponent, home/away, scheduled kickoff, status.
- Static venue facts: venue_id, coordinates, roof/indoor-outdoor status,
  name/city/state — genuinely stable over time, so "historical" is close to
  moot for these (a venue's location doesn't change per-game).
- Real historical odds/line-movement for that specific game, **if**
  `odds_snapshots` rows were ever captured for it (real since Phase 7).
- Real historical weather for that specific game, **if** a real WeatherAPI
  observation was captured for it (real only since Weather Activation,
  2026-09-07 — games before that date have no real row).
- Team-level (not player-level) real historical news activity for that
  game's two teams, with real temporal correlation to real market-movement
  windows.
- Travel distance / timezone shift / international-game flag for the team
  playing that historical game — genuinely computable for an **arbitrary
  past** game, not just "the next game," because the underlying query
  (`find_previous_final_game`) takes an explicit `before` timestamp.
- The player's own canonical identity + provider ID, **if** the player is
  one of the 34 players activated in Phase 8.2 (2 teams, MySportsFeeds only).

### Can only partially assemble
- Team roster membership history: real, append-only, but insert-on-change
  only (no end date — "released" is not representable), 2 of 32 teams.
- Season-aggregate player performance: real data confirmed to exist at the
  MySportsFeeds source, and the schema now supports storing it
  (`season_id`-scoped rows), but **no persistence code currently writes it**
  — the capability exists at the source and in the schema, not in the
  pipeline connecting them.
- Rest days (day-count since last game): the raw fields needed to compute it
  deterministically already exist (`games.scheduled_start` per team, the
  same fields travel computation already uses) — but no code performs this
  computation; only a current-only, non-historical `daily_game_intelligence.rest`
  value exists today.
- Injuries: real, append-only historical schema exists
  (`injury_reports`), and persistence/worker code is complete, but (a) the
  one provider Context Intelligence's own "injuries" dimension is gated on
  (BALLDONTLIE) has an unresolved billing block, and (b) even once
  unblocked, no retrieval code was found that reads "the injury report as of
  a specific past kickoff time" — only a "most recent" reader exists.

### Still unavailable
- **Any actual per-game player statistical performance** (targets,
  receptions, receiving yards, touchdowns, snap counts) for any specific
  historical game. This is the single most important gap — MANSA's own
  Phase 8.4E closeout names it verbatim as "the gating dependency for all of
  it." Only 2 fixture-pattern rows exist system-wide; the MySportsFeeds
  `_gamelogs` family (the one credible source) is confirmed non-working and
  permanently closed per HQ.
- Whether the player was active/inactive for that specific historical game —
  lineup/depth-chart data is real but current-roster-only and never
  represents active/inactive status at all, by design.
- Historical injury status as of that game's kickoff specifically (distinct
  from the billing block above — the retrieval code itself doesn't exist).
- Teammate availability/dependency (e.g. "was the starting QB active") —
  entirely unimplemented; an exhaustive search found zero code anywhere
  expressing this concept, not even a stub.
- Opponent's real defensive performance / matchup rating for that game —
  schema-only tables (`matchup_scores`/`offensive_matchup_scores`/
  `defensive_matchup_scores`), zero application code reads or writes them,
  and the agents that would consume them are explicitly deferred/unbuilt.
- Game state/script (score differential, quarter, time remaining, pass/run
  environment) — a real append-only capture table exists but every typed
  column is always written `null`; only an opaque, unvalidated
  `raw_payload` blob is captured, and no worker currently calls the
  persistence function at all. Gated on the first real 2026 NFL game, which
  per repository evidence was hours away from kickoff as of this audit's
  system date.
- A genuine "closing line" (as opposed to "the last odds observation MANSA
  happened to capture") — architecturally, no such marker exists anywhere;
  this is disclosed directly in the relevant agent's own evidence output,
  not merely an oversight.
- Player-specific news alignment — `news_article_history` is team-linked
  only (`related_team_ids`), with no player identity column at all.

### The meta-finding that cuts across all of the above
Even for the dimensions that genuinely are real, historical-capable, and
well-built (weather/market/news/venue, via the Context Intelligence engine —
Section 4 below), **none of them currently reach Probability Modeling.**
`ProbabilityModelingAgent.build_evidence()` (Section 5) only ever sees the
fan-out committee's `AgentOutput`s, which are built from `AgentContext`
(current-only `daily_game_intelligence` for weather/injuries/rest, plus
real historical odds and real historical-capable travel). The separate,
richer Context Intelligence engine is fully built and already produces
`ProvenanceRef`-backed, honestly-scored, `insufficient_evidence`-safe
results for all four of its real dimensions — and is, by its own explicit
module docstring, **zero percent wired into the model.** Wiring it in is
named as a future pass that requires reopening Phase 4, deliberately
deferred by the HQ instruction that built it.

---

## 2. Context Readiness Matrix

`H?` = historical-capable, `P?` = persisted, `R?` = retrieval code exists,
`W?` = wired into Probability Modeling's `build_evidence()`.

| Dim | Dimension | Status | H? | P? | R? | W? | Primary source | Join key(s) | Exact gap |
|---|---|---|---|---|---|---|---|---|---|
| A | Player identity | PARTIAL | Partial | Yes (34 real rows) | Yes | **No** | `players`, `player_provider_ids` | player_id ↔ (provider_name, provider_player_id) | Real data exists (post-8.2) but `engine.py`/`unsupported.py` unconditionally stub `player_performance`/`roster_role` regardless — real data is never actually read downstream. BALLDONTLIE excluded from `player_provider_ids` check constraint. |
| B | Game/event identity | PARTIAL | Partial | Yes (current season) | Yes | Yes (via `games`) | `games`, `game_provider_ids` | game_id ↔ (provider_name, provider_game_id) | Real for current season (12 rows); prior-season/historical game discovery returns provider 403. `finalized_at`/`status='final'` mechanism real but had not yet processed a real completed game as of this audit. |
| C | Player game-level performance | UNAVAILABLE | No | No (2 fixture rows) | Yes (unused) | No | `player_stats` (game_id-scoped) | player_id + game_id | Zero real per-game rows exist anywhere. `_gamelogs` (MSF) confirmed closed. Gate A/B are the only remaining paths, both unexercised. |
| C′ | Player *season-aggregate* performance | PARTIAL | N/A (season-scoped) | Real at source, not in MANSA schema | No writer | No | MSF `player_stats_totals` (source only) | player_id + season_id | Real season data confirmed at the MSF source; schema now accepts `season_id`-scoped rows, but no code writes them into MANSA's own `player_stats`/`team_stats`. |
| D | Lineup/depth/role | UNAVAILABLE (historical); PARTIAL (current) | No | Yes (34 rows, 2 teams) | Yes | No | `roster_memberships`, `depth_chart_snapshots` (team-scoped) | player_id/team_id + captured_at | No end-dating (can't tell when someone left a roster); active/inactive is never represented at all, by design; only 2/32 teams; stub overrides in Context Intelligence never consume the real rows. |
| E | Injuries | UNAVAILABLE | Partial (schema only) | Yes (real table, currently empty of real rows) | Partial (only "latest," no "as-of-timestamp") | No | `injury_reports` (append-only) | game_id + captured_at | BALLDONTLIE billing entitlement unresolved (blocks the provider Context Intelligence gates this dimension on); even unblocked, no point-in-time-historical reader exists, only a "most recent" one. |
| F | Teammate availability/dependency | UNAVAILABLE | No | No | No | No | — none — | — | Entirely unimplemented. Zero code anywhere (ai-orchestrator or sports-intel-layer) expresses this concept, not even as a stub. |
| G | Weather | PARTIAL | Yes (Context Intelligence path only) | Yes (`weather_snapshots`, real since 2026-09-07) | Yes (two implementations) | **No** (real path); Yes but current-only (fan-out path) | `weather_snapshots` / `daily_game_intelligence.weather` | game_id (+ captured_at for the real historical path) | Two separate implementations: fan-out committee's is current-only and IS wired to the model; Context Intelligence's is real/historical-capable and is NOT wired. Real coverage begins only 2026-09-07 forward. |
| H | Venue/surface | PARTIAL (leans JOINED for static facts) | Yes (facts are time-stable) | Yes (`canonical_venues`, `games` venue fields) | Yes | No | `venues`, `games.venue_id/venue_lat/venue_long/venue_type/stadium` | game_id → venue_id | Real, persisted, retrievable venue identity/coordinates/roof status — but not model-wired. No dedicated "surface" (turf/grass) column was found anywhere; venue_type covers indoor/outdoor/dome status only. |
| I | Rest / travel | PARTIAL (travel real+wired; rest unavailable but derivable) | Travel: Yes. Rest: No | Travel: Yes (`games`). Rest: current-only only | Travel: Yes. Rest: No | Travel: **Yes**. Rest: No (current-only) | `games` (travel); `daily_game_intelligence.rest` (current rest) | team + scheduled_start | Travel is genuinely historically reconstructable and already wired to the model (`TravelFatigueAgent`). `consecutive_road_games` is a dataclass field that is never populated (no recent-games reader). Rest days has no computation code at all, though the exact fields needed already exist in `games` and are already being fetched by the adjacent travel path — a code gap, not a data gap. |
| J | Opponent/matchup | PARTIAL (identity real; ratings unavailable) | Identity: Yes. Ratings: No | Identity: Yes. Ratings: schema-only | Identity: Yes. Ratings: No | Identity: implicitly (via games); Ratings: No | `games.home_team/away_team` (identity); `matchup_scores`/`offensive_matchup_scores`/`defensive_matchup_scores` (ratings, unused) | game_id | Opponent identity is trivial/real. Matchup rating tables have zero reading or writing application code anywhere in the repo; the agents meant to consume them are explicitly deferred/unbuilt. Opponent defensive stats depend on `team_stats`, itself fixture-linked only. |
| K | Game state/script (PBP) | UNAVAILABLE | No | Schema-only, always-null typed columns | Yes (unwired) | No | `game_events` (raw-capture) | game_id + provider_event_id | Real append-only table exists but every typed column (`period`/`clock`/`score_home`/`score_away`/etc.) is always written `null`; only an opaque `raw_payload` is captured. No worker calls the persistence function. Gated on the first real completed 2026 NFL game. No pass/run-environment field exists anywhere in the schema. |
| L | Odds/market context | PARTIAL (leans JOINED for raw history) | Yes | Yes (`odds_snapshots`, real since Phase 7) | Yes | **Yes** | `odds_snapshots` | game_id + captured_at | Real historical pregame price/point observations and deterministic line-movement math are real, persisted, retrievable, and already wired into the model (`VegasLineAgent`/`ClosingLineMovementAgent`). But no confirmed "closing line" marker exists anywhere — the architecture explicitly, self-disclosedly, cannot distinguish "the market's actual close" from "the last observation MANSA happened to capture." |
| M | News context | PARTIAL | Yes (team-level only) | Yes (`news_article_history`, real, gnews-sourced) | Yes | No | `news_article_history` | team_id (via `related_team_ids`) — **no player_id column exists** | Real, historical, team-linked news activity with real temporal correlation to real market movement exists via Context Intelligence, but is not wired into the model, and has no player-level linkage at all — a player-specific news question cannot be answered even in principle without a new join concept. |

---

## 3. Current end-to-end data-flow map

For each dimension, the actual path that exists today, using HQ's own
`PROVIDER → NORMALIZED → PERSISTED → ...` notation:

- **Weather (Context Intelligence path)**: `WeatherAPI adapter → weather_worker.py → weather_snapshots (persisted, append-only) → context_intelligence/weather.py (retrieval + comparison) → NOT WIRED TO MODEL`.
- **Weather (fan-out committee path)**: `WeatherAPI adapter → weather_worker.py → daily_game_intelligence.weather (persisted, OVERWRITTEN EACH REFRESH, current-only) → app/agents/context.py → app/agents/weather.py → build_evidence() → MODEL`.
- **Injuries**: `SportsDataIO/BALLDONTLIE adapter → injury_worker.py/balldontlie_injury_worker.py → injury_reports (persisted, append-only, real schema) → PERSISTED, NO POINT-IN-TIME RETRIEVAL CODE FOUND` (only a "latest" reader feeds `daily_game_intelligence.injuries`, itself current-only and separately consumed by `app/agents/injury_intelligence.py` → `build_evidence()` → MODEL, but that is current data, never historical).
- **Lineup/depth/role**: `(no live roster provider ever invoked) → roster_ingestion.py (persistence code complete, real schema) → roster_memberships/depth_chart_snapshots (34 real rows, 2 teams, one manual DEV activation) → NOT WIRED TO context_intelligence (stub override) → NOT WIRED TO MODEL`.
- **Player performance (per-game)**: `(no working real source) → player_stats.py persistence code (complete, unused for real data) → player_stats (2 fixture rows only) → NO REAL DATA TO RETRIEVE`.
- **Player performance (season-aggregate)**: `MySportsFeeds player_stats_totals (real, confirmed live) → NO PERSISTENCE CODE WRITES THIS SHAPE → STOPS AT SOURCE, never reaches MANSA's own schema`.
- **Rest/travel**: `games.scheduled_start + venue fields (real, persisted) → app/features/travel.py + find_previous_final_game (real, historically-parametrizable retrieval code) → app/agents/context.py → app/agents/travel_fatigue.py → build_evidence() → MODEL` (travel only; rest days has no equivalent computation path and instead reads `daily_game_intelligence.rest`, current-only).
- **Odds/market**: `The Odds API adapter → odds_worker → odds_snapshots (persisted, append-only, real) → app/persistence/odds_snapshots.py (retrieval) → app/agents/context.py (odds_history/line_movement) → app/agents/vegas_line.py / closing_line_movement.py → build_evidence() → MODEL`. Separately: `odds_snapshots (same table) → context_intelligence/market.py (cross-game comparative framing) → NOT WIRED TO MODEL`.
- **News**: `GNews adapter → news_article_history (persisted, real, team-linked) → context_intelligence/news.py (retrieval + market-movement-proximity framing) → NOT WIRED TO MODEL`.
- **Venue**: `canonical_venues + games.venue_id/venue_lat/venue_long/venue_type (persisted, real, static) → context_intelligence/venue.py (retrieval + venue-identity comparison) → NOT WIRED TO MODEL`.
- **Opponent/matchup ratings**: `SCHEMA EXISTS (matchup_scores/offensive_matchup_scores/defensive_matchup_scores) → NO REAL DATA, NO WRITER, NO READER anywhere in application code`.
- **Game state/PBP**: `(provider shape unknown/unvalidated) → game_events.py persistence function (complete, shape-agnostic) → game_events table (schema real, always-null typed columns) → NO WORKER CALLS THIS FUNCTION AT ALL → gated on first real completed 2026 game`.

---

## 4. `build_evidence()` integration audit

`apps/ai-orchestrator/app/agents/probability_modeling.py:20-41` — the
**complete** method body, read directly and reproduced in full for the
record:

```python
def build_evidence(self, context: SequentialDecisionContext) -> dict:
    return {
        "candidate": {
            "candidate_key": candidate_key(context.candidate),
            "game_id": context.candidate.game_id,
            "sportsbook": context.candidate.sportsbook,
            "market_type": context.candidate.market_type,
            "selection": context.candidate.selection,
            "american_odds": context.candidate.american_odds,
            "point": context.candidate.point,
        },
        "upstream_findings": [output.model_dump(mode="json") for output in context.upstream_outputs],
        "participation": {
            "configured_agent_count": len(context.participation.configured_agents),
            "built_agent_count": len(context.participation.built_agents),
            "deferred_agents": sorted(context.participation.deferred_agents),
            "successful_agents": sorted(context.participation.successful_agents),
            "failed_agents": sorted(context.participation.failed_agents),
            "fan_out_status": context.participation.fan_out_status,
            "committee_completeness": context.participation.committee_completeness,
        },
    }
```

**What it consumes**: exactly three things — the candidate bet's own fields,
the fan-out committee's already-produced `AgentOutput`s
(`context.upstream_outputs`, dumped verbatim), and honest participation
metadata (which agents ran/failed/were deferred). **It performs zero I/O
itself** — no database call, no provider call, nothing. Every actual context
fact reaches it only via whatever the fan-out committee agents themselves
put into their own `build_evidence()` (weather.py/injury_intelligence.py/
rest_days.py/travel_fatigue.py/vegas_line.py/closing_line_movement.py, all
read earlier this pass, all sourced from `AgentContext` per Section 3 above).

**Which context dimensions currently enter modeling**: weather (current-only),
injuries (current-only), rest (current-only), travel (real, historical-
capable, already wired), odds/line-movement (real, historical-capable,
already wired). That is 5 of the 13 audited dimensions, and 2 of those 5
(travel, odds) are genuinely historical-safe; the other 3 (weather,
injuries, rest) are current-only regardless of what game_id is requested.

**Which exist elsewhere but are not wired in**: the four Context
Intelligence dimensions (weather — historical variant, market, news, venue)
— fully built, real, `ProvenanceRef`-backed, `insufficient_evidence`-safe,
explicitly documented with the exact one-line integration point
(`"contextual_performance": contextual_intelligence.to_json()`) named in
`app/context_intelligence/engine.py:14-29`, and explicitly, deliberately
NOT wired in this pass, per that same docstring's own citation of "HQ's
'Do NOT reopen Phase 4' instruction."

**Which do not exist at all**: player_performance (per-game), roster_role
(active/inactive), team_performance (real per-game/season team stats),
depth_lineup (historical), game_state_pbp — all six are explicit
`UNSUPPORTED_DIMENSIONS` stubs even within Context Intelligence itself
(`app/context_intelligence/unsupported.py:26-57`), never attempted as a
real query, "so no query is attempted against tables confirmed
fixture-only or zero-row would only risk surfacing fixture data as though
it were real" (module docstring, `unsupported.py:9-15`).

**Whether wiring new context requires reopening Phase 4**: yes, explicitly,
per the engine's own docstring. `build_evidence()` was **not modified** by
this audit — read-only throughout, per HQ's explicit instruction.

---

## 5. Gate A readiness — BALLDONTLIE `/nfl/v1/stats`

- **Adapter support**: none exists. `apps/sports-intel-layer/app/adapters/providers/balldontlie.py` contains only `BallDontLieInjuryAdapter` (`/nfl/v1/player_injuries`). No `PlayerStatsAdapter`/`/nfl/v1/stats` class exists anywhere in the repo.
- **Endpoint contract**: known only at a high level from a prior bake-off doc (`docs/ops/nfl-provider-bakeoff-2026-09-03.md`) — "~50 typed fields, correct nulls for non-applicable positions" — derived from the provider's own SDK source, not a captured real response sample. No BDL-specific single-call diagnostic for this exact endpoint exists in this repo.
- **Canonical persistence**: `player_stats` (game_id-scoped) + `persist_player_stats()` structurally fits a per-game stats response with zero new columns needed (the `stats jsonb` column is unconstrained). But `persist_player_stats()` hardcodes `provider_name="sportsdataio"`, and `player_provider_ids`'s CHECK constraint does not include `'balldontlie'` (only game/team provider-ID tables were widened for BDL, not player) — so **one small migration** (adding `'balldontlie'` to `player_provider_ids_provider_name_check`) plus a new adapter class would be needed before a real BDL response could be persisted end-to-end. No new table or new column is required.
- **Billing/config discoverability from repo alone**: **NO.** The "account invoice open/unpaid" fact is carried-forward prose from a prior session's own finding, not independently re-derivable from any committed file. `/nfl/v1/stats`'s specific tier (Free vs. paid) is not labeled anywhere in this repo, and `docs/ops/phase-8.4e-game-level-data-capability-resolution-2026-09-08.md` states this endpoint's live status is "honestly UNKNOWN-pending-billing" — it has not been re-tested since the billing issue emerged. The env var name is `BALLDONTLIE_API_KEY`; its value/state is never in the repo (correctly).
- **SUCCESS**: HTTP 200 with a non-empty `data` array carrying real per-game player stat fields for a real player/game (not all-null placeholders).
- **FAILURE**: HTTP 401/403 (matching the pattern already observed on the injuries endpoint under the same billing block), or any 4xx/5xx.
- **INCONCLUSIVE**: HTTP 200 with an empty `data` array, an unrecognized/unparseable shape, or a timeout/no-response.

## 6. Gate B readiness — MySportsFeeds `game_boxscore`

- **Adapter support**: `apps/sports-intel-layer/app/adapters/providers/mysportsfeeds.py` has roster and season-stats adapters only; no `game_lineup`/`game_boxscore`/`game_playbyplay` method exists anywhere in the repo today.
- **Known prior behavior** (from `docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`, quoted): `game_lineup` — "responded 200 with real, substantive content even for a game 7 days out" (succeeds today). `game_boxscore` — "responded 204 No Content for the same unplayed game." `game_playbyplay` — "responded 204 No Content" for an unplayed game. All three responses were the well-formed, entitled shape (204, not 400/403), consistent with "not played yet" rather than an access problem.
- **Canonical game ID ↔ MSF ID linkage**: `game_provider_ids` exists as a mechanism but was **not** extended for `mysportsfeeds` by the identity migration (`20260908150000_mysportsfeeds_provider_identity.sql` only widens `team_provider_ids`/`player_provider_ids`, not `game_provider_ids`) — the one real MSF game ID exercised to date (163541, NE@SEA) has no persisted mapping row found.
- **Identifying an eligible completed game without a provider call**: YES — `games.status` (real enum including `'final'`) and `games.finalized_at` (real, nullable, set once on first observed transition to final) are both already-persisted columns; a `SELECT status='final'` query needs no provider call. The postgame worker already establishes this exact detection pattern. The missing piece is only the MSF-side game-ID mapping named above.
- **Persistence for `game_boxscore`**: none exists. No `DataCategory`/normalized model fits box-score/play-level granularity today (existing models are roster/schedule/team-stat/player-stat shaped, all season- or roster-scoped, not boxscore-shaped). Minimal new work: an MSF `game_provider_ids` mapping row/mechanism, plus a boxscore-shaped persistence model (a per-player, per-team nested jsonb shape, analogous to the existing `player_stats.stats jsonb` pattern) — explicitly flagged in a prior gap-test doc as unresolved architecture, not solved by any pass to date.
- **Billing/config discoverability from repo alone**: **PARTIALLY.** MSF's entitlement is documented as currently active and broad (NFL, Commercial Near-Realtime, CORE+STATS+DETAILS, 14-day trial noted as time-boxed to roughly 2026-09-17) — evidenced by multiple real 200 responses across other MSF feeds — but the trial's exact live validity cannot be independently re-confirmed from repo state alone; it is carried-forward prose, not a machine-checkable value.
- **SUCCESS**: HTTP 200 with a non-empty boxscore payload carrying real per-player stat lines for a genuinely completed game.
- **FAILURE**: HTTP 4xx (entitlement/plan block) or 5xx.
- **INCONCLUSIVE**: HTTP 204 again on a genuinely completed game (would mean "played vs. not played" is not the actual gating logic, undermining the premise this whole gate rests on), or a 200 with an empty/malformed body.

---

## 7. Context Assembly Proof readiness

**NOT READY.**

The proof's own gating dependency — real, per-game player performance data
for a specific player across specific historical games — is confirmed
UNAVAILABLE, exactly as MANSA's own prior Phase 8.4E closeout already
concluded ("the gating dependency for all of it is the same one row").
Lineup/active-status, historical injury status, and teammate dependency are
each independently UNAVAILABLE as well, and even the dimensions that ARE
real and historical-capable (weather/market/news/venue) are not wired into
anything that would let a "context package" actually inform a
recommendation — they exist only as a standalone, unwired module today.

## 8. Minimum blockers, ranked by strategic importance

1. **Per-game player performance substrate** (the central blocker). Neither
   Gate A nor Gate B has been exercised; MSF `_gamelogs` is permanently
   closed. Nothing else in this audit matters for the proof's core claim
   until one of these two gates produces real per-game data.
2. **A real completed 2026 NFL game must exist at all.** Per
   `docs/ops/nfl-provider-decision-record.md`, the season opener (Seahawks
   host Patriots, kickoff 2026-09-10T00:20:00Z) was the first candidate —
   hours away from this audit's own stated system date/time. This is a
   time-based blocker that resolves on its own; Gate B specifically cannot
   even be attempted honestly until it clears.
3. **Historical, point-in-time lineup/injury retrieval code.** Even with
   real data, no code was found that answers "what was true as of this
   past kickoff" for either dimension — only "current"/"latest" readers
   exist. This is a code gap layered on top of the data gap.
4. **BALLDONTLIE billing resolution**, specifically for the injuries
   entitlement Context Intelligence's "injuries" dimension is gated on, and
   separately for whatever tier `/nfl/v1/stats` requires (unknown,
   unverifiable from the repo).
5. **Context Intelligence → Probability Modeling wiring** (a
   separately-authorized Phase 4 reopening). Lower urgency than items 1-4 if
   the near-term goal is "assemble and show a context package"; higher
   urgency if the goal is "have context actually inform a recommendation."
6. **Player-provider identity coverage.** Cheap relative to the above — one
   CHECK-constraint value (`player_provider_ids` needs `'balldontlie'`
   added) plus broader roster/depth-chart activation beyond the current 2
   of 32 teams.
7. **Teammate-dependency and opponent-matchup-rating capability.**
   Currently zero-built. Lowest priority — arguably out of scope for a
   single-player historical-context proof in the first place.

## 9. Architectural risks discovered

Documented per HQ's instruction — **not fixed here**:

- **Current lineup/roster treated as historical lineup.** `roster_memberships`
  has no end-date and `daily_game_intelligence` retains nothing after being
  overwritten; a future implementation that naively reads "current roster"
  for a past game's active-status question would silently be wrong, with
  nothing in the schema stopping it.
- **Season aggregate stats treated as game stats.** The schema's own
  `game_id`/`season_id` nullable-either-or design on `player_stats`/
  `team_stats` makes both shapes structurally interchangeable at the
  storage layer — nothing prevents a future writer from putting a
  season-aggregate row where a caller expects a single-game row without an
  explicit, disciplined check on which key is populated.
- **Present injury status treated as historical injury status.** The only
  injury reader found returns "most recent," not "as of a given past
  timestamp" — a naive future caller reconstructing a historical context
  package could easily present today's injury status as if it were true on
  the historical game's date.
- **Venue defaults treated as evidence.** Currently low risk — the codebase
  already disciplines this correctly (`context_intelligence/venue.py`:
  "SoFi's unresolved roof type stays `None`, never invented"). Documented
  as a risk because this discipline is a convention future code must
  continue honoring, not a structural guarantee.
- **Missing weather silently filled.** Currently low risk — both weather
  implementations already degrade to `None`/`insufficient_evidence` rather
  than fabricate. Same caveat: convention, not a structural guarantee. A
  future path that reads `daily_game_intelligence.weather` directly
  (bypassing the disciplined agent/engine layers) could reintroduce this.
- **Player identity joins crossing providers incorrectly.** `player_provider_ids`
  is uniquely keyed per (provider_name, provider_player_id) and
  (player_id, provider_name), which is sound — but if BALLDONTLIE identity
  is added later via anything looser than a verified provider ID (e.g.
  name/team matching), two different real players with common names could
  merge under one canonical identity.
- **Duplicate append-only rows affecting historical truth.** `injury_reports`/
  `weather_snapshots`/`depth_chart_snapshots`/`game_events` all deliberately
  carry no uniqueness constraint on their natural key. A future "nearest
  observation before kickoff" query, if written carelessly, could pick an
  arbitrary near-duplicate row, or a sample-size/confidence computation
  (Context Intelligence's `scoring.py`) could double-count duplicates if
  ever pointed at these tables without dedup discipline.
- **Recommendation-time odds confused with game-close odds.** Already
  explicitly guarded in code (`ClosingLineMovementAgent`'s own docstring:
  every feature is named `latest_*`, never `closing_*`) — documented here
  as a risk because any FUTURE feature or report that casually calls
  captured odds data "the closing line" without carrying this same
  discipline forward would reintroduce exactly the confusion this
  architecture went out of its way to prevent.
- **Context evidence inserted into probability models without provenance.**
  Not a live risk today (Context Intelligence isn't wired in at all), but
  is exactly the risk the eventual wiring pass must guard against. The
  `ProvenanceRef` shape already built (table/source/row_count/earliest_at/
  latest_at) is good precedent, but nothing enforces its use once wiring
  actually happens — that must be part of that future pass's explicit
  acceptance criteria, not assumed.
- **Weak samples presented as high-confidence evidence.** Already well
  guarded today (`INSUFFICIENT_SAMPLE_FLOOR`, mandatory
  `insufficient_evidence`/`confidence=None` semantics baked into
  `ContextualDimensionResult`) — documented as a risk only insofar as this
  discipline is only as strong as future code's continued respect for it.

## 10. Contradictions with existing MANSA documentation or assumptions

- `app/context_intelligence/unsupported.py`'s reason strings for
  `player_performance` ("players/player_provider_ids are fixture/seed-only")
  and `roster_role` ("No real roster_memberships data exists") are now
  **stale/inaccurate as prose** — Phase 8.2 (2026-09-08) activated 34 real
  player/roster rows, one day before those reason strings' own module
  docstring date. The **functional behavior is unaffected** (the stub is
  unconditional regardless of real row counts, so the practical
  UNAVAILABLE conclusion for downstream use is still correct) — but the
  stated *reason* is no longer true. This is a minor, low-urgency
  documentation-accuracy gap worth a future correction pass, not a
  behavioral bug.
- No other contradiction was found. Phase 8.5's request-layer work (this
  session's own Pass 1-4/4.1) never touches any dimension audited here and
  is confirmed unaffected. This audit's NOT READY verdict for the Context
  Assembly Proof **confirms**, rather than contradicts, CLAUDE.md's own
  phase-gating discipline and the roadmap's Phase 8 gate — the gate exists
  precisely because this substrate wasn't ready, and this audit is the
  evidence that gate is functioning as intended.

## 11. Recommendation for the next HQ decision

**Recommendation: B — Authorize Gate B (MySportsFeeds `game_boxscore`).**

Justification: Gate B's provider entitlement is documented as currently
active and broad, evidenced by multiple real successful responses across
other MSF feeds — unlike Gate A, whose billing state is honestly unknown
and whose prior sibling endpoint (injuries) is confirmed blocked under the
same account. Gate B's eligibility condition (a genuinely completed 2026
NFL game) resolves within hours of this audit's own system date/time per
the season-opener record already in the repository, and MSF's trial window
is time-boxed (~2026-09-17) — a use-it-or-lose-it consideration that favors
attempting this gate soon rather than leaving it idle. A successful Gate B
call would directly validate the exact per-game player-performance
substrate this audit identifies as the single central blocker to the
Context Assembly Proof, using the provider path with the fewest open
unknowns. Gate A remains available as a follow-up or parallel
authorization once its billing state is separately resolved, and does not
need to be decided at the same time as Gate B.

This document does not execute this recommendation. No gate call has been
made.
