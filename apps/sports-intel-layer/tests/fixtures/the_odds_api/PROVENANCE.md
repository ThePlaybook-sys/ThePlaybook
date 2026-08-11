# The Odds API fixture provenance

Every fixture in this directory represents a *hypothetical* provider response used
to test `app/adapters/providers/the_odds_api.py` deterministically, without a live
API key (Phase 3B, fixture-first strategy approved 2026-08-11 — see PROGRESS.md).

None of these were captured from a real live call — this sandbox's egress policy
blocks `the-odds-api.com` (confirmed via the proxy's own status endpoint, see
PROGRESS.md's 2026-08-11 entry). Two provenance tiers apply, per file below:

- **CONFIRMED** — the underlying mechanic was verified against the provider's own
  documentation during this project's 2026-08-10 credit-usage projection (see
  PROGRESS.md): the bulk `/odds` endpoint costs `markets × regions` per call
  regardless of event count; the event-specific `/events/{id}/odds` endpoint
  (required for player props) costs the same `markets × regions` per game, per
  call; `/events` listing is free.
- **ASSUMED** — everything else: exact JSON field names, the
  events → bookmakers → markets → outcomes nesting shape, the NFL sport key
  (`americanfootball_nfl`), specific sportsbook keys, error response bodies,
  and header names. These reflect the provider's long-published public API shape
  from general knowledge, but were **not** independently re-verified via a live
  fetch this session. Anything ASSUMED must be checked against a real response
  the first time a live key is available, before being treated as fact — see the
  DEFERRED — FINANCIAL/EXTERNAL DEPENDENCY checklist in PROGRESS.md.

## Fixture-by-fixture

| File | Scenario | Tier |
|---|---|---|
| `bulk_odds_multi_game.json` | 3 NFL games, h2h/spreads/totals, 3 sportsbooks | ASSUMED shape, CONFIRMED cost model |
| `bulk_odds_missing_suspended_markets.json` | one book with no markets, one book missing entirely | ASSUMED |
| `bulk_odds_line_movement_t1.json` / `_t2.json` | same game/book/market, price + `last_update` changed between snapshots | ASSUMED |
| `bulk_odds_partial_data.json` | response covers only some of the requested game ids | ASSUMED |
| `player_props_event.json` | single event, player-prop markets, multiple books, Over/Under pairs | ASSUMED shape, CONFIRMED cost model (per-game call) |
| `player_props_missing_market.json` | event where none of the requested prop markets are offered | ASSUMED |
| `malformed_payload.json` | deliberately broken (missing required `id`/`key` fields) — not a provider claim of any kind, a defect-injection fixture | N/A — synthetic |
| `error_401.json`, `error_429.json` | vendor error response bodies | ASSUMED |

Nothing here is invented and then treated as provider fact in the adapter or its
tests — the adapter's own docstring carries the same CONFIRMED/ASSUMED split.
