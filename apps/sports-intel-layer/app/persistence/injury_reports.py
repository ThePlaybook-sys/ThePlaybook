"""Persists normalized InjuryReport data into injury_reports (Volume 3 §4,
Phase 3E-5) -- the append-only historical record `daily_game_intelligence`'s
`injuries` field already reads from (`app.persistence.snapshots.
latest_injury_report`, built in 3E-2 ahead of this worker existing).

Mirrors `app.persistence.odds_snapshots` deliberately: adapter-agnostic
(depends only on `InjuryReport`/`AdapterResponse`), resolves game identity
through `app.persistence.game_identity.resolve_game_ids` rather than any
hidden single-column assumption, and is pure-append -- **no update, no
upsert, no de-duplication** (Mac's explicit Decision 2: every successful
poll writes a new snapshot, even if nothing changed, matching every other
snapshot table's own "every movement is a new row" convention and
`injury_reports`' own append-only DB trigger from the Phase 1 migration).
"""
from __future__ import annotations

import os

import httpx

from app.adapters.models import AdapterResponse, InjuryReport
from app.persistence.game_identity import resolve_game_ids

#: The only provider this module ever persists injuries for -- not derived
#: from AdapterResponse.source, same defensive convention as
#: odds_snapshots.py's identical constant.
_PROVIDER_NAME = "sportsdataio"


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same distinction from ProviderError as odds_snapshots.py's identical
    class: a failure here is on our side of the adapter boundary."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


async def persist_injury_reports(response: AdapterResponse[list[InjuryReport]]) -> int:
    """Writes every InjuryReport in `response` as a new injury_reports row.
    A report whose game_external_id has no matching games row is skipped,
    not silently dropped from the return value -- callers get back the
    count actually written, same partial-write detectability as
    `persist_odds_lines`.
    """
    reports = response.value
    if not reports:
        return 0

    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=5.0) as client:
        game_ids = await resolve_game_ids(
            client,
            headers,
            provider_name=_PROVIDER_NAME,
            provider_game_ids=sorted({report.game_external_id for report in reports}),
        )
        rows = [
            {
                "game_id": game_ids[report.game_external_id],
                "report_data": {
                    "player_external_id": report.player_external_id,
                    "player_name": report.player_name,
                    "team": report.team,
                    "status": report.status,
                    "description": report.description,
                },
            }
            for report in reports
            if report.game_external_id in game_ids
        ]
        if not rows:
            return 0

        insert_response = await client.post("/rest/v1/injury_reports", json=rows, headers=headers)
        if insert_response.status_code not in (200, 201):
            raise PersistenceError(
                f"failed to insert injury_reports: {insert_response.status_code} {insert_response.text}"
            )
        return len(rows)
