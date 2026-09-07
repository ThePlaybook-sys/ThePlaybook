# Phase 8.0.5 — Data Activation Prerequisite: Audit + Safe Activation Plan (2026-09-07)

**Status: audit/design only. No workers activated, no provider ownership changed, no code/schema/config committed.** Per HQ's explicit "STOP BEFORE ACTIVATING NEW WORKERS OR CHANGING PROVIDER OWNERSHIP." Every finding below traces to a direct read of real code, real live DEV Supabase state, or a real Railway variable listing — nothing is inferred from memory of a prior audit.

---

## 1. Current worker wiring

| Worker | Code status | Cron target (`cron_dispatch.py`) | `main.py` internal endpoint | Credential configured |
|---|---|---|---|---|
| Injury | Real, tested (`run_injury_worker`) | **None** | **None** | Yes — `SPORTSDATAIO_API_KEY` |
| Weather | Real, tested (`run_weather_worker`) | **None** | **None** | **No — `WEATHERAPI_API_KEY` does not exist on this service** |
| News | Real, tested (`run_news_worker`) | **None** | **None** | **No — `NEWSAPI_API_KEY` does not exist; only `GNEWS_API_KEY` exists, and `news_worker.py` hardcodes `NewsAPINewsAdapter`, not GNews** |

Confirmed by direct read of `apps/workers/app/cron_dispatch.py`'s `_TARGET_PATHS` (exactly `recommendation-worker`, `postgame-grading`, `adaptive-weighting`, `master-refresh`, `odds-worker` — no injury/weather/news target exists) and a full grep of `main.py` (only `/v1/internal/master-refresh/run` and `/v1/internal/odds-worker/run` exist as internal routes). Confirmed by a live `list-variables` call against `sports-intel-layer` DEV (`d00230aa-52c7-46cc-a899-81ba4d55afd8`) — `WEATHERAPI_API_KEY` and `NEWSAPI_API_KEY` are absent from the full variable list.

## 2. Exact activation gaps

Three independent layers, not one — closing Layer A alone would not produce real data for any of the three:

**Layer A — runtime invocation (shared, all three).** No cron target, no internal HTTP endpoint, no Railway Cron Job service. Identical shape to Odds Worker's own pre-Milestone-7.0B gap; the same fix pattern (add target + endpoint + service) applies to all three.

**Layer B — credentials (Weather, News only).** Injury already has its real key. Weather and News have none configured at all — this is a purchase/provisioning gap, not a wiring gap.

**Layer C — data-dependency blockers, distinct per worker, confirmed by direct query against live DEV data:**
- **Injury:** `SportsDataIOInjuryAdapter`'s identity resolution requires a `game_provider_ids` row with `provider_name='sportsdataio'` for each candidate game (`_reverse_resolve_sportsdataio_ids`, `injury_worker.py`). **Queried live: none of the 8 real Phase-7-seeded games have one** (they only carry `the_odds_api` links). Even fully wired and credentialed, this worker would resolve zero real games today.
- **Weather:** needs `games.venue_lat`/`.venue_long` populated (`_location_for_game`). **Queried live: all 8 real games have both fields NULL.** Every one would be skipped as `games_skipped_unresolved_location`, even fully wired and credentialed.
- **News:** **no data blocker.** Team identity resolves via `resolve_team_ids(provider_name='sportsdataio')` against `games.home_team`/`.away_team` abbreviations — already 32/32 confirmed coverage. This is the only one of the three that could produce real data the moment Layers A+B close.

## 3. Proposed safe schedules/cadence (design only, not applied)

All three reuse their existing, already-built cadence logic completely unchanged — this audit found no reason any polling/TTL/append-only logic needs to change, only the invocation mechanism:

- **Injury:** new Railway Cron Job `cron-injury-worker`, `CRON_DISPATCH_TARGET=injury-worker`, schedule `*/15 * * * *` — matches the worker's own tightest real interval (`INACTIVE_LIST` = 15 min), so no tick fires faster than the worker's own logic would ever use. `should_poll_injuries`/day-of-week ramp/single-bulk-call design untouched.
- **Weather:** new Railway Cron Job `cron-weather-worker`, `*/15 * * * *` — matches its existing flat `_POLL_INTERVAL_SECONDS = 900` exactly, mirroring Odds Worker's already-proven cadence pattern. Dome-skip/per-game isolation untouched.
- **News:** new Railway Cron Job `cron-news-worker`, `*/15 * * * *` — matches its existing flat 900s interval. Append-only history write, dedup-by-URL, stale-data-preservation logic untouched.
- **Quota protection, generalized rather than reinvented:** if either newly-provisioned credential is metered, recommend the same self-counted, fail-closed ledger pattern already proven for `odds_api_credit_ledger` — a generic `provider_api_call_ledger(provider_name, ...)`, activated only when explicit budget/floor env vars are set, never defaulting to an invented number. Not built now.

## 4. Provider/API cost implications

- **SportsDataIO (Injury Worker's default):** the Injuries endpoint counts against the **same finite trial budget** as Schedule/Teams/Roster — 11/12 used, 1 reserved. **Activating Injury Worker against SportsDataIO today would immediately start consuming that reserved budget on every real tick.** This is exactly why Injury Worker cannot be safely activated against its current default provider without either spending the reserved call (not authorized) or redirecting it to BALLDONTLIE (a provider-ownership change — explicitly out of this pass's scope).
- **WeatherAPI:** no credential exists, so zero cost incurred to date. **No budget line for this vendor exists anywhere in this project's cost planning** (`docs/business/mansa-business-entitlement-plan-2026-09-03.md` prices BALLDONTLIE/MySportsFeeds/GNews/NewsAPI explicitly; WeatherAPI is absent) — a real, disclosed planning gap, not just a technical one.
- **NewsAPI:** no credential exists either; separately, the project's own News provider decision (NewsAPI vs. GNews) has been an open blocker since 2026-08-11, unresolved independent of this activation question (`docs/ops/news-provider-decision-record.md`).
- **BALLDONTLIE:** already paid (GOAT tier), already live in DEV, 5 req/min confirmed rate limit — the only one of the three real credentials with zero incremental cost to exercise further within its existing plan.

## 5. `player_stats` field-completeness findings

**Resolved with real evidence this pass — the Phase 8.0 audit's "unaudited" open question now has a confirmed answer**, via direct inspection of `tests/fixtures/sportsdataio/player_stats_week_bulk_normal.json` (its own PROVENANCE.md marks it "CONFIRMED FROM LIVE FREE TRIAL — STRUCTURE," i.e. real field shape, not synthetic) cross-checked against `SportsDataIOPlayerStatsAdapter.fetch_player_stats`'s actual mapping code:

- **`player_stats.stats` jsonb captures the complete real payload — 169 fields, confirmed, nothing dropped** beyond the 4 identity fields (`GameKey`/`PlayerID`/`Name`/`Team`) pulled out for typed columns (`stats=remaining`, confirmed by direct code read).
- **Role/usage data: CONFIRMED PRESENT**, resolving the prior open question with a yes: `OffensiveSnapsPlayed`, `OffensiveTeamSnaps`, `DefensiveSnapsPlayed`, `DefensiveTeamSnaps`, `SpecialTeamsSnapsPlayed`, `SnapCountsConfirmed`, `Started`, `Played`, `Activated`, `DeclaredInactive` are all real fields. Target-share is derivable from `ReceivingTargets`/`Receptions`/`ReceptionPercentage` (team-level denominator requires summing across a team's roster for that game — a buildable aggregation, not a missing field).
- **Opponent/matchup context: CONFIRMED PRESENT** — `Opponent`, `OpponentID`, `OpponentRank`, `OpponentPositionRank`.
- **Playing surface: CONFIRMED PRESENT, but in the wrong place for pregame use.** `PlayingSurface`, `Stadium`, `Temperature`, `Humidity`, `WindSpeed` all appear on this POST-GAME player-stat row — the data exists in SportsDataIO's real payload, it's simply not promoted to a pregame-queryable `games` column. This partially resolves the Phase 8.0 "surface not captured" finding: useful for retrospective/backfill contextual analysis once real stats accumulate, not for a pregame weather/surface agent today.
- **Game state/script: CONFIRMED ABSENT**, unchanged from Phase 8.0 — this remains a single aggregate post-game row; no play-level or drive-level sequencing exists in it.
- **BALLDONTLIE comparison** (`NFLStats`, confirmed from the official PyPI package source): ~60 real fields, comprehensive box-score-level stats, but **no snap-count/role field of any kind, and no opponent-rank field.**

**Conclusion:** SportsDataIO is the stronger source specifically for role/usage-based Phase 8 features; BALLDONTLIE is the more accessible, current-season-reachable source for the categories it does cover. Neither alone is sufficient for every Phase 8 contextual feature — this sharpens the Phase 8 audit's "no single provider covers everything" conclusion with real field-level evidence instead of a category-level one.

## 6. BALLDONTLIE provider-neutral integration design (schedules/rosters/injuries/player stats) — design only, not built

Follows the existing `ProviderAdapter` architecture exactly, matching the bake-off's own original recommendation ("Add `BALLDONTLIE*Adapter` classes"), never built until now:

- **Four new adapter classes**, a new `app/adapters/providers/balldontlie.py`: `BallDontLieScheduleAdapter(ScheduleAdapter)`, `BallDontLieRosterAdapter(RosterAdapter)`, `BallDontLieInjuryAdapter(InjuryAdapter)`, `BallDontLiePlayerStatsAdapter(PlayerStatsAdapter)`. No worker/persistence code needs to know which vendor backs the interface — the entire point of the pattern already in place (`base.py`: "Nothing outside this package is allowed to import a provider SDK directly").
- **Identity:** add `'balldontlie'` as a new allowed value to `game_provider_ids.provider_name` / `team_provider_ids.provider_name` / `player_provider_ids.provider_name`'s CHECK constraints — three small, additive migrations, the exact precedent already used for `the_odds_api`/`sportsdataio` ("adding a new vendor is a small follow-up migration," per Volume 3's own text). Not applied this pass.
- **Schedule:** `NFLGame.date` (confirmed this session, via the live discovery probe, to carry a full kickoff timestamp) maps directly to `ScheduleEntry.scheduled_start`. `home_team`/`away_team` resolve via the same `team_provider_ids` mechanism already used everywhere else.
- **Roster:** `NFLPlayer` maps directly to `RosterEntry`; `depth_chart_rank` stays `None` from this adapter (BALLDONTLIE has no dedicated depth-chart endpoint, confirmed by the bake-off) — an honest gap, never fabricated.
- **Injury — the one genuinely different identity path:** `NFLPlayerInjury` (confirmed from the official package source) carries no game reference at all, only `player: NFLPlayer` (which embeds `team`). The adapter cannot resolve `InjuryReport.game_external_id` itself — the **worker** must resolve it via team + week → internal `games.id`, the same technique `injury_worker.py` already uses today, except **simpler**: no provider GameKey hop needed at all, since the player's team resolves directly via `team_provider_ids` and the worker already has `games.home_team`/`.away_team`/`.week` in hand.
- **Player stats:** `NFLStats.game.id` (BALLDONTLIE's own numeric id) needs a `game_provider_ids(provider_name='balldontlie')` row per game — same additive-migration + linking pattern the_odds_api already uses for Odds Worker. Field mapping follows the same "keep the whole remaining dict" pattern as the SportsDataIO adapter, so no fixed field list needs deciding in advance.
- **Rate-limit protection, real not invented:** BALLDONTLIE's confirmed 5 req/min limit (its own `x-ratelimit-limit` header, per the 2026-09-03 bake-off) needs a real token-bucket client for any bulk/backfill use — the bake-off itself already flagged this exact requirement. Not built now.
- **Master Refresh stays untouched, as instructed.** This design describes new adapter classes only; `app.master_refresh.production_clients.build_real_master_refresh_clients` remains SportsDataIO-only. Switching Master Refresh's actual provider is a separate, future, explicitly-not-authorized decision.

## 7. Remaining at-risk 2026 data

Same core urgency as the Phase 8/8.0 audits, restated against today's concrete blockers (opener in ~2.3 days, 2026-09-10T00:20Z; cluster in ~6 days, 2026-09-13T20:25Z):

- **News Worker is the single fastest, lowest-risk real-data win available** — zero data-dependency blocker, only credentials + wiring stand between it and real history today.
- **Injury and Weather both carry a real secondary blocker wiring alone will not fix** — GameKey linkage (Injury) and venue coordinates (Weather) — so authorizing their cron wiring without also resolving Layer C would produce a worker that runs, costs real API calls, and still writes zero real rows for the currently-tracked games.
- If nothing changes before kickoff, zero real pregame injury/weather/news history will exist for either tracked real cluster, permanently, for those specific games — unchanged from the original warning, now measured against confirmed blockers rather than a general risk statement.

## 8. Exact implementation steps for 8.0.5 (proposed sequence — NOT executed this pass)

1. HQ decision: authorize News Worker activation first (lowest risk; only a `NEWSAPI_API_KEY` purchase — or revisiting GNews vs. NewsAPI first — stands in the way).
2. Add `news-worker` to `_TARGET_PATHS`, `/v1/internal/news-worker/run` to `main.py`, a new Railway Cron Job service — mirroring Odds Worker's Milestone 7.0B pattern exactly.
3. For Weather: HQ decision on a `WEATHERAPI_API_KEY` purchase (no existing budget line) plus a small design pass on populating `venue_lat`/`venue_long` for manually-seeded/BALLDONTLIE-sourced games (a static ~30-stadium coordinate table — not a new geocoding vendor, per the existing architectural constraint) before wiring its cron target.
4. For Injury: HQ decision on the reserved-SportsDataIO-call question, or authorize building the BALLDONTLIE injury path (§6) as the real activation route instead.
5. Once any worker is cron-wired, confirm its existing cadence/TTL/append-only/quota-guard logic needs zero changes — this audit found the gap is entirely at the invocation/credential/identity layer, never the polling logic itself.
6. Re-run this audit's own row-count check after each newly-wired worker's first real tick, mirroring the exact "proof before leaving unattended" discipline already established for Odds Worker's own activation.

## 9. Decisions HQ must approve before activation

1. Authorize purchasing/configuring `NEWSAPI_API_KEY` (or revisit GNews vs. NewsAPI first) — News Worker's only real blocker beyond wiring.
2. Authorize purchasing/configuring `WEATHERAPI_API_KEY` — no budget line exists for this today.
3. Decide Injury Worker's real activation path: spend the reserved SportsDataIO call to link real GameKeys, or authorize building the BALLDONTLIE injury adapter (§6) as an alternative route.
4. Authorize the actual cron-wiring work (new `main.py` endpoints, `cron_dispatch.py` targets, Railway Cron Job services) once the above are decided — this document proposes the design, not the code.
5. Authorize a `venue_lat`/`venue_long` backfill approach for Weather Worker's real games (static stadium-coordinate table vs. waiting for a real Master Refresh/BALLDONTLIE schedule cycle to supply it naturally).
6. Whether to build the BALLDONTLIE adapter classes now (fixture-first, matching established discipline) even before the identity migrations/cron wiring above are authorized, or wait until the provider-path decision (#3) is made first.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call still reserved); Phase 7 observation window untouched; no Phase 7.2/7.3; no Phase 8.1 implementation; no Phase 4 modification; no Milestone 5.6; staging/production untouched; no invented provider capability (every BALLDONTLIE/SportsDataIO claim traces to a real fixture, real code, or the already-published 2026-09-03 diagnostic reports); MySportsFeeds PBP/box-score decision left exactly as pending as it already was. No worker activated, no cron target added, no provider ownership changed.
