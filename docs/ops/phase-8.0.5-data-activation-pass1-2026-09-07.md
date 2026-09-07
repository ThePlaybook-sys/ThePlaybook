# Phase 8.0.5 — Data Activation, Pass 1 (2026-09-07)

**Status: real DEV implementation, executed and verified. No recurring polling activated — per HQ's explicit "no recurring external-API polling until the controlled live proof succeeds," and the proof succeeded only partially (see below).** DEV only throughout. Zero SportsDataIO calls (11/12 used, final call still reserved). Phase 7 observation window, Phase 4, Milestone 5.6, and staging/production all untouched.

---

## 1. News credential/provider verification

**`GNEWS_API_KEY` is configured on `sports-intel-layer` DEV; `NEWSAPI_API_KEY` is not** (both re-confirmed live before writing any code). **No `GNewsNewsAdapter` existed anywhere in the real codebase** — the only prior GNews code was the 2026-09-03 validation's own temporary diagnostic, already fully reverted. This is the precise finding the directive's own contingency anticipated ("if the GNews credential truly is not configured... STOP"): the *credential* was configured, but the *adapter code* to use it did not exist. Per HQ's direct instruction this turn ("use the existing GNews DEV path, not NewsAPI"), a real, permanent `GNewsNewsAdapter` was built — not a provider-decision change: `news_worker.py`'s own hardcoded default (`NewsAPINewsAdapter`) is completely untouched, and GNews is used only via the worker's pre-existing `news_adapter` dependency-injection seam, at the new internal endpoint's own call site. Volume 2 §8's NewsAPI-vs-GNews decision remains exactly as undecided as before.

## 2. News live-pull result and rows written

**Real, substantial success, with a real rate-limit constraint surfaced.** First live pull: `teams_fetched=2` (of 10 due), `games_updated=2`, **`history_rows_written=20`**, 8 teams failed with `rate limited`. Verified directly against DEV Supabase: **20 real `news_article_history` rows**, real headlines/URLs/sources/publish timestamps, correctly team-attributed (e.g. New England Patriots and Arizona Cardinals articles correctly linked to their real `team_id`s). A second pull (run to test the BALLDONTLIE comparison call, see §3) correctly wrote **zero new rows** for already-seen articles — the `(provider_name, article_url)` unique index deduping exactly as designed — and fetched 1 additional new team's worth of real, non-duplicate data.

**Root cause of the 8 failures: GNews's own real, aggressive rate limit** — the same behavior the 2026-09-03 validation already found ("Run 1... hit 4/9 calls rate-limited despite Essential's documented 10 req/sec limit"). `run_news_worker`'s existing loop calls `fetch_news` sequentially per team with no inter-call pacing at all — fine for NewsAPI's own limits, not for GNews's real behavior under this key's current plan.

**Recurring activation verdict: not safe yet, as-is.** The pull mechanism, identity resolution, and persistence are all proven genuinely real and correct end-to-end — but a full 10-team cycle would hit real rate limits every time under the current plan/pacing. Recommend adding inter-call pacing (or a smaller per-cycle team batch) to the News path before proposing a recurring schedule — a small, scoped fix, not a redesign.

## 3. BALLDONTLIE injury adapter implementation

Built exactly as designed in the Phase 8.0.5 audit: `BallDontLieInjuryAdapter` (new, real `InjuryAdapter`) calling `nfl/v1/player_injuries`, constructor-scoped to an explicit `team_ids` list plus an injected `game_external_id_for_team_id` resolver (BALLDONTLIE injury rows carry no game reference at all, confirmed from the official package source — the adapter stays a thin translation layer, the new `run_balldontlie_injury_worker` resolves identity). `persist_injury_reports` widened with an explicit `provider_name` parameter (default unchanged) so this second real provider persists through the same, already-tested function rather than a duplicate. A deliberately separate module from `injury_worker.py` — the existing SportsDataIO path (and the reserved trial call it protects) is completely untouched.

Additive migration applied to DEV: `'balldontlie'` added to `game_provider_ids`/`team_provider_ids`' `provider_name` CHECK constraints. Real, session-confirmed identity seeded: `team_provider_ids` for the 10 real teams across the 5 tracked games, `game_provider_ids` for all 5 games — all using the exact real BALLDONTLIE numeric ids this session's own earlier schedule-discovery probe already captured (no new discovery call spent).

## 4. Injury live-pull result and rows written

**Identity resolution: 5/5 games linked, 10/10 teams resolved — perfect.** **The actual injuries fetch failed with a real 401 ("invalid or missing API key").** A single, targeted follow-up call — the identical credential against `/nfl/v1/games` (the same endpoint this session's earlier schedule-discovery probe already used successfully) — **returned 200 OK**, in the same deploy, same process. **This conclusively proves the credential itself is valid; the 401 is specific to the `player_injuries` endpoint**, not a broken or missing key. **Zero injury_reports rows were written** (still exactly 1 — the pre-existing fixture row, untouched) — the fetch failure occurred before persistence was ever reached, so there is no partial or contaminated write to clean up.

**This is a real, disclosed discrepancy against the 2026-09-03 bake-off's own finding**, which reported this exact endpoint as GREEN ("real, specific, non-scrambled descriptions") on the same credential. Something has changed since then — the account's plan/tier, or the specific access this endpoint requires — that this session cannot diagnose further without either BALLDONTLIE account/dashboard access or spending additional real calls on speculative retries, neither of which is authorized by this pass. Flagged for HQ, not guessed past.

## 5. Identity-resolution results

Both providers' identity chains resolved perfectly in the real pulls: BALLDONTLIE's team+game linkage (5/5 games, 10/10 teams) and GNews's team-level resolution (all 10 real teams resolved via the existing 32/32 `sportsdataio` `team_provider_ids` coverage — no gap here at all). The News path's `teams_unresolved` came back empty on both real pulls. Identity was never the blocker for either provider this pass — credentials/endpoint-access were.

## 6. Venue/coordinate solution

**Smallest authoritative approach, identified and sourced, not yet applied (per this pass's own report-only scope for Weather):** a static, public NFL stadium coordinate lookup — the same epistemic tier as this project's own `TEAM_BACKFILL` (public, standard, verifiable facts, never fabricated), matched against the real stadium names already captured from BALLDONTLIE's own schedule response and already stored on these games' `stadium` column. Verified via WebSearch this pass (Wikipedia/latlong.net), not recalled from memory:

| Game | Stadium | Lat | Long | `venue_type` |
|---|---|---|---|---|
| SEA/NE | Lumen Field | 47.595097 | -122.332245 | `outdoor` |
| LV/MIA | Allegiant Stadium | 36.090794 | -115.183952 | `dome` (fixed, fully enclosed) |
| MIN/GB | U.S. Bank Stadium | 44.973774 | -93.258736 | `dome` (fixed roof) |
| PHI/WAS | Lincoln Financial Field | 39.900898 | -75.168098 | `outdoor` |
| LAC/ARI | SoFi Stadium | 33.953587 | -118.339630 | **genuinely unclassifiable** under this schema's current 3-value vocabulary (`outdoor`/`dome`/`retractable_dome`) — a fixed canopy roof with open sides, neither a sealed dome nor a retractable one. Recommend `NULL` (an honest "unknown," matching the existing `retractable_dome`-or-missing precedent) rather than forcing it into either category. |

**Not applied this pass** — a one-line `UPDATE games SET venue_lat=..., venue_long=..., venue_type=...` per game, ready for HQ's go-ahead.

## 7. WeatherAPI recommendation/cost

**Correction to the prior Phase 8.0.5 audit's own finding: a WeatherAPI budget line DOES already exist.** `docs/business/mansa-business-entitlement-plan-2026-09-03.md` confirms: **"$0/mo — CONFIRMED... free-tier capacity (WeatherAPI: 1M calls/mo) is sufficient."** WeatherAPI is also the vendor the real, already-built `WeatherAPIWeatherAdapter` code already targets (OpenWeatherMap/OpenWeather are documented fallback/candidate alternatives, not yet needed). **Recommendation: provision a free-tier `WEATHERAPI_API_KEY` — zero cost, no purchase decision blocking this.** The only real blocker to Weather Worker activation is the missing credential itself plus the venue-coordinate gap above — not cost.

## 8. Proposed recurring schedules after proof

**News:** proceed only after adding inter-call pacing (matching the 2026-09-03 validation's own 5s-spacing fix) or reducing per-cycle team batch size — then `*/15 * * * *`, matching the existing flat interval. **Not yet safe to schedule as-is.**

**BALLDONTLIE Injuries:** blocked entirely on resolving the real 401 (§4) — HQ needs to check the BALLDONTLIE account/plan for `player_injuries` access before any schedule is proposed. The code, identity, and persistence path are all proven ready the moment the credential/access issue is resolved.

**Weather:** not proposed this pass, per HQ's explicit instruction — the coordinate gap (§6) and credential provisioning (§7) both need to close first.

## 9. Anything blocking preservation before the opener

1. **BALLDONTLIE injuries access** — needs HQ/account-level resolution (§4); the code is ready.
2. **GNews rate-limit pacing** — needs a small, scoped fix to `news_worker.py`'s call loop before recurring activation is safe; the underlying pull and persistence are already proven real.
3. **WeatherAPI key provisioning** — free, zero cost, simply not yet requested/configured.
4. **Venue coordinates** — identified and sourced (§6), one small additive write away from closing.

None of these block what's already real and captured: **20 real news articles with correct team attribution are already preserved**, and the identity/persistence scaffolding for BALLDONTLIE injuries is fully proven and ready to activate the moment access is resolved. The opener is ~2.2 days out; the cluster ~5.9 days out.

---

**Guardrails held throughout:** DEV only; zero SportsDataIO calls (11/12 used, final call untouched); Phase 7 observation window untouched; no Phase 7.2/7.3; no Phase 8.1 intelligence implementation; no Phase 4 modification; no Milestone 5.6; staging/production untouched; no provider capability invented (BALLDONTLIE/GNews endpoint shapes carried forward from already-confirmed sources, stadium coordinates verified via live WebSearch against public records, not recalled); no new paid weather service purchased or configured; no recurring cron service created for either newly-built path. Temporary diagnostic probe (`app/diagnostics/data_activation_pass1_proof.py`, its `__init__.py`, and the gated `main.py` hook) fully reverted after both real pulls completed; `RUN_DATA_ACTIVATION_PASS1_PROOF` reset to `"0"`.
