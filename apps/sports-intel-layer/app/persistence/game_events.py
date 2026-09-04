"""Raw-capture-only persistence for game_events (Volume 3 §4.3) --
2026 Data Preservation Readiness Plan, pre-9/9 minimum implementation.

**This module does NOT normalize.** Its one job is writing whatever a
provider's play-by-play/game-event response actually contains into
`raw_payload jsonb`, unconditionally -- every typed column
(`period`/`clock`/`event_type`/`score_home`/`score_away`/
`involved_team_id`/`involved_player_ids`) is left `null` here, exactly
as Volume 3 §4.3 specifies. Normalizing those fields against a real
MySportsFeeds (or any other provider's) payload shape is explicitly
deferred to a future pass, once the 2026-09-09/10 live-game validation
(`docs/ops/nfl-provider-decision-record.md`) confirms what that shape
actually is -- this module must not fabricate or infer it ahead of that.

**Shape-agnostic on purpose.** A provider's real PBP/game-event response
might be a JSON array of per-play objects, or a single nested object with
no obvious per-event list at all -- this isn't known yet. `write_raw_game_events`
accepts either: a list is written as one `game_events` row per list item;
anything else (a dict, or any other JSON value) is written as exactly one
row whose `raw_payload` is that whole value. Either way, nothing is lost
and nothing is guessed about internal structure.

Mirrors `app.persistence.weather_snapshots`/`injury_reports` deliberately:
adapter-agnostic at the call boundary (though there is no adapter yet --
this is invoked directly with a raw response), self-contained
`httpx.AsyncClient` construction from env vars, and pure-append with no
update/upsert/de-duplication -- matching every other snapshot table's
"every capture is a new row" convention. No uniqueness constraint exists
on `provider_event_id` (Volume 3 §4.3's own explicit deferral), so this
module makes no attempt at idempotency either -- calling it twice with
the same payload writes it twice, which is the correct, disclosed
behavior until a real provider payload confirms a stable identity to
dedupe against.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx


class PersistenceError(Exception):
    """Raised when a raw payload can't be written to Supabase -- same
    distinction from a provider-side error as every sibling
    snapshot-persistence module's identical class."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


def _fragments(raw_response: Any) -> list[Any]:
    """A list is one fragment per item; anything else is one fragment
    holding the whole value. Never inspects keys/shape beyond this --
    that would be exactly the premature normalization this module exists
    to avoid."""
    if isinstance(raw_response, list):
        return raw_response
    return [raw_response]


async def write_raw_game_events(
    *,
    game_id: str,
    provider_name: str,
    raw_response: Any,
    now: datetime | None = None,
) -> int:
    """Writes `raw_response` as one or more new `game_events` rows, every
    typed column left null, `raw_payload` carrying the untouched fragment.
    Returns the number of rows written. A `None`/empty-list response
    writes nothing and returns 0 -- not an error, since "the provider had
    nothing to report" is a legitimate real result (e.g. a game with no
    events yet)."""
    fragments = [f for f in _fragments(raw_response) if f is not None]
    if not fragments:
        return 0

    now = now or datetime.now(timezone.utc)
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    rows = [
        {
            "game_id": game_id,
            "provider_name": provider_name,
            "raw_payload": fragment,
            "captured_at": now.isoformat(),
        }
        for fragment in fragments
    ]

    async with httpx.AsyncClient(base_url=supabase_url, timeout=10.0) as client:
        insert_response = await client.post("/rest/v1/game_events", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert game_events: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)
