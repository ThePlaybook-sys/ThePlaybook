"""Phase 8.0.5 Pass 2.2 (2026-09-07) -- real, durable per-team last-poll
state for News Worker.

**Why `news_article_history` cannot serve this purpose, despite carrying
an `ingested_at` column:** that table is insert-once-per-(provider_name,
article_url) -- first-sighting only (2026-09-04 design). A team whose
fetch succeeds but finds zero NEW articles writes no row at all that
cycle, which is indistinguishable from "this team was never polled." This
table instead records "a real fetch attempt happened for this team,"
independent of whether anything new was found -- the actual fact
`_should_poll`'s per-team cadence gate needs to be correct.

One row per `team_id` (unique/primary key), upserted after every real
fetch attempt (success or provider error alike -- see
`app.workers.news_worker`'s own reasoning: a provider error still means a
real round-trip happened and a real quota unit was spent, so the team
must not be treated as eligible again next tick at no cost)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx


class PollStateError(Exception):
    """Raised when a poll-state read or write fails on Supabase's side."""


async def read_last_polled_at(
    client: httpx.AsyncClient, headers: dict, *, team_ids: list[str]
) -> dict[str, datetime]:
    """Bulk-reads real last-poll timestamps for `team_ids`. A team_id with
    no row is simply absent from the returned dict -- the caller's own
    `.get(team_id)` already treats a missing key as "never polled,"
    exactly like the existing DI-injected `last_polled_at` dict semantics
    this real read replaces."""
    if not team_ids:
        return {}
    response = await client.get(
        "/rest/v1/news_worker_poll_state",
        params={"team_id": f"in.({','.join(team_ids)})", "select": "team_id,last_polled_at"},
        headers=headers,
    )
    if response.status_code != 200:
        raise PollStateError(f"failed to read news poll state: {response.status_code} {response.text}")
    return {
        row["team_id"]: datetime.fromisoformat(row["last_polled_at"].replace("Z", "+00:00"))
        for row in response.json()
    }


async def record_polled(
    client: httpx.AsyncClient, headers: dict, *, team_id: str, polled_at: datetime
) -> None:
    """Upserts this team's real last-poll timestamp -- one row per team,
    always overwritten to the latest real attempt (never accumulated,
    unlike odds_snapshots' append-only history; this is current-state-only
    scheduling metadata, not a fact worth preserving history of)."""
    response = await client.post(
        "/rest/v1/news_worker_poll_state",
        params={"on_conflict": "team_id"},
        json={
            "team_id": team_id,
            "last_polled_at": polled_at.astimezone(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={**headers, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201, 204):
        raise PollStateError(f"failed to record poll state for team_id={team_id!r}: {response.status_code} {response.text}")


__all__ = ["PollStateError", "read_last_polled_at", "record_polled"]
