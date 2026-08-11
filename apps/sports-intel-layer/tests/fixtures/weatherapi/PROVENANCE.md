# WeatherAPI fixture provenance

None of these were captured from a real live call — this sandbox's egress policy
blocks `weatherapi.com` (same restriction as `the-odds-api.com` and
`sportsdata.io`, confirmed via the proxy's own status endpoint before concluding
fixtures were the only option). Three tiers apply, per Mac's 2026-08-11 instruction:

- **CONFIRMED** — verified against the provider's own documentation this session.
  Nothing in this vendor's fixtures reaches this tier yet (unlike The Odds API's
  credit-formula research in Phase 3B) — flagged explicitly rather than implied.
- **ASSUMED** — reflects WeatherAPI's long-published public API shape from
  general knowledge, not independently re-verified via a live fetch this
  session: the `forecast.json` endpoint shape (`location`/`current`/
  `forecast.forecastday[].hour[]`), the `error.code` field and specific auth
  codes (1002/2006/2007/2008/2009) used to distinguish a bad key from a bad
  request on an HTTP 400 (WeatherAPI is known to return 400, not a clean 401,
  for most key problems — the exact mechanism is ASSUMED), and the 3-day
  forecast window used in requests.
- **DEFERRED LIVE VERIFICATION** — cannot be resolved without a real key:
  real authentication, the actual live payload shape, real quota/rate-limit
  behavior and headers, real latency, and a fixture-vs-live diff. Tracked
  centrally in `PROGRESS.md`'s DEFERRED — FINANCIAL/EXTERNAL DEPENDENCY
  checklist, not just here.

## Fixture-by-fixture

| File | Scenario | Tier |
|---|---|---|
| `forecast_normal.json` | current + one forecast day with hourly entries bracketing kickoff | ASSUMED |
| `forecast_outside_window_falls_back_to_current.json` | empty `forecastday` (kickoff beyond the forecast horizon) — adapter falls back to `current` | ASSUMED |
| `forecast_malformed.json` | forecast hour missing `temp_f` | N/A — synthetic defect-injection fixture |
| `error_400_bad_key.json` | HTTP 400, `error.code: 2006` (ASSUMED auth code) | ASSUMED |
| `error_400_bad_location.json` | HTTP 400, `error.code: 1006` (ASSUMED "no location found" code, not an auth error) | ASSUMED |

## A note on `WeatherAdapter`'s missing location parameter

`fetch_weather(game_external_id, kickoff)` (3A) doesn't carry a location — this
adapter's constructor takes an injected `location_for_game` resolver instead,
so the shared 3A interface didn't need to change. In production that resolver
would read `games.stadium`, which is Milestone F's job, not built here. See the
adapter module's own docstring for the full explanation.
