"""Persists normalized OddsLine data into odds_snapshots (Volume 3 §4) --
the append-only historical record Time Machine reconstruction reads from.

This module is adapter-agnostic: it only ever depends on the normalized
`OddsLine`/`AdapterResponse` models from `app.adapters.models`, never on
any vendor-specific shape. That's the actual proof that the pipeline
downstream of an adapter can't tell which vendor produced the data it's
persisting -- the same guarantee 3A's adapter-swap test proves one layer
up.
"""
from __future__ import annotations

import os

import httpx

from app.adapters.models import AdapterResponse, OddsLine


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    deliberately distinct from ProviderError: a failure here is on our
    side of the adapter boundary, not the vendor's, and callers should
    never confuse the two."""


async def _resolve_game_ids(
    client: httpx.AsyncClient, headers: dict, external_ids: list[str]
) -> dict[str, str]:
    """Maps games.external_provider_id -> games.id for the given external
    ids. A game with no matching row is simply absent from the returned
    dict -- callers decide how to handle that, this function doesn't guess.
    """
    if not external_ids:
        return {}
    response = await client.get(
        "/rest/v1/games",
        params={
            "external_provider_id": f"in.({','.join(external_ids)})",
            "select": "id,external_provider_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PersistenceError(
            f"failed to resolve game ids: {response.status_code} {response.text}"
        )
    return {row["external_provider_id"]: row["id"] for row in response.json()}


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
        game_ids = await _resolve_game_ids(
            client, headers, sorted({line.game_external_id for line in lines})
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


async def read_latest_odds_snapshots(game_external_id: str, *, limit: int = 10) -> list[dict]:
    """Downstream-read proof: reads back the most recent odds_snapshots
    rows for a game, by its external id, exactly as a real downstream
    caller (a worker, an agent) would -- never reading adapter output
    directly, always through the persisted record.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_response = await client.get(
            "/rest/v1/games",
            params={"external_provider_id": f"eq.{game_external_id}", "select": "id"},
            headers=headers,
        )
        if game_response.status_code != 200:
            raise PersistenceError(
                f"failed to resolve game id: {game_response.status_code} {game_response.text}"
            )
        rows = game_response.json()
        if not rows:
            return []
        game_id = rows[0]["id"]

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
