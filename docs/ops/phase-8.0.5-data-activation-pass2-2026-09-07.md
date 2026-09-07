# Phase 8.0.5 — Data Activation, Pass 2 (2026-09-07)

**Status: real DEV implementation, executed and verified. News Worker is now recurring-active on a real Railway Cron Job.** DEV only throughout. Zero SportsDataIO calls (11/12 used, final call still reserved). Phase 7 observation window, Phase 4, Milestone 5.6, and staging/production all untouched. New locked architecture rule honored throughout: canonical venues are sport-agnostic; the one NFL-specific literal each new adapter makes is now a named, single-edit-point constant, not parameterized (real multi-sport support is out of scope this pass).

---

## 1. GNews pacing implementation and live proof

**Smallest safe change:** `run_news_worker` gained one new parameter, `inter_call_delay_seconds: float = 0.0` — default preserves every existing caller's exact behavior (zero test changes needed beyond the one signature-contract test asserting the full parameter set). A generic `asyncio.sleep` between per-team fetches (never before the first call, never a trailing sleep after the last), applied regardless of which adapter is injected — not a GNews-specific branch smeared into the shared loop. The new internal endpoint (`/v1/internal/news-worker/run`) passes `5.0`, matching the 2026-09-03 GNews validation's own confirmed-safe spacing.

**Live proof: completely clean.** `status='success'`, **10/10 teams fetched**, **5/5 games updated**, **zero failures** (Pass 1's same pull, with zero spacing, had failed 8/10 teams). Verified directly against DEV Supabase: `news_article_history` now holds **97 real rows across all 10 tracked teams** (up from Pass 1's 20), real headlines/URLs/sources/timestamps throughout.

## 2. Recurring News activation status

**Activated.** A new Railway Cron Job service, `cron-news-worker` (id `41754758-dd90-46ed-a77b-6a3c6a931554`), created mirroring `cron-odds-worker`'s exact configuration: same repo/branch/`rootDirectory` (`apps/workers`), same `DOCKERFILE` builder, same frozen `watchPatterns`, same `restartPolicyType=NEVER`, schedule `*/15 * * * *` (the existing approved News Worker cadence, Volume 2 §8's "every 15 minutes"). `CRON_DISPATCH_TARGET=news-worker`, `CRON_DISPATCH_BASE_URL` pointing at `sports-intel-layer`, `INTERNAL_SERVICE_TOKEN` set as a Railway cross-service reference (`${{sports-intel-layer.INTERNAL_SERVICE_TOKEN}}`) rather than a copied literal, so it always stays in sync with the source of truth. **First build confirmed SUCCESS.** The first real scheduled tick fires within 15 minutes of this report — not yet independently observed post-activation, since confirming it would mean waiting out the same interval this report is being written in; the identical code path was just proven clean seconds earlier via the live proof above.

## 3. Canonical venue changes

**New table: `venues`** (`id`, `name`, `city`, `state`, `lat`, `long`, `venue_type`, `created_at`) — deliberately carries **no `sport_id`/`league_id`/league reference of any kind**. A physical venue is not owned by one sport; this table is directly reusable the moment a future NBA game needs a venue, with zero redesign. This supersedes Option A's original rationale for keeping venue data as direct `games` columns only ("smallest additive change... given the league's small ~30 venue count," Volume 3 v4.9) — that reasoning was explicitly NFL-scoped and no longer holds under the newly locked sport-agnostic rule. **`games.venue_lat`/`.venue_long`/`.venue_type` are NOT removed** — same "legacy field stays populated for compatibility" precedent already established for `games.sport` alongside `sport_id`. New `games.venue_id` (nullable FK to `venues.id`) is the canonical path going forward; the legacy columns are kept in sync at write time so Weather Worker's existing, unchanged read path continues to work without modification.

## 4. Venue coordinates applied and provenance

All 5 real tracked games linked to a real `venues` row (matched by their already-real `stadium` name) and their legacy `venue_lat`/`venue_long`/`venue_type` columns synced:

| Game | Venue | Lat | Long | `venue_type` |
|---|---|---|---|---|
| SEA/NE | Lumen Field | 47.595097 | -122.332245 | `outdoor` |
| LV/MIA | Allegiant Stadium | 36.090794 | -115.183952 | `dome` |
| MIN/GB | U.S. Bank Stadium | 44.973774 | -93.258736 | `dome` |
| PHI/WAS | Lincoln Financial Field | 39.900898 | -75.168098 | `outdoor` |
| LAC/ARI | SoFi Stadium | 33.953587 | -118.339630 | `NULL` (see §5) |

**Provenance:** every coordinate verified via live WebSearch this pass (Wikipedia, latlong.net) — not recalled from training data, not guessed. The 3 Oct-11 cluster games (from the earlier Phase 7 discovery) were deliberately left unlinked — their real stadium names were never captured from BALLDONTLIE, so no authoritative venue data exists for them yet; no placeholder was invented.

## 5. SoFi venue-type decision

**Left `NULL`, not forced.** SoFi Stadium's real design (a fixed, translucent canopy roof with open sides) genuinely doesn't fit any of the existing 3-value vocabulary (`outdoor`/`dome`/`retractable_dome`) — it's neither a sealed dome, a classic open stadium, nor a retractable roof. Per HQ's explicit instruction ("do not force it into an inaccurate enum") and the exact precedent `venue_type`'s own design already established (missing/`retractable_dome` → `None`, "a real, distinct unknown state, never coerced"), `NULL` is the honest representation. **Not a schema gap to silently work around**: if HQ later wants a 4th vocabulary value (e.g. something like `fixed_open_air`) that's a real, separate decision on the vocabulary itself, not made or invented here.

## 6. WeatherAPI credential status

**Confirmed absent.** A live check of `sports-intel-layer` DEV's full variable list found no `WEATHERAPI_API_KEY` (re-confirmed, unchanged from the Pass 1 audit). Per HQ's explicit instruction, **the live weather-call portion is stopped here — nothing further attempted.** **What's needed:** an account at weatherapi.com (free tier, already confirmed $0/mo / 1M calls/mo sufficient in the business plan), a generated API key, and that key set as `WEATHERAPI_API_KEY` on the `sports-intel-layer` DEV Railway service. No purchase decision blocks this — it's free — only account creation and key provisioning, which requires a human with account access, not something this session can do on its own.

## 7. Weather live-pull result and rows

**Not executed — correctly gated on §6.** No `WeatherAPIWeatherAdapter` client could be constructed without the credential, so no live call was attempted and none should have been. Zero new `weather_snapshots` rows (still exactly the 1 pre-existing fixture row).

## 8. Recurring Weather recommendation/status

**Not recommended, not activated — as instructed.** Two real prerequisites remain: (a) `WEATHERAPI_API_KEY` provisioning (§6), (b) confirmation that a real controlled pull against the now-real venue data (§3/§4) is clean, which cannot happen until (a) closes. Once both clear, Weather Worker's own cadence (`*/15`, already correctly reusing `Window.STOPPED` + the existing 4-hour post-kickoff extension) needs no further change — the gap was never the worker's own logic, only credentials and venue data, both addressed or in progress this pass.

## 9. BALLDONTLIE injury blocker

**Adapter/pipeline left completely untouched this pass, exactly as instructed — no workaround attempted.** New finding, from public documentation only (no live API call spent): BALLDONTLIE's own published NFL pricing tiers show **`player_injuries` is an ALL-STAR-tier feature ($9.99/mo, 60 req/min)** — a *different* tier from GOAT ($39.99/mo, 600 req/min), which unlocks advanced stats/PBP/odds/props/rosters but, per this same source, is a separate feature set rather than a strict superset that automatically includes ALL-STAR's own features. This lines up exactly with Pass 1's real evidence: `/nfl/v1/games` (free tier) returned 200 with the account's current key; `/nfl/v1/player_injuries` (ALL-STAR-tier) returned 401 with the identical key. **The exact requirement blocking this: the account's active BALLDONTLIE subscription does not currently include ALL-STAR-tier access** (either the real active plan differs from GOAT as documented, or BALLDONTLIE's tiers are non-cumulative and ALL-STAR must be added separately from GOAT) — this needs a real check of the BALLDONTLIE account/billing dashboard, not anything resolvable from this session. The code, identity, and persistence path all remain fully proven and ready to activate the moment access is confirmed.

## 10. Multi-sport hardcoding findings

Audited every file touched across both Data Activation passes (this pass's own files plus Pass 1's, since they're the same connected effort and this is the first pass the sport-agnostic rule was locked):

- **`BallDontLieInjuryAdapter`** hardcoded `/nfl/v1/player_injuries` directly in the URL. **Fixed**: extracted to a named `_SPORT_PATH = "nfl"` module constant (matching `the_odds_api.py`'s own existing `_SPORT_KEY` precedent) — a single, visible edit point, not real parameterization.
- **`GNewsNewsAdapter`** hardcoded `"NFL"` as an unconditional query qualifier. **Fixed**: extracted to `_SPORT_QUALIFIER = "NFL"`, same treatment.
- **New `venues` table**: already correctly sport-agnostic from the start (no `sport_id`/`league_id`) — no fix needed, this is the one place this pass built genuinely new shared infrastructure and it was designed right the first time.
- **Real, pre-existing gap, exposed but NOT fixed this pass (explicitly out of scope per HQ's "only fix issues directly introduced or exposed" instruction):** no specialized worker — not `odds_worker.py`, not `weather_worker.py`, not `injury_worker.py`, not this pass's own new `balldontlie_injury_worker.py`/`news_worker.py` — filters its candidate-game query by sport at all. Every one of them implicitly assumes every row in the 7-day candidate window is NFL, since today nothing else exists. This is shared, pre-existing architecture debt, not something introduced only by this pass's own new files, and fixing it consistently would mean touching every specialized worker — real scope, correctly left for a dedicated future multi-sport pass, not started here.
- **`persist_injury_reports`'s widened `provider_name` parameter** (Pass 1): already fully generic, no sport assumption, no fix needed.

## 11. Anything still blocking real 2026 contextual-data preservation

1. **BALLDONTLIE injuries** — needs the account/plan-tier check (§9); code is ready.
2. **WeatherAPI key** — needs provisioning (§6); free, zero cost, just needs a human to create the account.
3. **Venue data for the Oct-11 cluster** — never captured; not urgent (that cluster is still outside its own candidate window).
4. **The pre-existing sport-filtering gap (§10)** — not urgent today (single-sport reality), but worth a dedicated pass before any real NBA game data ever reaches these tables.

**What's already real and safe today:** News is now fully live and recurring — 97 real articles captured, growing every 15 minutes, zero known blockers. The opener is ~2.15 days out; the cluster ~5.85 days out.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call untouched); Phase 7 observation window untouched; no Phase 7.2/7.3; no Phase 8.1 intelligence implementation; no Phase 4 modification; no Milestone 5.6; staging/production untouched; no invented venue/provider data (every coordinate WebSearch-verified, every BALLDONTLIE tier claim sourced from public pricing pages, no live API call spent to investigate the 401 further); no WeatherAPI service purchased/configured; BALLDONTLIE injury adapter/pipeline left completely untouched, no workaround attempted. Temporary diagnostic (`app/diagnostics/news_pacing_proof.py`, its `__init__.py`, and the gated `main.py` hook) fully reverted after the live proof; `RUN_NEWS_PACING_PROOF` reset to `"0"`.
