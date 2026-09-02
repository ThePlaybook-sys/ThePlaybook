"""Persists normalized OddsLine data into odds_snapshots (Volume 3 §4) --
the append-only historical record Time Machine reconstruction reads from.

This module is adapter-agnostic: it only ever depends on the normalized
`OddsLine`/`AdapterResponse` models from `app.adapters.models`, never on
any vendor-specific shape. That's the actual proof that the pipeline
downstream of an adapter can't tell which vendor produced the data it's
persisting -- the same guarantee 3A's adapter-swap test proves one layer
up.

Game resolution (Phase 3E-1, Decision 2, 2026-08-13): this module used to
resolve every OddsLine's game_external_id by matching it directly against
games.external_provider_id -- a hidden assumption that column was always
The Odds API's own event id, with no way for a second vendor's id to ever
coexist on the same game. It now resolves through the general
game_provider_ids mapping table (via app.persistence.game_identity),
explicitly as provider_name="the_odds_api" -- the only provider this
module's own AdapterResponse.source is ever expected to carry, since this
file is the odds/props persistence path, not a generic one.
"""
from __future__ import annotations

import os
from datetime import datetime

import httpx

from app.adapters.models import AdapterResponse, OddsLine, PlayerProp
from app.persistence.game_identity import resolve_game_ids

#: The only provider this module ever persists odds/props for. Not derived
#: from AdapterResponse.source, so a caller can't accidentally point this
#: module's writes at some other provider's game_provider_ids rows by
#: passing a differently-sourced AdapterResponse.
_PROVIDER_NAME = "the_odds_api"


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    deliberately distinct from ProviderError: a failure here is on our
    side of the adapter boundary, not the vendor's, and callers should
    never confuse the two."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def persist_odds_lines(response: AdapterResponse[list[OddsLine]]) -> int:
    """Writes every OddsLine in `response` as a new odds_snapshots row.
    Lines whose game_external_id has no matching games row are skipped,
    not silently dropped from the return value -- callers get back the
    count actually written, so a partial write is detectable rather than
    reported as a full success.
    """
    lines = response.value
    if not lines:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=sorted({line.game_external_id for line in lines}),
        )
        rows = [
            {
                "game_id": game_ids[line.game_external_id],
                "sportsbook": line.sportsbook,
                "market_type": line.market_type,
                "line_data": line.line_data,
            }
            for line in lines
            if line.game_external_id in game_ids
        ]
        if not rows:
            return 0

        insert_response = await client.post("/rest/v1/odds_snapshots", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert odds_snapshots: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)


async def persist_player_props(response: AdapterResponse[list[PlayerProp]]) -> int:
    """Writes every PlayerProp in `response` as a new odds_snapshots row
    with `market_type='prop'` (Phase 3E-4E).

    **Schema-conflict check performed before writing this (per Mac's
    explicit "STOP and report" instruction if one existed):** Volume 3
    §4's `odds_snapshots` table comment already documents `market_type`
    as `'moneyline','spread','total','prop'` -- 'prop' is a designed,
    pre-existing value, not a new one this phase invents. `line_data
    jsonb` is documented as "full odds payload, normalized shape from
    adapter" -- deliberately schema-flexible, so player-prop-specific
    fields (player identity, prop type, line, over/under odds) fit inside
    it exactly as spreads/totals/moneylines already do, with no new
    column needed. **No conflict found; proceeding with this design was
    confirmed safe by direct inspection, not assumed.**

    Same game-resolution and skip-not-drop behavior as
    `persist_odds_lines` -- a prop whose `game_external_id` has no
    matching `games` row is skipped, not silently dropped from the
    return value.
    """
    props = response.value
    if not props:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=sorted({prop.game_external_id for prop in props}),
        )
        rows = [
            {
                "game_id": game_ids[prop.game_external_id],
                "sportsbook": prop.sportsbook,
                "market_type": "prop",
                "line_data": {
                    "player_external_id": prop.player_external_id,
                    "player_name": prop.player_name,
                    "prop_type": prop.prop_type,
                    "line": prop.line,
                    "over_odds": prop.over_odds,
                    "under_odds": prop.under_odds,
                },
            }
            for prop in props
            if prop.game_external_id in game_ids
        ]
        if not rows:
            return 0

        insert_response = await client.post("/rest/v1/odds_snapshots", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert player-prop odds_snapshots: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)


async def read_last_polled_at() -> dict[str, datetime]:
    """Derives `run_odds_worker`'s `last_polled_at` argument from
    already-persisted `odds_snapshots` history, keyed by internal
    `game_id` (not the provider's external id -- this reads the same
    space `run_odds_worker`'s own `due_games` loop indexes into).

    **Phase 7 Milestone 7.0B (2026-09-02):** `run_odds_worker` has no
    built-in run-history storage of its own -- its own docstring says
    passing `None` (the default) means "treat every due game as
    never-polled," which is always SAFE for a single invocation but
    would make `app.workers.windows`'s adaptive cadence meaningless for a
    stateless HTTP-triggered caller: every invocation would see every
    non-kicked-off candidate game as due, unconditionally, regardless of
    how recently it was actually last fetched. Rather than adding new
    state storage (out of this milestone's "minimum operational change"
    scope, and duplicating what `odds_snapshots.captured_at` already
    records), this derives the same information from the real append-only
    history already being written: the most recent `captured_at` across
    ANY sportsbook/market row for a game is exactly the "when was this
    game last actually polled" fact `should_poll` needs. A game with zero
    prior rows is simply absent from the returned dict -- `last_polled_at.
    get(game_id)` then returns `None`, which `should_poll` already
    correctly treats as "never polled, always due" -- the same safe
    default `run_odds_worker` already documents, just realized instead of
    replaced.

    Deliberately takes no `game_ids` argument and doesn't pre-filter by
    candidate window -- that would require duplicating `run_odds_worker`'s
    own `_CANDIDATE_WINDOW_DAYS` query. Reading the most recent rows
    overall and reducing to one entry per game_id is simpler and gives an
    identical result: a game outside any real candidate window either has
    no rows (absent from the dict, same as today) or old rows that get
    naturally superseded once real polling resumes for it.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        response = await client.get(
            "/rest/v1/odds_snapshots",
            params={
                "select": "game_id,captured_at",
                # Newest-first: the first row seen per game_id, below, is
                # therefore its max(captured_at) -- no server-side GROUP
                # BY needed for this single-column aggregate.
                "order": "captured_at.desc",
                # Generous bound, not a correctness-critical one: real
                # NFL-scale volume (a handful of games x sportsbooks x
                # markets, even at the tightest 2-minute pregame cadence)
                # stays far under this. Ordered newest-first, so even if
                # ever hit, the rows that matter (the most recent per
                # game) are the ones guaranteed present.
                "limit": "5000",
            },
            headers=headers,
        )
        if response.status_code != 200:
            raise PersistenceError(
                f"failed to read odds_snapshots for last_polled_at: {response.status_code} {response.text}"
            )

        result: dict[str, datetime] = {}
        for row in response.json():
            game_id = row["game_id"]
            if game_id not in result:
                result[game_id] = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
        return result


async def read_latest_odds_snapshots(game_external_id: str, *, limit: int = 10) -> list[dict]:
    """Downstream-read proof: reads back the most recent odds_snapshots
    rows for a game, by its external id, exactly as a real downstream
    caller (a worker, an agent) would -- never reading adapter output
    directly, always through the persisted record.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=[game_external_id],
        )
        if game_external_id not in game_ids:
            return []
        game_id = game_ids[game_external_id]

        snapshots_response = await client.get(
            "/rest/v1/odds_snapshots",
            params={
                "game_id": f"eq.{game_id}",
                "select": "*",
                "order": "captured_at.desc",
                "limit": str(limit),
            },
            headers=headers,
        )
        if snapshots_response.status_code != 200:
            raise PersistenceError(
                f"failed to read odds_snapshots: {snapshots_response.status_code} {snapshots_response.text}"
            )
        return snapshots_response.json()
