"""Per-game odds poll ATTEMPT state (2026-09-16, "ODDS WORKER COST + FAILURE
HARDENING").

**Why this exists rather than reusing `odds_snapshots`.**
`odds_snapshots.read_last_polled_at` derives "when was this game last polled"
from captured snapshot rows. That is only ever a record of SUCCESS: a poll
whose event could not be resolved to a canonical game writes no snapshot, so
it leaves no trace, so the game reads as never-polled and comes due again on
the very next cron tick -- permanently. Attempt and success were the same
signal and only success was recorded.

This table records the other half: a real attempt was made for this game,
whatever came of it. It is the same fix, for the same reason, that
`news_worker_poll_state` already applies to News Worker (whose own migration
comment spells out the identical "writes no row at all -- indistinguishable
from never polled" trap).

**Current-state, not history.** One row per `(game_id, provider_name)`,
always overwritten. This is scheduling metadata, not a fact worth preserving
-- the deliberate opposite of `odds_snapshots`, which is append-only because
an observed market price IS a fact. `news_worker_poll_state` makes the same
call for the same reason.

**Reads never fail the run.** A failure reading this state is reported and
degrades to today's behaviour (cadence alone), never to a crash -- losing
backoff for one cycle costs at most one extra provider call, whereas failing
the run costs every game's odds. Writes are likewise collected as failures
rather than raised, matching this worker's established per-step isolation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.workers.odds_backoff import OUTCOME_SUCCESS

_TABLE = "/rest/v1/odds_worker_poll_state"


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


class PollStateError(Exception):
    """Raised when reading or writing odds poll state fails on Supabase's
    side -- our side of the adapter boundary, never the vendor's."""


@dataclass(frozen=True)
class PollState:
    """One game's attempt state, as this worker needs it for due-selection."""

    game_id: str
    last_attempt_at: datetime | None
    last_attempt_outcome: str | None
    last_success_at: datetime | None
    consecutive_failure_count: int


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def read_poll_state(
    client: httpx.AsyncClient, headers: dict, *, provider_name: str
) -> dict[str, PollState]:
    """Bulk-reads attempt state for `provider_name`, keyed by `game_id`.

    A game with no row is simply absent from the returned dict. Every caller
    treats a missing key as "never attempted", which is the same safe default
    `should_poll` already applies to a missing `last_polled_at` -- realized
    rather than replaced.

    Deliberately takes no `game_ids` filter, matching
    `odds_snapshots.read_last_polled_at`'s own reasoning: the table holds one
    row per game rather than per observation, so it stays small, and
    filtering would mean duplicating the worker's candidate-window query.
    """
    response = await client.get(
        _TABLE,
        params={
            "provider_name": f"eq.{provider_name}",
            "select": (
                "game_id,last_attempt_at,last_attempt_outcome,"
                "last_success_at,consecutive_failure_count"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PollStateError(
            f"failed to read odds poll state for {provider_name!r}: "
            f"{response.status_code} {response.text}"
        )
    return {
        row["game_id"]: PollState(
            game_id=row["game_id"],
            last_attempt_at=_parse(row.get("last_attempt_at")),
            last_attempt_outcome=row.get("last_attempt_outcome"),
            last_success_at=_parse(row.get("last_success_at")),
            consecutive_failure_count=row.get("consecutive_failure_count") or 0,
        )
        for row in response.json()
    }


async def read_poll_state_from_env(provider_name: str = "the_odds_api") -> dict[str, PollState]:
    """`read_poll_state` for a caller that holds no Supabase client of its
    own, building one from the environment exactly as
    `odds_snapshots.read_last_polled_at` already does.

    This exists so `app.main`'s thin HTTP adapter can supply real attempt
    state without ever referencing the service-role credential by name --
    `tests/test_environment_safety.py` forbids that module from naming any
    provider or service-role credential, and this keeps that guarantee
    intact rather than working around it.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()
    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        return await read_poll_state(client, headers, provider_name=provider_name)


async def record_attempt(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_name: str,
    attempted_at: datetime,
    outcome: str,
    consecutive_failure_count: int,
    failure_reason: str | None = None,
) -> None:
    """Upserts one game's attempt state after a real poll attempt.

    `last_success_at` is advanced ONLY on `OUTCOME_SUCCESS`, and is otherwise
    omitted from the payload entirely so an unresolved attempt cannot
    overwrite a genuine earlier capture time. That separation is the whole
    point of this table: an attempt must never be able to masquerade as fresh
    odds data to the kickoff-proximity cadence.

    `last_failure_reason` is cleared on success and set otherwise, so a
    failure is preserved rather than silently dropped.
    """
    stamped = attempted_at.astimezone(timezone.utc).isoformat()
    payload = {
        "game_id": game_id,
        "provider_name": provider_name,
        "last_attempt_at": stamped,
        "last_attempt_outcome": outcome,
        "consecutive_failure_count": consecutive_failure_count,
        "last_failure_reason": None if outcome == OUTCOME_SUCCESS else failure_reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if outcome == OUTCOME_SUCCESS:
        payload["last_success_at"] = stamped

    response = await client.post(
        _TABLE,
        params={"on_conflict": "game_id,provider_name"},
        json=payload,
        headers={
            **headers,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    if response.status_code not in (200, 201, 204):
        raise PollStateError(
            f"failed to record odds poll attempt for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
