"""Persists normalized ScheduleEntry data from a Schedule adapter (Volume 3
§4.0/§4.1, Phase 3E-1) -- the ingestion path that creates and maintains
games rows and their game_provider_ids mapping for the schedule's provider.

Deliberately narrow: this is the FOUNDATION path only (3E-1's own scope).
For each ScheduleEntry it:
  - looks up an existing game_provider_ids mapping for
    (response.source, entry.game_external_id);
  - if found, updates that games row's mutable fields (status, stadium,
    scheduled_start, season_type, week, venue_lat, venue_long, venue_type);
  - if not found, creates a new games row and links it via
    game_provider_ids -- this is how a provider's Schedule call establishes
    a game's existence in the first place.

**Final is terminal (2026-09-15).** A Schedule response is a forward-looking
view of the slate: a provider can still describe a game as `Scheduled` or
`InProgress` long after it has actually ended, and with Master Refresh V2
persisting the full season, every already-played game is re-seen on every
daily refresh. So once a canonical game is finalized -- `finalized_at` stamped
by `app.workers.canonical_finalization` off real postgame evidence -- a later
refresh MUST NOT write `status` back to `scheduled`/`live`.

The guard is the DATABASE's own, never a prior read: the update PATCHes with
`finalized_at=is.null` as a server-side filter. A finalized game matches zero
rows, so the downgrade is impossible rather than merely unlikely -- there is no
read-then-write window for a concurrent finalization to slip through. When that
happens the row is then re-patched WITHOUT `status`, so every other mutable
field (venue, stadium, week, kickoff) still refreshes normally on a game that
has already been played; only the status is held terminal. `final_score` and
`finalized_at` are never in the writable field set at all, so a Schedule
refresh could not clear them even if it tried.

**Cross-provider reconciliation (2026-09-15, CHANGELOG v4.29).** This module
used to state that it deliberately did NOT reconcile two providers
independently discovering the same real-world game, leaving Decision 2's
"does this game already exist under another provider?" as an open item. That
item is now closed, narrowly: see `app.persistence.game_reconciliation`.
Provider ids stay authoritative whenever already linked; only an entry with NO
mapping falls back to deterministic canonical identity (canonical home team id
+ canonical away team id + bounded kickoff alignment), and fuzzy/name-only
matching remains prohibited.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

import httpx

from app.adapters.models import AdapterResponse, ScheduleEntry
from app.persistence.game_identity import GameIdentityError, link_provider_id, resolve_game_ids
from app.persistence.game_reconciliation import (
    AMBIGUOUS,
    MATCHED_EXACT,
    UNRESOLVED_TEAMS,
    CanonicalGame,
    decide_reconciliation,
    link_reconciled_game,
    load_reconciliation_candidates,
)
from app.persistence.team_identity import TeamIdentityError, resolve_team_ids


class PersistenceError(Exception):
    """Raised when a normalized response can't be written to Supabase --
    same boundary distinction as odds_snapshots.PersistenceError: a
    failure here is on our side of the adapter boundary, not the
    vendor's."""


def _auth_headers() -> dict:
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }


@dataclass
class SchedulePersistenceResult:
    """Counts for one ingestion run. Iterable as `(created, updated)` so the
    long-standing `games_created, games_updated = await persist_schedule_entries(...)`
    contract keeps working unchanged, while the reconciliation counters added in
    2026-09-15's canonical-identity amendment are available to callers that want
    them."""

    created: int = 0
    updated: int = 0
    #: Existing canonical games that gained this provider's id instead of being
    #: duplicated (see `app.persistence.game_reconciliation`).
    reconciled: int = 0
    #: Entries matched on an exact kickoff vs. within the bounded tolerance.
    reconciled_exact: int = 0
    reconciled_within_tolerance: int = 0
    #: Entries refused rather than guessed -- reported, never silently dropped.
    ambiguous: list[str] = field(default_factory=list)
    unresolved_teams: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def __iter__(self):
        yield self.created
        yield self.updated


async def persist_schedule_entries(
    response: AdapterResponse[list[ScheduleEntry]],
) -> SchedulePersistenceResult:
    """Upserts every ScheduleEntry in `response` into games, resolving/
    creating each row through game_provider_ids keyed by
    (response.source, entry.game_external_id).

    **Reconciliation before insertion (2026-09-15).** An entry with no mapping
    for this provider is NOT immediately a new game. It is first put through
    `app.persistence.game_reconciliation`, which matches it against existing
    canonical games on canonical home team id + canonical away team id +
    bounded kickoff alignment. Exactly one match -> the existing game gains this
    provider's id and keeps its row. Zero matches -> genuinely missing, insert.
    More than one -> refused and reported, never guessed and never duplicated.
    Only then does the insert path run. Without this step, the first ingestion
    from a new provider duplicates every game that already exists under another
    provider's identity.
    """
    entries = response.value
    if not entries:
        return SchedulePersistenceResult()

    provider_name = response.source
    supabase_url = os.environ["SUPABASE_URL"]
    headers = _auth_headers()
    result = SchedulePersistenceResult()

    async with httpx.AsyncClient(base_url=supabase_url, timeout=30.0) as client:
        existing = await resolve_game_ids(
            client,
            headers,
            provider_name=provider_name,
            provider_game_ids=[entry.game_external_id for entry in entries],
        )

        # One batched candidate load for the whole run, only when something is
        # actually unmapped -- a routine refresh of an already-mapped slate
        # costs nothing extra.
        candidates: list[CanonicalGame] | None = None
        entry_team_ids: dict[str, str] = {}
        # Entries refused by reconciliation. They must NOT fall through to
        # the insert path below -- inserting an ambiguous or unresolvable
        # entry creates exactly the duplicate canonical game the match rule
        # exists to prevent.
        refused: set[str] = set()
        if any(entry.game_external_id not in existing for entry in entries):
            # A failure here is BLOCKING and deliberately so. Without canonical
            # team identity there is no way to tell an existing game from a new
            # one, and the fallback -- inserting -- would duplicate every game
            # that already exists under another provider. Failing the run is
            # strictly better than splitting canonical identity, so the
            # underlying identity/read error is re-raised as the blocking
            # PersistenceError this path already declares.
            try:
                candidates = await load_reconciliation_candidates(
                    client, headers, provider_name=provider_name
                )
                entry_team_ids = await resolve_team_ids(
                    client,
                    headers,
                    provider_name=provider_name,
                    provider_team_ids=sorted(
                        {e.home_team for e in entries} | {e.away_team for e in entries}
                    ),
                )
            except (GameIdentityError, TeamIdentityError) as exc:
                raise PersistenceError(
                    f"cannot reconcile canonical game identity for {provider_name}, "
                    f"refusing to insert possible duplicates: {exc}"
                ) from exc

        for entry in entries:
            if entry.game_external_id not in existing and candidates is not None:
                decision = decide_reconciliation(
                    entry_home_team_id=entry_team_ids.get(entry.home_team),
                    entry_away_team_id=entry_team_ids.get(entry.away_team),
                    entry_scheduled_start=entry.scheduled_start,
                    candidates=candidates,
                )
                if decision.outcome == AMBIGUOUS:
                    result.ambiguous.append(
                        f"{entry.game_external_id} ({entry.away_team}@{entry.home_team}): "
                        f"{len(decision.candidate_game_ids)} candidates "
                        f"{decision.candidate_game_ids}"
                    )
                    refused.add(entry.game_external_id)
                    continue
                if decision.outcome == UNRESOLVED_TEAMS:
                    result.unresolved_teams.append(
                        f"{entry.game_external_id} ({entry.away_team}@{entry.home_team})"
                    )
                    continue
                if decision.game_id is not None:
                    try:
                        await link_reconciled_game(
                            client,
                            headers,
                            game_id=decision.game_id,
                            provider_game_id=entry.game_external_id,
                            provider_name=provider_name,
                        )
                    except GameIdentityError as exc:
                        result.conflicts.append(str(exc))
                        refused.add(entry.game_external_id)
                        continue
                    existing[entry.game_external_id] = decision.game_id
                    result.reconciled += 1
                    if decision.outcome == MATCHED_EXACT:
                        result.reconciled_exact += 1
                    else:
                        result.reconciled_within_tolerance += 1
                    # Mark it mapped so a second entry can't also claim it.
                    candidates = [
                        (
                            replace(c, has_provider_mapping=True)
                            if c.game_id == decision.game_id
                            else c
                        )
                        for c in candidates
                    ]

        for entry in entries:
            if entry.game_external_id in refused:
                continue
            mutable_fields = {
                "home_team": entry.home_team,
                "away_team": entry.away_team,
                "scheduled_start": entry.scheduled_start.isoformat(),
                "stadium": entry.stadium,
                "status": entry.status,
                "season_type": entry.season_type,
                "week": entry.week,
                # Phase 3E-6, Option A: refreshed on every Schedule ingestion,
                # same as every other mutable field above -- never fabricated
                # when the entry itself carries None.
                "venue_lat": entry.venue_lat,
                "venue_long": entry.venue_long,
                "venue_type": entry.venue_type,
            }

            game_id = existing.get(entry.game_external_id)
            if game_id is not None:
                # The terminal guard: `finalized_at=is.null` is enforced by
                # Postgres, so a finalized game simply matches no row.
                patch_response = await client.patch(
                    "/rest/v1/games",
                    params={"id": f"eq.{game_id}", "finalized_at": "is.null"},
                    json=mutable_fields,
                    headers={**headers, "Prefer": "return=representation"},
                )
                if patch_response.status_code not in (200, 204):
                    raise PersistenceError(
                        f"failed to update game {game_id}: "
                        f"{patch_response.status_code} {patch_response.text}"
                    )

                # Zero returned rows means the game is already finalized. A 204
                # carries no representation to count at all, so it is taken at
                # face value as a normal update.
                guard_blocked = (
                    patch_response.status_code != 204
                    and bool(patch_response.content)
                    and not patch_response.json()
                )
                if not guard_blocked:
                    result.updated += 1
                    continue

                # Finalized: refresh everything EXCEPT status, so a played
                # game's venue/week/kickoff still reconcile while its outcome
                # stays terminal.
                retained = {k: v for k, v in mutable_fields.items() if k != "status"}
                retained_response = await client.patch(
                    "/rest/v1/games",
                    params={"id": f"eq.{game_id}"},
                    json=retained,
                    headers=headers,
                )
                if retained_response.status_code not in (200, 204):
                    raise PersistenceError(
                        f"failed to update finalized game {game_id}: "
                        f"{retained_response.status_code} {retained_response.text}"
                    )
                result.updated += 1
                continue

            insert_response = await client.post(
                "/rest/v1/games",
                json={**mutable_fields, "sport": "nfl"},
                headers={**headers, "Prefer": "return=representation"},
            )
            if insert_response.status_code not in (200, 201):
                raise PersistenceError(
                    f"failed to create game for {provider_name}:{entry.game_external_id}: "
                    f"{insert_response.status_code} {insert_response.text}"
                )
            new_rows = insert_response.json()
            new_game_id = new_rows[0]["id"]
            await link_provider_id(
                client,
                headers,
                game_id=new_game_id,
                provider_name=provider_name,
                provider_game_id=entry.game_external_id,
            )
            result.created += 1

    return result
