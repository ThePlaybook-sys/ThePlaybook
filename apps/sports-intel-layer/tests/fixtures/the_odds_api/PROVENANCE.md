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

## Row isolation (2026-08-18, Data Dictionary reconciliation corrective pass)

Found and fixed as part of a broader row-isolation sweep prompted by the
SportsDataIO Schedule status fix (same day): `TheOddsApiOddsAdapter.fetch_odds`
and `TheOddsApiPlayerPropsAdapter.fetch_player_props` both wrapped their entire
event-parsing loop in one try/except, so one malformed event/bookmaker/market/
outcome anywhere in the response aborted the whole call — for `fetch_odds`,
that meant every game in the bulk multi-game response; for `fetch_player_props`,
every game in that cycle's batch, despite each game already being its own HTTP
call.

**Fixed with the same defensive philosophy as the Schedule fix, no vendor-shape
assumptions changed:**
- `fetch_odds`: two isolation tiers — a malformed event (missing id/teams/
  commence_time) is logged and skipped; a malformed market within an
  otherwise-valid event is logged and skipped, that event's other valid
  markets still process.
- `fetch_player_props`: three isolation tiers — a malformed event (one game's
  own HTTP response) is logged and skipped, moving on to the next game_id; a
  market with no usable `outcomes` is logged and skipped; a malformed
  individual outcome is logged and skipped, the market's other valid
  Over/Under pairs still process.
- HTTP failure, invalid top-level JSON, and non-array/non-object payloads
  still fail the whole call, unchanged — no change to `_get`/
  `_parse_json_array`/`_parse_json_object`.
- **Known characteristic, not a defect:** a malformed field that fails *after*
  a `PlayerProp` has already been created for a given (bookmaker, market,
  player, point) key (e.g. a missing `price` on the very first outcome seen
  for that key) leaves that prop in the result with the affected side
  (`over_odds`/`under_odds`) still `None` rather than removing the whole
  entry — consistent with the model's own optional-field design and the
  null-not-neutral convention, not fabricated data. Isolation guarantees no
  *other* valid prop is lost; it does not retroactively undo a partial
  mutation already made to an in-progress record.

`malformed_payload.json`'s own tier note above is unaffected — the fixture
still deliberately breaks a required field, it now demonstrates isolation
(logged, skipped, empty result) rather than a raised exception.
