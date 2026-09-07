# Phase 8.0.5 — Weather Activation + Closeout (2026-09-07)

**Status: Weather Worker real, live, verified, and recurring in DEV. Phase 8.0.5 closeout audit complete.** DEV only throughout. Zero SportsDataIO calls (11/12 used, final call untouched). Zero staging/prod changes. No Phase 7.2/7.3, Phase 8.1, Phase 4, or Milestone 5.6 work performed. No invented data anywhere.

---

## 1. Weather credential/runtime verification

`WEATHERAPI_API_KEY` confirmed present in `sports-intel-layer`'s **DEV** environment variable list via a live `list-variables` read — the exact same Railway service/environment that now hosts `/v1/internal/weather-worker/run` and that `cron-weather-worker` dispatches to. Value never read into this session or logged anywhere (`list-variables` returns names only under this session's connection type; `production_clients.py`'s own `build_real_weather_worker_clients()` is the only place in the codebase that reads it by name, matching the isolation discipline already reserved for it in `tests/test_environment_safety.py`'s forbidden-names list ahead of this moment).

## 2. Controlled live Weather result

One controlled real run, via the same temporary gated-diagnostic pattern established for every prior live proof this project has used (this sandbox cannot reach Railway's private network directly). Real result, read from actual DEV deploy logs:

```
games_considered=5, games_due=2, games_skipped_dome=[LV/MIA, MIN/GB],
games_skipped_unresolved_location=[], snapshots_persisted=3 (real, before
the repeat run correctly found them already covered)
```

Candidate window held exactly the 5 real Phase 7/8 games within 7 days of 2026-09-07 (the 3 Oct-11-cluster games remain outside that window, unaffected). Of those 5: 2 are domes (correctly zero-cost skipped, never reaching WeatherAPI at all), 3 are real, pollable, coordinate-resolved games — and all 3 were fetched and persisted in the run that happened first. A back-to-back immediate repeat (both within the diagnostic's own two calls, and — because Railway raced this deploy against the git-push autodeploy the same way it did for Pass 2.2's News proof — across more than one independent container start) correctly found all 3 already covered and made zero additional real WeatherAPI calls, only re-confirming the 2 dome games as (harmlessly, zero-cost) "due." **Total real WeatherAPI spend for this entire proof: 3 calls.**

## 3. Persisted real Weather rows

Read directly from `weather_snapshots` after the proof:

| game_id | Real game | `weather_data` |
|---|---|---|
| `280e7b05...` | SEA @ NE | `{source: "weatherapi", is_dome: false, temperature_f: 63.1, wind_mph: 0.9, conditions: "Overcast", precipitation_pct: 15, observed_at: "2026-09-09T23:00:00+00:00"}` |
| `cd0f612b...` | PHI @ WAS | `{source: "weatherapi", is_dome: false, temperature_f: 76.5, wind_mph: 11.4, conditions: "Cloudy", precipitation_pct: 7, observed_at: "2026-09-09T23:00:00+00:00"}` |
| `57316028...` | LAC @ ARI (SoFi) | `{source: "weatherapi", is_dome: null, temperature_f: 81, wind_mph: 7.2, conditions: "Clear", precipitation_pct: 2, observed_at: "2026-09-09T23:00:00+00:00"}` |

Every explicit verification HQ asked for, checked against these real rows, not just logs:

- **Game/venue association:** each row's `game_id` matches exactly the real, already-identity-resolved tracked game (confirmed against the Pass 2.1 recovery-checkpoint export). Venue coordinates feeding the WeatherAPI `q` param came from `games.venue_lat`/`.venue_long`, themselves sourced from the canonical sport-agnostic `venues` table built in Pass 2 — the architecture asked for was used exactly as-is, nothing new built.
- **Observation/forecast timestamps:** `observed_at` (`2026-09-09T23:00:00+00:00`, WeatherAPI's own forecast-hour timestamp, closest to each game's real kickoff) is present and distinct from `captured_at` (`2026-09-07 23:10:25`, our own real poll time) — a real, previously-silently-dropped gap closed this pass (see §"A gap closed" below).
- **Provider provenance:** `source: "weatherapi"` present on every real row, absent from the old fixture row (see below) — genuinely distinguishable, not inferred.
- **No fixture/synthetic contamination:** the one pre-existing fixture row (`game_id=a5000000-...-003`, a seed/test game, `weather_data={temp_f, wind_mph, condition, precipitation_pct}`) uses a **structurally different key shape** (`temp_f`/`condition`, no `source`/`observed_at`) than every real row (`temperature_f`/`conditions`, with `source`/`observed_at`) — the two are cleanly distinguishable by shape alone, and the fixture row was untouched (still exactly 1, now alongside 3 new real rows — 4 total).
- **SoFi's unresolved venue type — NULL preserved, never invented:** the LAC/ARI row's `is_dome` is JSON `null`, not `false`. This is the exact real behavior HQ required ("Do not invent data for the unresolved SoFi venue type. NULL remains valid.") — confirmed from the real persisted row, not just code inspection.
- **Dedup/idempotency:** `weather_snapshots` remains deliberately append-only (matching `odds_snapshots`/`injury_reports`'s own established "every real capture is a new row" convention) — there is no unique constraint to violate, and none was needed: the real repeat run produced zero *additional* rows for the 3 already-covered games because the durable cadence gate (below) correctly judged them not-yet-due, not because of any database-level dedup. This is the same idempotency mechanism Odds Worker already relies on.

**A gap closed, not merely diagnosed (Pass 2.1's own discipline applied proactively this time):** `WeatherAPIWeatherAdapter` always computed a real `source`/`provider_reported_at`, but `run_weather_worker`'s per-game loop discarded both before calling `persist_weather_snapshots` — neither was ever persisted, anywhere, before this pass. Fixed with a two-line, zero-schema-change addition: both values are now embedded into the existing `weather_data` jsonb payload (`source`, `observed_at`). No migration, no new column — the smallest fix that makes HQ's own explicit verification checklist actually checkable from real data instead of only from transient logs.

## 4. Quota/cadence analysis

**WeatherAPI DEV Free-tier budget: 1,000,000 requests/month** (already confirmed, not re-derived — `docs/business/mansa-business-entitlement-plan-2026-09-03.md`'s own 2026-08-10 procurement finding).

- **External calls per eligible game/run:** exactly 1 real WeatherAPI call per due, non-dome, coordinate-resolved game per invocation — confirmed by the live proof (3 pollable games → 3 real calls, not more).
- **Cron invocation frequency vs. real provider-call frequency (explicitly distinguished, per HQ's instruction):** `cron-weather-worker` ticks every 15 minutes (96 ticks/day), but a real WeatherAPI call only happens for a game whose real, persisted `last_polled_at` (derived from `weather_snapshots.captured_at`, mirroring Odds Worker's own established pattern — see §"Durable last_polled_at" below) shows ≥15 minutes elapsed. In steady state this means each pollable game is actually fetched roughly once per 15-minute window it remains due, not once per cron tick.
- **Expected calls per game through the candidate window:** a game enters the 7-day candidate window, is polled at most once per 15 minutes while due (bounded further by `Window.STOPPED`/`in_game()` gating exactly as today, unchanged), then drops out of the window. Real, worst-case upper bound per game across its full ~7-day pollable life: 7 days × 96 ticks/day = 672 calls — never approached in practice since most of that window a game isn't yet within any tighter ramp boundary that would matter, and this worker's own flat 15-minute interval is already the ceiling, not a floor.
- **Estimated daily exposure, current tracked games:** 3 pollable games × 96 ticks/day (if every tick found something due, which it won't once cadence is real) = a generous upper bound of 288 calls/day = **8,640/month — 0.86% of the free-tier budget.**
- **Reasonable future NFL exposure:** a full active slate (~16 games/week) with a generous 12 non-dome average simultaneously inside the 7-day window: 12 × 96/day × 30 ≈ 34,560/month — **3.5% of budget.** Even an extreme, unrealistic upper bound (32 games, every one polled every single tick with zero cadence gating at all) is 32 × 96 × 30 ≈ 92,160/month — **9.2% of budget.**

**Conclusion: quota is not a binding constraint at any realistic current or future scale.** Unlike GNews's real 100/day free-tier ceiling (the actual cause of Pass 2.1's incident), WeatherAPI's 1M/month allowance has enormous headroom even under generous growth assumptions. Building a dedicated hard quota ledger (mirroring News's `news_provider_daily_quota`) here would be manufactured protection against a risk the real numbers show doesn't exist — inconsistent with "no unnecessary provider spend" and needless complexity for its own sake.

**Provider-budget protection actually included, matching what the architecture genuinely needed:** the same class of bug that caused Pass 2.1's News incident (a stateless HTTP-triggered cron caller never deriving real `last_polled_at`, so every candidate reads as "never polled" on every tick) was fixed here **proactively, before any recurring activation, not after an incident.** `app.persistence.weather_snapshots.read_last_polled_at()` derives real per-game cadence state from already-persisted `captured_at` history — zero new schema, reusing the exact pattern Odds Worker already established for the identical problem. This is the correct, proportionate protection for a provider whose real quota isn't tight: cadence correctness, not a redundant ledger.

## 5. Recurring Weather activation status

**Clean and authorized — activated.** New Railway Cron Job service `cron-weather-worker` (id `681b34a9-a80a-48a3-b94e-06e1705922d1`) created mirroring `cron-odds-worker`'s exact configuration (same repo/branch/`rootDirectory`, same `DOCKERFILE` builder, same frozen `watchPatterns`, same `restartPolicyType=NEVER`), `CRON_DISPATCH_TARGET=weather-worker`, `CRON_DISPATCH_BASE_URL`/`INTERNAL_SERVICE_TOKEN` set as cross-service references to `sports-intel-layer` (never copied literals) — the smallest existing worker/cron pattern, exactly as HQ authorized. Schedule: `*/15 * * * *` (matching the worker's own existing, already-correctly-reasoned flat 15-minute cadence — no widening needed, unlike News, since quota headroom here is enormous). First build confirmed **SUCCESS**, deployed from the clean, post-diagnostic-revert commit. First real scheduled tick fires within 15 minutes of this report.

## 6. BALLDONTLIE blocker update

Recorded exactly as HQ specified, no new calls made:

> GOAT entitlement is documented as including Player Injuries. The `Authorization` header format our adapter sends matches documented requirements exactly. The user's Sep 5 BALLDONTLIE invoice is OPEN/unpaid, so paid GOAT entitlement is not currently confirmed active — this, not a code defect, is the likely cause of the real 401. `Games` works today because it is available on the Free tier; Player Injuries remains unavailable pending confirmed paid entitlement.

No additional live calls made to `/nfl/v1/player_injuries` this pass. The completed adapter (`BallDontLieInjuryAdapter`) was not modified. Zero SportsDataIO spend. When paid access becomes available, validation begins with exactly one controlled request, per HQ's own instruction — not before.

## 7. Phase 8 real-data substrate matrix

Audited via a live `list_tables` read against DEV plus targeted row inspections (not assumed from memory of prior reports).

| Dimension | Status | Real evidence |
|---|---|---|
| **Schedules/games** | **REAL + ACTIVE** | 8 real Phase 7/8 games (`manual_seed=true`), real `game_provider_ids` (17 rows, the_odds_api + balldontlie identity for all 8), real kickoff/week/season data. `cron-master-refresh`/`cron-odds-worker` both running. |
| **Teams** | **REAL + ACTIVE** | 32/32 NFL teams, full canonical reference data; `team_provider_ids` (59 rows) resolving sportsdataio/the_odds_api/balldontlie identity for every tracked team. |
| **Players/rosters** | **MISSING/INSUFFICIENT** | `players`: 6 rows, all explicitly seed/fixture (`"Seed QB Chiefs"`, `external_provider_id="seed-p1"`, etc.) — zero real player identity resolved. `player_provider_ids`: 0 rows. |
| **Depth/lineups** | **MISSING/INSUFFICIENT** (code ready) | `roster_memberships`/`depth_chart_snapshots`: 0 rows each, but `app.persistence.roster_ingestion` is a real, complete, well-designed persistence module (first-observed-membership/team-change/no-fuzzy-matching semantics all already built) — never invoked against a live `RosterAdapter`. Not blocked by any credential/entitlement; simply never scoped/authorized to run for real. |
| **Injuries** | **IMPLEMENTED BUT BLOCKED** | `injury_reports`: 1 row, fixture only. Real adapter (`BallDontLieInjuryAdapter`) complete and correct; blocked on the account's own unpaid GOAT invoice (§6), not code. |
| **Player stats** | **MISSING/INSUFFICIENT** (schema/mapping proven, no real data) | `player_stats`/`player_stats_nfl`: 2 rows each, both explicitly fixture-linked (same `a6000000...` seed IDs). The Phase 8 audit's "169 real SportsDataIO fields confirmed" finding came from a local fixture file review, never persisted as live captured data — real field-completeness is proven, real game data is not present. |
| **Team stats** | **MISSING/INSUFFICIENT** | `team_stats`: 2 rows, fixture-linked identically to player_stats. |
| **Odds history** | **REAL + ACTIVE** | `odds_snapshots`: 138 rows (134 real + 4 original fixture), `cron-odds-worker` running continuously, real credit-guarded quota (Phase 7). |
| **News history** | **REAL + ACTIVE** | `news_article_history`: 97 rows, `cron-news-worker` running at the approved 4-hour cadence with a durable, concurrency-safe 80/day quota guard (Pass 2.2). |
| **Weather history** | **REAL + ACTIVE, as of this pass** | `weather_snapshots`: 4 rows (1 fixture + 3 real, this pass), `cron-weather-worker` just created and confirmed SUCCESS, first real tick due within 15 minutes of this report. |
| **Game events/PBP** | **MISSING/INSUFFICIENT** (blocked by real-world timing, not by us) | `game_events`: 0 rows. Real, deliberately raw-capture-only persistence code exists (`app.persistence.game_events`), explicitly deferred pending the 2026-09-09/10 live-game validation window (`docs/ops/nfl-provider-decision-record.md`) that simply hasn't arrived yet — this is the one dimension genuinely blocked by the calendar, not by any decision or credential. |
| **Venue/context metadata** | **REAL + ACTIVE** | `venues`: 5 rows, real WebSearch-verified coordinates (Pass 2), sport-agnostic canonical architecture, directly reused by this pass's own Weather activation with zero redesign. |

## 8. Phase 8.0.5 closeout verdict (A)

**Yes, closeable — with two dimensions explicitly carried forward as named, disclosed debt, not silently dropped.** Phase 8.0.5's own stated purpose (per its own founding audit, 2026-09-07 morning) was closing the "specialized-worker runtime gap" so real comparable evidence could exist before Phase 8.1 tries to validate against it. That gap is now closed for every worker where a real, live provider path exists: Odds, News, Weather, and BALLDONTLIE Injuries (code-complete, entitlement-blocked, not a runtime gap). Roster/depth-chart and player/team stats remain real gaps, but they are gaps in *provider activation*, not in *this milestone's own scope* (5.6/Depth Chart activation was never phase-gated into 8.0.5, and player/team stats real capture depends on the still-reserved final SportsDataIO call, an explicit, previously-made decision, not an oversight).

## 9. Phase 8.1 readiness verdict (B, C, D)

**B: Enough real substrate exists to begin Phase 8.1 honestly for SOME contextual dimensions — not all.** Building the full 17-agent committee against real data today would still mean fabricating evidence for roster/depth/player-stats/team-stats/PBP-dependent agents. Building only the dimensions with real, active data is legitimate and honest; building the rest against fixtures and presenting it as real would not be.

**C: Contextual dimensions implementable honestly right now:**
- Odds-derived agents (Vegas Line, Closing Line Movement, Sharp Money, Line Value) — real, active, append-only history already exists.
- News-derived agents (any sentiment/injury-mention/momentum signal sourced from real headlines) — real, active, growing every 4 hours.
- Weather-derived agents (Weather score, any dome/outdoor-conditioned logic) — real, active as of this pass, growing every 15 minutes.
- Venue/travel-context agents that only need real coordinates/venue metadata (Travel & Fatigue's location-distance component) — real, active.

**D: Dimensions that must remain insufficient-evidence until real data arrives:**
- Any player-level agent (Player Prop Agent, Offensive/Defensive Matchup, injury-severity-by-player reasoning) — blocked on real `players`/`player_provider_ids`/roster data, none of which exists.
- Any stats-driven agent (recent-form, matchup-strength-by-statistical-profile) — blocked on real `player_stats`/`team_stats`, currently 100% fixture.
- Any PBP/game-script-aware agent — blocked on `game_events`, genuinely zero real rows, and additionally blocked on the calendar (2026-09-09/10 validation window hasn't happened yet).
- Depth-chart-aware reasoning (starter/backup-sensitive logic) — blocked on `roster_memberships`/`depth_chart_snapshots`, zero real rows.

## 10. Remaining mandatory Beta blockers (E)

Distinguishing genuinely mandatory-before-Phase-12-Beta from merely enrichment debt:

**Mandatory before Beta** (the product's core trust claims depend on these, not optional polish):
1. **Real player/roster identity** (`player_provider_ids`, real `roster_memberships`) — without this, no player-level recommendation can be honestly attributed to a real player at all.
2. **Real player/team stats capture** — currently gated on the single remaining reserved SportsDataIO call (an explicit, prior decision, not new information this pass) or an equivalent BALLDONTLIE/other-provider path; either way, real recent-form data is load-bearing for any credible recommendation, not enrichment.
3. **BALLDONTLIE Injuries entitlement resolved** (or an equivalent real injury source) — injury status is one of the most commonly cited real factors in sports betting reasoning; shipping without it, or worse, silently omitting it, undermines the product's own stated trust claim.

**Enrichment debt, not mandatory before Beta:**
1. **Game events/PBP** — genuinely valuable for advanced/in-game features, but the roadmap's own Phase 5 Time Machine reproducibility test (the single most important test per the roadmap) does not require live in-game PBP to pass; pregame recommendation quality does not structurally depend on this.
2. **Depth-chart-aware reasoning** — a real enhancement to player-availability reasoning, but not load-bearing if player-level agents are already correctly gated as insufficient-evidence per §9D above.
3. **Multi-sport (NBA, etc.) expansion** — explicitly out of scope per this pass's own locked architecture rule; not a Beta blocker for the NFL-focused launch.

---

## Multi-sport architecture rule — held, not touched

Canonical `venues` (sport-agnostic since Pass 2) was reused by this pass's Weather activation with **zero redesign** — the exact proof point the rule's own rationale predicted. No NBA implementation begun. The one NFL-specific choice this pass's own new code makes (none, in fact — Weather Worker's game-keyed, coordinate-driven design was already sport-agnostic by construction, unlike the `_SPORT_PATH`/`_SPORT_QUALIFIER` constants Pass 2 had to extract for BALLDONTLIE/GNews) required no new "single edit point" constant at all.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call untouched); no staging/prod changes; no Phase 7.2/7.3; no Phase 8.1 implementation (this report's own closeout section is analysis, not implementation); no Phase 4; no Milestone 5.6; no invented data (SoFi `is_dome=null` held exactly as instructed); no unnecessary provider spend (3 real WeatherAPI calls total this entire pass, quota analysis showing a dedicated guard would be unneeded manufactured protection). Temporary diagnostic (`app/diagnostics/weather_activation_proof.py`, its `__init__.py`, and the gated `main.py` hook) fully reverted after the live proof, confirmed via a clean post-revert deploy log; `RUN_WEATHER_ACTIVATION_PROOF` reset to `"0"`.
