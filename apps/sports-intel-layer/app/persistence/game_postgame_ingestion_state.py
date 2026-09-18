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

**Provider-independent since 2026-09-18** (HQ "Persistent Checkpoint
Foundation"). Every function below takes `provider_name` as a keyword with
a `mysportsfeeds` default, so the three existing MSF callers are unchanged
byte for byte while the same durable state machine now serves any
final-score provider. This is not a generalization for its own sake: the
SportsDataIO postgame audit found that worker holding its checkpoint
progress in a process-local dict, which a cron forgets on every tick --
a persistence defect that belongs to *any* provider driven by a stateless
cron, so it is fixed once, here, rather than per vendor.

The table was already provider-*shaped* (a `provider_name` column, a
`UNIQUE (game_id, provider_name)` key) but provider-*locked* (`check
(provider_name in ('mysportsfeeds'))`). Migration
`20260918190000_generic_postgame_checkpoint_foundation` unlocks it to a
closed allow-list and adds `checkpoints_done`.

**Three invariants are enforced by a database trigger, not by this
module** -- deliberately, per Volume 3's append-only-via-trigger rule,
because a guarantee that lives only in Python is a guarantee any future
caller can skip: `checkpoints_done` may only grow, `attempt_count` may
only grow, and `confirmed_complete` may never reopen. So a duplicate cron
tick, a container restart, or a careless generic `update_ingestion_state`
cannot hand back an attempt budget or re-buy a checkpoint already paid
for. This module's job is to make the correct write easy; the trigger's
job is to make the incorrect one impossible.
"""
from __future__ import annotations

from datetime import datetime

import httpx

#: Kept as the default for every function so the MSF callers that predate
#: the generic foundation continue to work without passing it.
_PROVIDER_NAME = "mysportsfeeds"


class IngestionStateError(Exception):
    """Raised when a `game_postgame_ingestion_state` read or write fails
    on Supabase's side -- same boundary distinction as every other
    persistence module's identical class in this codebase."""


async def get_ingestion_state(
    client: httpx.AsyncClient, headers: dict, *, game_id: str, provider_name: str = _PROVIDER_NAME
) -> dict | None:
    """Reads the current `game_postgame_ingestion_state` row for
    (game_id, provider_name), or `None` if none exists yet."""
    response = await client.get(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{provider_name}",
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
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    first_eligible_at: datetime,
    provider_name: str = _PROVIDER_NAME,
) -> dict:
    """Check-then-insert: creates a fresh `state='scheduled'` row for
    (game_id, provider_name) with `next_eligible_attempt_at =
    first_eligible_at` if none exists yet; otherwise returns the existing
    row untouched (never overwrites in-flight or terminal state -- see
    module docstring). Returns the row either way."""
    existing = await get_ingestion_state(
        client, headers, game_id=game_id, provider_name=provider_name
    )
    if existing is not None:
        return existing

    insert_response = await client.post(
        "/rest/v1/game_postgame_ingestion_state",
        json={
            "game_id": game_id,
            "provider_name": provider_name,
            "state": "scheduled",
            "next_eligible_attempt_at": first_eligible_at.isoformat(),
        },
        headers={**headers, "Prefer": "return=representation"},
    )
    if insert_response.status_code == 409:
        # A genuine concurrent-caller race -- another process created the
        # row between our GET and this POST. Re-read rather than raise.
        row = await get_ingestion_state(
            client, headers, game_id=game_id, provider_name=provider_name
        )
        if row is not None:
            return row
    if insert_response.status_code not in (200, 201):
        raise IngestionStateError(
            f"failed to create game_postgame_ingestion_state row for game {game_id}: "
            f"{insert_response.status_code} {insert_response.text}"
        )
    return insert_response.json()[0]


async def promote_due_scheduled_row(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    now: datetime,
    provider_name: str = _PROVIDER_NAME,
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
            "provider_name": f"eq.{provider_name}",
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
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    now: datetime,
    provider_name: str = _PROVIDER_NAME,
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
            "provider_name": f"eq.{provider_name}",
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


async def read_confirmed_complete_states(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str = _PROVIDER_NAME,
    limit: int = 500,
) -> list[dict]:
    """Reads every terminal `state='confirmed_complete'` row for
    `provider_name` -- the set of canonical games whose completed boxscore is
    already durably captured.

    Added for the MSF -> canonical finalization wiring (2026-09-15). Every
    existing read in this module is single-game (`get_ingestion_state`) or a
    targeted claim; the finalization worker needs the whole completed set, and
    `game_id`/`raw_capture_id` on these rows ARE the canonical game and the
    exact capture that justified the state -- so finalization never has to
    match on teams or dates, and never has to call a provider again.

    Selects `*` rather than an explicit column list so a future column added to
    this table can't turn this read into a 400.
    """
    response = await client.get(
        "/rest/v1/game_postgame_ingestion_state",
        params={
            "provider_name": f"eq.{provider_name}",
            "state": "eq.confirmed_complete",
            "select": "*",
            "order": "game_id.asc",
            "limit": str(limit),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise IngestionStateError(
            f"failed to read confirmed_complete ingestion states for {provider_name}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def update_ingestion_state(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_name: str = _PROVIDER_NAME,
    **fields,
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
        params={"game_id": f"eq.{game_id}", "provider_name": f"eq.{provider_name}"},
        json=fields,
        headers=headers,
    )
    if response.status_code not in (200, 204):
        raise IngestionStateError(
            f"failed to update game_postgame_ingestion_state for game {game_id}: "
            f"{response.status_code} {response.text}"
        )


async def read_checkpoints_done(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_name: str = _PROVIDER_NAME,
) -> frozenset[str]:
    """Returns the set of checkpoint labels this (game, provider) has
    already completed -- the durable replacement for
    `app.workers.postgame_worker`'s process-local
    `ReconciliationGameState.checks_done`.

    Returns an EMPTY set when no row exists, which is the honest answer:
    a game nobody has scheduled a check for has completed no checkpoints.
    That is also why this returns a `frozenset` -- it is fed straight to
    `app.workers.reconciliation.due_checkpoints`, whose `checks_done`
    parameter is already typed that way, so no adapter layer is needed
    between persistence and the schedule.
    """
    row = await get_ingestion_state(
        client, headers, game_id=game_id, provider_name=provider_name
    )
    if row is None:
        return frozenset()
    return frozenset(row.get("checkpoints_done") or [])


async def record_checkpoints_done(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    labels: set[str] | frozenset[str],
    provider_name: str = _PROVIDER_NAME,
    now: datetime | None = None,
) -> frozenset[str]:
    """Durably records that `labels` have now been completed for this
    (game, provider), and returns the full resulting set.

    **Unions rather than replaces.** It re-reads the stored set and writes
    the union, so a caller that knows only about the checkpoint it just
    finished cannot erase one finished by an earlier process. The database
    trigger refuses a shrinking write outright, so a bug here surfaces as a
    loud `IngestionStateError` rather than as a silently re-purchased
    provider call -- but this function is written so that never has to fire
    in the first place.

    A no-op returning the stored set when `labels` adds nothing new, so a
    duplicate cron tick costs one read and no write.

    `now`, when given, is also stamped as `last_attempt_at`, since in every
    real caller these are the same moment and splitting them into two
    writes would leave a window where a checkpoint is recorded with no
    attempt time behind it.
    """
    stored = await read_checkpoints_done(
        client, headers, game_id=game_id, provider_name=provider_name
    )
    merged = stored | frozenset(labels)
    if merged == stored:
        return stored

    fields: dict = {"checkpoints_done": sorted(merged)}
    if now is not None:
        fields["last_attempt_at"] = now.isoformat()
    await update_ingestion_state(
        client, headers, game_id=game_id, provider_name=provider_name, **fields
    )
    return merged


__all__ = [
    "IngestionStateError",
    "get_ingestion_state",
    "ensure_scheduled_row",
    "promote_due_scheduled_row",
    "claim_game_for_capture",
    "read_checkpoints_done",
    "read_confirmed_complete_states",
    "record_checkpoints_done",
    "update_ingestion_state",
]
