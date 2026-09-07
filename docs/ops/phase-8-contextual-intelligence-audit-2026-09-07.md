# Phase 8 — Contextual Performance Intelligence: Architecture & Data Audit (2026-09-07)

**Status: audit/planning only. No implementation, no schema change, no code change, no provider calls, no Phase 4 modification, no Phase 7 modification.** This document extends Milestone 8.0 (`docs/blueprint/engineering-roadmap-build-order.md`, Phase 8; Volume 4 §8.6; `docs/ops/2026-data-preservation-requirement.md`) with the deeper, HQ-requested audit below — it confirms and sharpens Milestone 8.0's existing findings rather than contradicting them, and adds several findings Milestone 8.0 did not go deep enough to surface (most importantly: which specialized workers actually run today, which committee agents actually exist as code, and the exact Probability Modeling integration point).

**Method:** direct inspection only — live DEV Supabase row counts (`nhwjtsdebgiwskshzqiq`), direct reads of `apps/workers/app/cron_dispatch.py`, `apps/ai-orchestrator/app/agents/*.py`, `apps/ai-orchestrator/app/agents/committee_context.py`, `docs/blueprint/volume-3-database-architecture.md`, `docs/blueprint/volume-4-ai-intelligence.md` §8.6/§2.2-2.5, `docs/blueprint/engineering-roadmap-build-order.md` Phase 8, and the two 2026-09-03 NFL provider diagnostic reports. Nothing below is inferred from memory of a prior session's summary — every claim traces to one of these direct reads. Zero SportsDataIO calls made; the reserved final trial call remains unspent.

---

## 1. Existing usable substrate

**Real, live DEV row counts as of 2026-09-07T19:00Z** (the season has not started — opener kicks off 2026-09-10, so nothing below reflects a played game):

| Category | Table(s) | Rows | What the rows actually are |
|---|---|---|---|
| Odds | `odds_snapshots` | **138** | **Real.** 5 real, provider-linked games (the Phase 7 opener + 4-game cluster), captured this session. The one category with genuine, substantial pregame history today. |
| Teams | `teams`, `team_provider_ids` | 32 / 49 | Real. Full 32-team league; `sportsdataio` mapping 32/32 confirmed; `the_odds_api` mapping ~17/32 (grew this session via Phase 7 work). |
| Games | `games`, `game_provider_ids` | 12 / 12 | Mixed: 4 non-real Phase-1 demo/fixture rows + 8 real Phase-7-manually-seeded rows. **Zero games created by a real Master Refresh cycle.** |
| Players | `players`, `player_provider_ids` | 6 / 0 | Fixture only — "the entire universe of player identity evidence this project has ever captured" per Volume 3 §4.0's own text. No live provider call has ever expanded this. |
| Player/team stats | `player_stats`, `team_stats`, `player_stats_nfl` | 2 / 2 / 2 | Fixture only. No game has finished, so no real postgame stats exist anywhere. |
| Injuries | `injury_reports` | 1 | Fixture only. |
| Weather | `weather_snapshots` | 1 | Fixture only. |
| Referee | `referee_assignments` | 1 | Fixture only. |
| Roster history | `roster_memberships` | **0** | Never populated, ever, since the table's creation. |
| Depth charts | `depth_chart_snapshots` | **0** | Never populated, ever. |
| News history | `news_article_history` | **0** | Table live (migration applied 2026-09-04, append-only trigger proven), write path wired into `news_worker.py` — but zero real rows exist. |
| Game events / PBP | `game_events` | **0** | Table live (migration applied 2026-09-04, same proof discipline), `write_raw_game_events` exists and is tested — never invoked against a real game. |
| `daily_game_intelligence` | 1 | Fixture-only demo row. |

**Root cause of the zeros, confirmed by direct code read, not assumed:** `apps/workers/app/cron_dispatch.py`'s own current docstring (edited this session, 2026-09-07) states plainly: *"Only Odds Worker is activated this milestone... the other six specialized workers (Player Props/Injury/Weather/News/Pregame/Postgame Ingestion) remain unwired."* `_TARGET_PATHS` confirms it — exactly five targets exist (`recommendation-worker`, `postgame-grading`, `adaptive-weighting`, `master-refresh`, `odds-worker`); there is no `injury-worker`, `weather-worker`, `news-worker`, `player-props-worker`, `pregame-worker`, or `postgame-ingestion-worker` target at all. So `injury_reports`/`weather_snapshots`/`news_article_history` aren't at 0 because the underlying workers are broken — they're at 0 because **nothing in DEV ever calls them.** The code and schema are real; the runtime activation is not.

`roster_memberships`/`depth_chart_snapshots` are at 0 for a related but distinct reason: those are captured by **Master Refresh**, which *does* have a real cron target — but Master Refresh's only real client is SportsDataIO (`app.master_refresh.production_clients.build_real_master_refresh_clients`), and no real Master Refresh cycle has ever run against live data, because doing so would spend real SportsDataIO trial calls beyond the deliberately reserved final one (11/12 used, 1 reserved, confirmed untouched this pass).

**Committee reality (new finding, not previously surfaced this precisely):** Volume 4 §2.2-2.4 defines 17 fan-out agents. `apps/ai-orchestrator/app/agents/committee_context.py`'s own `CONFIGURED_AGENTS`/`BUILT_AGENTS` constants (the system's own honest, disclosed tracking of this) show **6 of 17 actually exist as code**: Injury Intelligence, Weather, Travel & Fatigue, Rest Days, Vegas Line, Closing Line Movement. `committee_completeness = 6/17 ≈ 0.353`. **Zero of the 8 Matchup & Form Agents (§2.3) exist** — including Offensive Matchup Agent, Defensive Matchup Agent, and Player Prop Agent, which are exactly the agents Volume 4 §8.6's own architecture-position paragraph names as natural consumers of contextual-performance output. This is a real, disclosed (the system tracks `deferred_agents` honestly), and directly relevant constraint on what Phase 8 can integrate with today.

**Genuinely usable substrate, net of the above:**
- **Real, substantial:** Odds pregame history (5 games, 138 rows) — usable today for anything odds-movement-related, not for player/team performance context.
- **Real but thin:** teams/team identity (solid), games (8 real rows, all pregame, none played).
- **Schema-ready, zero real data:** injuries, weather (pregame), depth charts, roster history, news history, game events — every one of these needs either (a) the specialized-worker wiring gap closed, or (b) a real Master Refresh/backfill cycle, before Phase 8 could query anything real from them.
- **Genuinely absent:** playing surface (no column anywhere), in-game state for any category, comparable-situation retrieval computation (doesn't exist, is new work regardless of table state).

## 2. Missing substrate

Restating and updating the 2026-09-04 Data Preservation Requirement's findings against today's actual state:

1. **In-game capture, every category, still zero, unchanged.** Odds/Player Props Workers still stop at kickoff (`Window.STOPPED`, unchanged this session). Injury/Weather Workers gained a 4-hour bounded post-kickoff extension (live since 2026-09-04) — **but Injury/Weather Workers still have no cron invocation path at all**, so that extension has never actually executed against a real game either. The capability was built; it has never run.
2. **No play-by-play/game-event content.** Table live, zero rows, gated on the still-not-yet-run 2026-09-09/10 live-game MySportsFeeds validation.
3. **No news history content**, despite the write path being wired — News Worker is unwired at the cron layer, same root cause as #1.
4. **No playing-surface column** anywhere in `games` or any supporting table.
5. **`player_stats.stats` role/usage field-completeness is still unaudited** — an open question, not a confirmed gap or a confirmed capability.
6. **No roster/depth-chart real history** — blocked on Master Refresh never having run against live data (see §1's root-cause note), itself blocked on the reserved SportsDataIO call question.
7. **No comparable-situation retrieval capability exists anywhere** — genuinely new computation Phase 8 must build, independent of any table's row count.
8. **Historical backfill has not actually been pulled into MANSA's own database at all** — provider-side availability (BALLDONTLIE ~2 seasons, MySportsFeeds mixed, API-SPORTS 2022-2024) is a different fact from data actually sitting in MANSA's own tables, and none of it does yet.

## 3. Provider/source matrix (BALLDONTLIE + MySportsFeeds, per HQ's explicit scope — SportsDataIO's final call not spent to add anything further)

Carried forward from the 2026-09-03 bake-off (`docs/ops/nfl-provider-bakeoff-2026-09-03.md`) and gap-test (`docs/ops/nfl-provider-gap-test-mysportsfeeds-2026-09-03.md`) — not re-tested this pass, per the explicit "do not invent provider capabilities" guardrail; these are the same live-verified findings those two diagnostic passes already produced.

| Capability | BALLDONTLIE (paid GOAT, active DEV credential) | MySportsFeeds (Live, 10-min delay, CORE+STATS+DETAILS) | Verdict for Phase 8 |
|---|---|---|---|
| Current-season schedules | **GREEN**, confirmed live 2026 | Not the recommended source (BALLDONTLIE already covers it) | BALLDONTLIE |
| Current-season rosters | **GREEN** (`/players/active`) | Not tested for current season | BALLDONTLIE |
| Current-season injuries | **GREEN**, real specific descriptions | **YELLOW** — 2 of 3 sampled descriptions were literally `"unknown"` | BALLDONTLIE preferred |
| Current-season player stats | **GREEN** (`/stats`, `/season_stats`) | Not the recommended source | BALLDONTLIE |
| Advanced/next-gen player stats | **GREEN**, exclusive strength (air yards, aggressiveness, CPOE) | Not offered | BALLDONTLIE-exclusive |
| Current-season **team** stats | **RED** — no endpoint exists in the official SDK | **GREEN** — real, deeply-typed, confirmed populated on a completed season | **MySportsFeeds is the only GREEN of the two for this specific gap** |
| Lineups (expected/depth-level) | Not offered | **GREEN** — real, correctly-null-where-unconfirmed | MySportsFeeds-exclusive strength |
| Play-by-play | **RED** — no endpoint exists at all | **UNKNOWN** — endpoint exists, clean `204` on an unplayed game, never observed against a real payload | Unresolved for both; needs the still-pending post-kickoff live test |
| Box scores / game detail | Not offered | **UNKNOWN** — same untested-against-a-real-game constraint | Unresolved |
| Historical game listings (backfill) | **GREEN**, at least 1 prior season (2025) confirmed live | **RED for this plan** — prior-season game LISTS 403'd on two feeds, even though prior-season standings succeeded on the same key | BALLDONTLIE materially ahead; MySportsFeeds' restriction is plan-specific, not a blanket capability absence |
| Standings | UNKNOWN (rate-limited both bake-off attempts) | **GREEN**, real prior-season data | MySportsFeeds, where BALLDONTLIE is unconfirmed |
| Freshness/correction signal | Not offered | **GREEN**, exclusive (`latest_updates`, 120 named sub-feeds) | MySportsFeeds-exclusive strength |

**Net conclusion (unchanged from the gap-test's own conclusion, restated for this audit): no single provider — including SportsDataIO — covers everything Phase 8 needs.** The realistic composite is BALLDONTLIE for current-season schedule/roster/injury/player-stat/advanced-stat substrate, MySportsFeeds for current-season team stats and lineups specifically, with PBP/box-score depth an open question for both, pending a live-game test that still hasn't happened (no 2026 game has been played as of this audit).

## 4. Proposed contextual intelligence architecture

**Confirms and does not depart from Volume 4 §8.6's already-approved design.** Restated for HQ's specific "design the comparison model" ask, with the "do not create one table/model per player" constraint addressed directly:

- **A deterministic, stateless computation, not a stored per-entity model.** Given `(player_id or team_id, game_id, context_dimension)`, the module queries already-existing append-only history (`player_stats`/`team_stats` joined against `games`/`weather_snapshots`/`injury_reports`/`depth_chart_snapshots` at the relevant historical point) and returns a plain computed result — never a persisted, mutable "current model state" row per player. This is the actual mechanism that avoids the one-table-per-player anti-pattern: there is no `player_impact_<id>` table and no single `player_contextual_state` row that gets UPDATEd — every call re-derives its answer fresh from immutable history, the same reproducibility discipline every other table in this schema already follows (Volume 3 §1's own non-negotiable).
- **Required output shape, per HQ's evidence-requirements list (already locked in Volume 4 §8.6):** `sample_size`, `similarity_score` (or equivalent), `recency_weight`, `baseline_performance`, `confidence`/`uncertainty`, `disclosed_confounders` (nullable list), and an explicit `insufficient_comparable_evidence: bool` — never a suppressed or dressed-up guess when evidence is thin.
- **If caching/memoization ever becomes a real performance need** (not evidenced as necessary today, since the underlying real-data volume is currently ~zero per §1 above): a generic, keyed cache table (`cohort_key`, `computed_at`, `result jsonb`, TTL) is the correct shape — still not one row or table per player, and still fully reproducible from source history if the cache is ever cleared.
- **Home: a new deterministic module in `ai-orchestrator`** (e.g. `app/features/contextual_performance.py`), matching `app/features/market.py`/`app/features/grading.py`'s exact precedent — not a new worker, not a new agent, not a new table beyond the optional cache above.

## 5. Propagation into markets

Per Volume 4 §8.6's own target flow (unchanged, confirmed correct by this audit): `Raw data → Contextual Performance Intelligence → player/team impact → Probability Modeling → market comparison → EV/Risk/Consensus → Recommendation → Grading`. Because Probability Modeling is **already candidate-anchored** (Volume 4 §4.1's v5.1 note — it runs once per specific priced `MarketCandidate`: moneyline, spread, total, or prop), Phase 8's signal reaches every market type through that same existing per-candidate mechanism — **no separate propagation path is needed per market type.** Whatever market the current candidate is, Probability Modeling already receives a fresh evaluation for it.

**Correlated parlays are explicitly out of reach today, not a Phase 8 gap.** Volume 4 §9 Decision AD/AN, confirmed by a full-codebase grep at the time it was written: "no joint-probability formula, no combined-EV formula, no correlation data... exists anywhere in this codebase." Contextual intelligence has nothing to propagate into until a joint-probability/correlation engine itself exists — that's new scope beyond Phase 8, not something this audit can schedule.

## 6. Probability Modeling integration point

**Exact location, confirmed by direct read: `apps/ai-orchestrator/app/agents/probability_modeling.py`, `ProbabilityModelingAgent.build_evidence()`.** Today it constructs exactly three keys: `candidate`, `upstream_findings` (the dumped outputs of whichever fan-out agents ran), and `participation` (honest committee-completeness metadata). The smallest correct integration is a fourth key — e.g. `contextual_performance` — sourced from the new module's output for this candidate's game/players, mirroring exactly how the 6 built fan-out agents already receive `context.injuries`/`context.weather` via `AgentContext` (confirmed by reading `injury_intelligence.py`: `build_evidence` is a one-line passthrough of already-assembled context, not a direct DB query).

**Two consistent entry points, matching §8.6's own "feeds existing agents, also flows to Probability Modeling" language exactly** — not competing designs:
1. Enrich `AgentContext` so the 6 already-built fan-out agents (especially Injury Intelligence and Weather, the two most directly context-relevant) reason over evidence-graded historical impact, not only raw current-state data.
2. Add the same signal as a new field in `SequentialDecisionContext`, surfaced directly in Probability Modeling's own `build_evidence()`.

**Real, disclosed constraint this audit surfaces precisely: full "Committee Integration" (Milestone 8.2) is bounded by which agents exist.** Offensive Matchup, Defensive Matchup, and Player Prop Agent — the three agents most naturally suited to consume contextual performance impact — do not exist as code (§1 above). Wiring into them is not possible until they're built, which is Phase 4 completion work, explicitly out of this audit's authorized scope ("do not modify Phase 4 yet"). Milestone 8.2 can genuinely integrate with the 6 built agents and Probability Modeling directly; full integration waits on Phase 4.

## 7. Immediate 2026 preservation gaps

Same core urgency the 2026-09-04 document already named, still live (opener 2026-09-10, cluster 2026-09-13 — both still ahead of this audit):

1. **Injury/Weather in-game capture is built but has never run** — no cron target exists for either worker. This is the single most actionable, lowest-effort closeable gap: the extension logic already exists (4h post-kickoff bounded window), it's just never been invoked.
2. **News history is built but has never run** — same root cause, same fix shape (a cron target).
3. **PBP/game-event capture remains gated on the still-pending live-game validation** — unchanged, unresolved, and now three days closer to the opener than when first flagged.
4. **Surface column still not added.**
5. **`player_stats.stats` field-completeness still unaudited.**
6. **Newly sharpened this pass: roster/depth-chart history cannot become real without either spending the reserved SportsDataIO call or deciding BALLDONTLIE becomes Master Refresh's real schedule/roster source.** This is a genuine, live decision blocking real data in two Phase-8-relevant tables (`roster_memberships`, `depth_chart_snapshots`) that has not been named this explicitly before.

## 8. Historical-backfill strategy

- **BALLDONTLIE is the strongest available backfill source today** — already paid (GOAT tier), already confirmed live for the current season plus at least one prior season (2025), zero incremental cost. Best fit for schedule/roster/injury/player-stat/advanced-stat backfill.
- **MySportsFeeds' backfill depth is genuinely mixed, not uniformly blocked** — prior-season game *listings* 403'd on the evaluated plan, but prior-season *standings* succeeded on the identical key. This needs a feed-by-feed recheck before writing it off, not a single yes/no conclusion.
- **API-SPORTS (2022-2024) is now the lowest-priority option** — older than BALLDONTLIE's own reach, and its one former unique strength (current-season team stats) is matched by MySportsFeeds without the plan restriction, per the gap-test's own conclusion.
- **SportsDataIO's real backfill depth is completely unconfirmed** — the reserved final trial call has deliberately never been spent to test it, and this audit does not spend it either, per its own guardrail.
- **Recommended shape (not authorized to execute):** BALLDONTLIE-first backfill for schedule/roster/injury/player-stat substrate (already paid, already proven), MySportsFeeds layered in for team-stats/lineup history once its feed-by-feed depth is separately confirmed, SportsDataIO backfill depth left as an open HQ spending decision. None of this is scheduled by this document.

## 9. Proposed Phase 8 milestones

Builds on, does not replace, the roadmap's existing 8.0-8.3 breakdown — adding one new proposed insertion this audit's findings make necessary, and sharpening 8.1/8.2's real dependencies:

- **8.0 — Contract Audit & Architecture Decision. COMPLETE** (roadmap entry + this document).
- **8.0.5 (new, proposed) — Data Activation Prerequisite.** Wire the specialized-worker runtime invocation gap (Injury/Weather/News at minimum) and/or resolve the SportsDataIO-reserved-call/BALLDONTLIE-as-Master-Refresh-source decision. Explicitly NOT Phase 8 subject-matter work — it's Phase 3E/3F worker-activation debt plus a provider decision — but Phase 8 cannot honestly produce real evidence-graded output without real rows to query, and today there are almost none outside odds. Flagged as a hard sequencing dependency, not assumed away.
- **8.1 — Comparable-Situation Retrieval & Evidence Scoring.** Can be BUILT fixture-first now (no real-data dependency to start coding, matching the project's own established discipline). **Cannot be VALIDATED against real comparable situations until 8.0.5 closes and/or real games accumulate history** — a distinction worth keeping explicit rather than letting "built" quietly stand in for "proven."
- **8.2 — Committee Integration.** Genuinely achievable scope today: the 6 built fan-out agents + Probability Modeling's own `build_evidence()` (§6 above, exact integration points named). Full-committee integration (Offensive/Defensive Matchup, Player Prop Agent) waits on Phase 4 completion — outside this milestone's authorized scope.
- **8.3 — Explainability & Market Propagation.** As scoped in the roadmap; confirm reach across every candidate market type via the existing candidate-anchored mechanism (§5 above); parlay propagation stays deferred until Volume 4 §9's own parlay activation, not before.

**Dependency order:** 8.0 (done) → 8.0.5 (new, HQ decision required) → 8.1 (build now, validate later) → 8.2 (bounded by Phase 4 today) → 8.3.

## 10. Blockers/decisions requiring HQ approval

1. **Authorize wiring the remaining specialized workers' runtime invocation paths** (Injury/Weather/News at minimum) — zero cron/HTTP path exists for any of them today except Odds.
2. **Decide the reserved-SportsDataIO-call question**: spend it (for historical-depth testing) or formally adopt BALLDONTLIE as Master Refresh's real schedule/roster source — `roster_memberships`/`depth_chart_snapshots` stay at 0 real rows either way until one is decided.
3. **The 2026-09-09/10 live-game PBP/box-score validation remains pending** — same open gate as before, now closer.
4. **Authorize (or hold) Milestone 8.1's build**, understanding it can start now but can't be validated against real data yet.
5. **Decide whether closing the News-history activation gap should be prioritized ahead of Phase 8 proper** — §8.6 itself names it as a real prerequisite for the News→context connection.
6. **Confirm whether to formally add "8.0.5 Data Activation Prerequisite" to the roadmap**, or fold its content into 8.1's own dependency list instead.
7. **Authorize the still-outstanding `player_stats.stats` role/usage field-completeness audit** — blocks confidently claiming "player role/usage" as available Phase 8 substrate.

---

**Guardrails held throughout:** no implementation, no Phase 8 code/migration, no Phase 7 change (observation window untouched), no Phase 4 modification, no Milestone 5.6 work, zero SportsDataIO calls (11/12 used, final call still reserved), no staging/production access, no invented provider capability (every provider claim above traces to the two already-published 2026-09-03 diagnostic reports, never re-guessed).
