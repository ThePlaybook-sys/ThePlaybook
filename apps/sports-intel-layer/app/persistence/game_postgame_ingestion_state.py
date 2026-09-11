"""Persistence helpers for `game_postgame_ingestion_state` (Permanent Box
Score Worker Build, 2026-09-11, HQ-authorized) -- the durable per-
(game, provider) MSF completion-check state machine the Sunday Ingestion
Foundation Build pass (2026-09-11) created the table for but left
unread/unwritten by any code ("no worker reads or writes this table
yet"). This module is that worker-facing read/write layer;
`app.workers.msf_postgame_worker` calls it, never queries the table
directly.

**Atomic claim, no new locking primitive** -- exactly the shape the
migration's own comment already specifies: `UPDATE ... SET
state='capture_in_progress' ... WHERE state='eligible_for_postgame_check'
AND next_eligible_attempt_at <= now() RETURNING *`. Postgres's own
row-level locking on `UPDATE` makes two concurrent claims against the
same row serialize automatically -- proven live for this exact shape in
the Sunday Ingestion Foundation Build's own pgTAP suite (Proof 3). This
module's `claim_game_for_capture` targets one explicit `game_id`
(matching `app.workers.msf_postgame_worker`'s "one eligible canonical
game" framing) rather than an unbounded batch claim, so no `LIMIT` on an
`UPDATE` (a genuinely different, less portable PostgREST feature) is
ever needed.

**Never clobbers in-flight state.** `ensure_scheduled_row` is
check-then-insert, not an upsert -- an upsert against
`(game_id, provider_name)` would silently overwrite a row already mid-
capture or already `confirmed_complete` if called again by mistake. The
row this table exists to protect is exactly the kind of state an upsert
would put at risk.
"""
from __future__ import annotations

from datetime import datetime

import httpx

_PROVIDER_NAME = "mysportsfeeds"


class IngestionStateError(Exception):
    """Raised when a `game_postgame_ingestion_state` read or write fails
    on Supabase's side -- same boundary distinction as every other
    persistence module's identical class in this codebase."""


async def get_ingestion_state(
    client: httpx.AsyncClient, headers: dict, *, game_id: str
) -> dict | None:
    """Reads the current `game_postgame_ingestion_state` row for
    (game_id, mysportsfeeds), or `None` if none exists yet."""
    response = await client.get(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "select": "*",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise IngestionStateError(
            f"failed to read game_postgame_ingestion_state for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def ensure_scheduled_row(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, first_eligible_at: datetime
) -> dict:
    """Check-then-insert: creates a fresh `state='scheduled'` row for
    (game_id, mysportsfeeds) with `next_eligible_attempt_at =
    first_eligible_at` if none exists yet; otherwise returns the existing
    row untouched (never overwrites in-flight or terminal state -- see
    module docstring). Returns the row either way."""
    existing = await get_ingestion_state(client, headers, game_id=game_id)
    if existing is not None:
        return existing

    insert_response = await client.post(
        "/rest/v1/game_postgame_ingestion_state",
        json={
            "game_id": game_id,
            "provider_name": _PROVIDER_NAME,
            "state": "scheduled",
            "next_eligible_attempt_at": first_eligible_at.isoformat(),
        },
        headers={**headers, "Prefer": "return=representation"},
    )
    if insert_response.status_code == 409:
        # A genuine concurrent-caller race -- another process created the
        # row between our GET and this POST. Re-read rather than raise.
        row = await get_ingestion_state(client, headers, game_id=game_id)
        if row is not None:
            return row
    if insert_response.status_code not in (200, 201):
        raise IngestionStateError(
            f"failed to create game_postgame_ingestion_state row for game {game_id}: "
            f"{insert_response.status_code} {insert_response.text}"
        )
    return insert_response.json()[0]


async def promote_due_scheduled_row(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, now: datetime
) -> None:
    """Flips a due `state='scheduled'` row to `'eligible_for_postgame_check'`
    -- the first arrow in the design's own chain
    (`scheduled -> eligible_for_postgame_check`). A no-op (0 rows
    affected, no error) if the row isn't `scheduled`, isn't due yet, or
    doesn't exist -- this function never creates a row itself (see
    `ensure_scheduled_row` for that)."""
    response = await client.patch(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "state": "eq.scheduled",
            "next_eligible_attempt_at": f"lte.{now.isoformat()}",
        },
        json={"state": "eligible_for_postgame_check"},
        headers=headers,
    )
    if response.status_code not in (200, 204):
        raise IngestionStateError(
            f"failed to promote scheduled row for game {game_id}: "
            f"{response.status_code} {response.text}"
        )


async def claim_game_for_capture(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, now: datetime
) -> dict | None:
    """Atomically claims one game for a capture attempt: `UPDATE ... SET
    state='capture_in_progress', last_attempt_at=now WHERE
    game_id=eq.<id> AND provider_name=eq.mysportsfeeds AND
    state='eligible_for_postgame_check' AND next_eligible_attempt_at <=
    now RETURNING *`. Returns the claimed row (with its PRE-claim
    `attempt_count`, since the caller increments it only once the check
    actually completes -- see module docstring on attempt_count
    semantics), or `None` if the claim didn't apply (not eligible, not
    due, already claimed by a concurrent caller, or terminal) -- a safe,
    silent no-op in every one of those cases, exactly mirroring the
    no-double-claim proof already established for this table."""
    response = await client.patch(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "state": "eq.eligible_for_postgame_check",
            "next_eligible_attempt_at": f"lte.{now.isoformat()}",
        },
        json={"state": "capture_in_progress", "last_attempt_at": now.isoformat()},
        headers={**headers, "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201, 204):
        raise IngestionStateError(
            f"failed to claim game {game_id} for capture: {response.status_code} {response.text}"
        )
    rows = response.json() if response.content else []
    return rows[0] if rows else None


async def update_ingestion_state(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, **fields
) -> None:
    """Generic field-level update for (game_id, mysportsfeeds) --
    `app.workers.msf_postgame_worker` uses this for every state
    transition after the initial claim (recording `attempt_count`,
    `last_http_status`, `last_error`, `error_classification`,
    `next_eligible_attempt_at`, `raw_capture_id`, `captured_at`,
    `quarantine_reason`, and the terminal/resting `state` itself) rather
    than this module hardcoding one function per transition -- the state
    machine's own shape lives in the worker/design docs, not duplicated
    here as a wall of near-identical functions."""
    if not fields:
        return
    response = await client.patch(
        "/rest/v1/game_postgame_ingestion_state",
        params={"game_id": f"eq.{game_id}", "provider_name": f"eq.{_PROVIDER_NAME}"},
        json=fields,
        headers=headers,
    )
    if response.status_code not in (200, 204):
        raise IngestionStateError(
            f"failed to update game_postgame_ingestion_state for game {game_id}: "
            f"{response.status_code} {response.text}"
        )


__all__ = [
    "IngestionStateError",
    "get_ingestion_state",
    "ensure_scheduled_row",
    "promote_due_scheduled_row",
    "claim_game_for_capture",
    "update_ingestion_state",
]
