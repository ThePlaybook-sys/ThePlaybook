"""The Odds API adapters (Volume 2 §8, Phase 3B).

Implements `OddsAdapter` and `PlayerPropsAdapter` against The Odds API's
documented v4 REST contract -- two separate adapter classes, one per
DataCategory, sharing an HTTP client (per `base.py`'s own guidance: "that
vendor gets one adapter class per category ... not one adapter answering
for several categories at once").

Provenance of what's below, since Mac's explicit instruction is to never
present an assumption as vendor fact:

- The credit-cost mechanics (bulk `/odds` costs markets x regions per call
  regardless of event count; the event-specific `/events/{id}/odds`
  endpoint costs the same per game, per call; `/events` listing is free)
  are CONFIRMED -- verified against the provider's own documentation during
  this project's 2026-08-10 credit-usage projection (see PROGRESS.md).
- Everything else here -- exact JSON field names, the shape of
  bookmakers/markets/outcomes, the sport key, error response bodies,
  header names -- is ASSUMED: it reflects this provider's long-published,
  stable public API shape, but has not been independently re-verified via
  a live fetch in this session (this sandbox's egress policy blocks
  the-odds-api.com; see PROGRESS.md's DEFERRED checklist). Anything ASSUMED
  is marked inline so a real key can correct it on first live contact
  without ambiguity about what was actually checked versus recalled.

The HTTP client is injected (`client: httpx.AsyncClient`) so tests can
point it at a mocked transport (respx-backed fixtures today) or the real
network (once a key exists) -- this module never special-cases "am I under
test," and swapping the transport is the only thing that changes.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.adapters.base import OddsAdapter, PlayerPropsAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, OddsLine, PlayerProp

#: ASSUMED: NFL's sport key on this provider.
_SPORT_KEY = "americanfootball_nfl"

#: Vendor market key -> odds_snapshots.market_type ('moneyline'|'spread'|
#: 'total'|'prop', per Volume 3 §4 / models.py's OddsLine docstring).
#: ASSUMED: h2h/spreads/totals are the provider's stable bulk-odds market
#: keys.
_BULK_MARKET_TYPE = {
    "h2h": "moneyline",
    "spreads": "spread",
    "totals": "total",
}
_BULK_MARKETS = tuple(_BULK_MARKET_TYPE)

#: ASSUMED: 5 representative player-prop markets, matching the set already
#: used in the 2026-08-10 credit-usage projection (PROGRESS.md) -- not a
#: provider-confirmed enumeration of every market the vendor offers.
_PLAYER_PROP_MARKETS = (
    "player_pass_tds",
    "player_pass_yds",
    "player_rush_yds",
    "player_reception_yds",
    "player_receptions",
)

_logger = logging.getLogger("sports-intel-layer.adapters.the_odds_api")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _slugify(name: str) -> str:
    """ASSUMED fallback: The Odds API's player-prop outcomes carry a
    player name (`description`) but no vendor player id -- there is nothing
    to normalize into `player_external_id` except the name itself. Flagged
    explicitly rather than silently treating a slugified name as a real
    vendor identifier; downstream name-matching against our own `players`
    table is a known open item, not solved here."""
    return name.strip().lower().replace(" ", "-").replace(".", "").replace("'", "")


async def _get(
    client: httpx.AsyncClient, path: str, *, params: dict, provider_name: str
) -> httpx.Response:
    """Shared HTTP call + error translation for both adapters below -- the
    actual enforcement point of "no vendor-specific exception escapes an
    adapter" (errors.py's own stated contract)."""
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(
            f"transport error calling {path}: {exc}", provider=provider_name
        ) from exc

    if response.status_code == 401:
        raise ProviderAuthError("invalid or missing API key", provider=provider_name)
    if response.status_code == 429:
        # ASSUMED: header name/presence for retry guidance -- not confirmed.
        retry_after = response.headers.get("Retry-After")
        raise ProviderRateLimitError(
            "rate limited",
            provider=provider_name,
            retry_after_seconds=float(retry_after) if retry_after else None,
        )
    if response.status_code >= 500:
        raise ProviderUnavailableError(
            f"provider returned {response.status_code}", provider=provider_name
        )
    if response.status_code != 200:
        raise ProviderDataError(
            f"unexpected status {response.status_code}: {response.text}", provider=provider_name
        )
    return response


def _parse_json_array(response: httpx.Response, *, provider_name: str) -> list[dict]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderDataError("response body was not valid JSON", provider=provider_name) from exc
    if not isinstance(data, list):
        raise ProviderDataError("expected a JSON array of events", provider=provider_name)
    return data


def _parse_json_object(response: httpx.Response, *, provider_name: str) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderDataError("response body was not valid JSON", provider=provider_name) from exc
    if not isinstance(data, dict):
        raise ProviderDataError("expected a single JSON event object", provider=provider_name)
    return data


class TheOddsApiOddsAdapter(OddsAdapter):
    provider_name = "the_odds_api"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_odds(self, game_external_ids: list[str]) -> AdapterResponse[list[OddsLine]]:
        """Bulk `/odds` fetch (h2h/spreads/totals only -- player props need
        the event-specific endpoint, see `TheOddsApiPlayerPropsAdapter`).
        The bulk endpoint has no per-game filter param (ASSUMED, consistent
        with the CONFIRMED credit formula: bulk cost is markets x regions
        regardless of event count -- a per-game filter would make that
        formula meaningless), so this filters the full-slate response down
        to the requested games after fetching.

        **Discovery mode (Phase 3E-4B/C): an empty `game_external_ids`
        returns every event in the response, unfiltered.** Since the bulk
        endpoint always returns the full slate regardless of what's
        requested (see above) and its cost doesn't scale with event count,
        there is nothing to save by filtering when the caller doesn't yet
        know which The Odds API event ids correspond to its internal
        games -- exactly the situation the Odds Worker is in for a game
        Master Refresh created but this provider hasn't been linked to yet
        (`app.persistence.odds_game_linking`). Passing a non-empty list
        keeps the original filtered behavior unchanged.
        """
        response = await _get(
            self._client,
            f"/v4/sports/{_SPORT_KEY}/odds",
            params={
                "apiKey": self._api_key,
                "regions": "us",
                "markets": ",".join(_BULK_MARKETS),
                "oddsFormat": "american",
            },
            provider_name=self.provider_name,
        )
        events = _parse_json_array(response, provider_name=self.provider_name)
        wanted = set(game_external_ids)

        # Row isolation (2026-08-18, same defensive philosophy as the
        # Schedule fix): a malformed row must not destroy otherwise valid
        # data from the same response. Two isolation tiers, matching the
        # two levels of "row" this bulk payload actually has:
        #   - event-level: if an event's own identifying fields (id/teams/
        #     commence_time) are malformed, nothing under it can be
        #     trusted (every OddsLine needs them), so the whole event is
        #     skipped -- logged, not silently dropped.
        #   - market-level: once an event's own fields are known-good, one
        #     malformed bookmaker/market/outcome must not take down that
        #     event's other valid markets -- isolated per market.
        # HTTP failure / invalid top-level JSON / non-array payload still
        # fail the whole call, unchanged -- those already happened above,
        # via `_get`/`_parse_json_array`, before this loop starts.
        lines: list[OddsLine] = []
        latest_update: str | None = None
        for event in events:
            try:
                event_id = event["id"]
                if wanted and event_id not in wanted:
                    continue
                home_team = event["home_team"]
                away_team = event["away_team"]
                commence_time = _parse_timestamp(event["commence_time"])
            except (KeyError, TypeError, ValueError) as exc:
                _logger.warning(
                    "skipping malformed odds event (id=%r): %s", event.get("id"), exc
                )
                continue

            for bookmaker in event.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    try:
                        lines.append(
                            OddsLine(
                                game_external_id=event_id,
                                home_team=home_team,
                                away_team=away_team,
                                commence_time=commence_time,
                                sportsbook=bookmaker["key"],
                                market_type=_BULK_MARKET_TYPE.get(market["key"], "prop"),
                                line_data={"outcomes": market["outcomes"]},
                            )
                        )
                        market_update = market.get("last_update")
                        if market_update and (latest_update is None or market_update > latest_update):
                            latest_update = market_update
                    except (KeyError, TypeError, ValueError) as exc:
                        _logger.warning(
                            "skipping malformed odds market (event=%r, bookmaker=%r): %s",
                            event_id, bookmaker.get("key"), exc,
                        )
                        continue

        return AdapterResponse(
            value=lines,
            source=self.provider_name,
            provider_reported_at=_parse_timestamp(latest_update),
        )


class TheOddsApiPlayerPropsAdapter(PlayerPropsAdapter):
    provider_name = "the_odds_api"

    def __init__(self, *, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def fetch_player_props(self, game_external_ids: list[str]) -> AdapterResponse[list[PlayerProp]]:
        """One event-specific call per game (CONFIRMED per-game cost model)
        -- the bulk endpoint doesn't carry player props at all. Each
        Over/Under pair for the same bookmaker+market+player+point is
        merged into a single `PlayerProp`, matching that model's
        over_odds/under_odds shape.
        """
        props: list[PlayerProp] = []
        latest_update: str | None = None

        for game_id in game_external_ids:
            response = await _get(
                self._client,
                f"/v4/sports/{_SPORT_KEY}/events/{game_id}/odds",
                params={
                    "apiKey": self._api_key,
                    "regions": "us",
                    "markets": ",".join(_PLAYER_PROP_MARKETS),
                    "oddsFormat": "american",
                },
                provider_name=self.provider_name,
            )
            event = _parse_json_object(response, provider_name=self.provider_name)

            # Row isolation (2026-08-18, same defensive philosophy as the
            # Schedule/Odds fixes), three tiers matching this payload's
            # actual nesting:
            #   - event-level: if this game's own identifying fields are
            #     malformed, nothing under it can be trusted -- skip this
            #     game_id entirely (logged), move on to the next one. This
            #     is already its own HTTP call, so isolating it costs
            #     nothing extra.
            #   - market-level: a market with no usable `outcomes` is
            #     skipped, other markets for the same game still process.
            #   - outcome-level: one malformed outcome must not discard
            #     every other valid Over/Under pair for the same market.
            try:
                event_id = event["id"]
                event_home_team = event["home_team"]
                event_away_team = event["away_team"]
                event_commence_time = _parse_timestamp(event["commence_time"])
            except (KeyError, TypeError, ValueError) as exc:
                _logger.warning(
                    "skipping malformed player-prop event (game_id=%r): %s", game_id, exc
                )
                continue

            grouped: dict[tuple[str, str, str, float | None], PlayerProp] = {}
            for bookmaker in event.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    market_update = market.get("last_update")
                    if market_update and (latest_update is None or market_update > latest_update):
                        latest_update = market_update
                    try:
                        outcomes = market["outcomes"]
                    except (KeyError, TypeError) as exc:
                        _logger.warning(
                            "skipping malformed player-prop market (game_id=%r, bookmaker=%r): %s",
                            game_id, bookmaker.get("key"), exc,
                        )
                        continue
                    for outcome in outcomes:
                        try:
                            player_name = outcome["description"]
                            key = (bookmaker["key"], market["key"], player_name, outcome.get("point"))
                            prop = grouped.get(key)
                            if prop is None:
                                prop = PlayerProp(
                                    game_external_id=event_id,
                                    home_team=event_home_team,
                                    away_team=event_away_team,
                                    commence_time=event_commence_time,
                                    sportsbook=bookmaker["key"],
                                    player_external_id=_slugify(player_name),
                                    player_name=player_name,
                                    prop_type=market["key"],
                                    line=outcome["point"],
                                )
                                grouped[key] = prop
                            side = outcome["name"]
                            if side == "Over":
                                prop.over_odds = outcome["price"]
                            elif side == "Under":
                                prop.under_odds = outcome["price"]
                        except (KeyError, TypeError, ValueError) as exc:
                            _logger.warning(
                                "skipping malformed player-prop outcome (game_id=%r, bookmaker=%r, market=%r): %s",
                                game_id, bookmaker.get("key"), market.get("key"), exc,
                            )
                            continue

            props.extend(grouped.values())

        return AdapterResponse(
            value=props,
            source=self.provider_name,
            provider_reported_at=_parse_timestamp(latest_update),
        )


__all__ = ["TheOddsApiOddsAdapter", "TheOddsApiPlayerPropsAdapter", "ProviderError"]
