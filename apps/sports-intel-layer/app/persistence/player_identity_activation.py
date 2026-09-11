"""Automatic MSF player identity activation + quarantine (2026-09-11,
HQ-authorized "AUTOMATIC PLAYER IDENTITY + QUARANTINE BUILD").

This is the permanent wrapper the accepted Sunday ingestion design named
(Section 3) but never built: a provider-ID-first activation path around
the already-proven `app.persistence.player_identity`/`team_identity`
functions, which this module calls and never reimplements. It decides,
per player, whether a MySportsFeeds boxscore entry can be safely resolved
to a canonical `players.id` or must be quarantined into
`player_identity_quarantine` for manual review -- it never silently
merges or guesses.

Rules A-J (HQ's own numbering, preserved verbatim in code comments below):
  A. Provider player ID is primary identity evidence.
  B. If provider_player_id already maps uniquely: reuse the existing
     canonical player.
  C. For a genuinely unseen provider_player_id: resolve team through the
     persisted MSF team identity mapping.
  D. Never create a player when team identity is unresolved or
     conflicting.
  E. Never create/merge identity based on name alone.
  F. Name similarity may ONLY act as a duplicate/conflict safety signal.
     It must never establish canonical identity.
  G. If evidence suggests an existing canonical player may represent the
     same person but provider identity is not safely linked: QUARANTINE
     rather than auto-merge.
  H. Provider-ID collision, team conflict, ambiguous canonical match, or
     malformed identity must quarantine.
  I. A quarantined player must not prevent safe players from the same
     game from being resolved/persisted later.
  J. Everything must be idempotent across retries/redeploys.

Rule I is satisfied structurally: this module operates on one player at
a time and returns an `ActivationResult` for every documented quarantine
outcome rather than raising -- a caller looping over a game's roster
naturally continues to the next player regardless of one player's
quarantine. The one raised exception (`PlayerIdentityActivationError`)
is reserved for a genuine infra failure (a non-2xx Supabase response this
module cannot itself classify into one of the four quarantine cases),
never for a normal quarantine outcome.

No live provider call is made anywhere in this module -- it operates
entirely on already-resolved provider identity strings its caller
supplies (from an already-fetched/parsed payload), matching this pass's
explicit "no provider calls" scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from app.persistence.player_identity import PlayerIdentityError, link_provider_player_id, resolve_player_ids
from app.persistence.team_identity import resolve_team_ids

#: Matches the prior manual pass's precedent (no reusable fuzzy-matching
#: function exists anywhere else in the codebase -- confirmed by grep --
#: so this cutoff is reimplemented here, deliberately kept identical
#: rather than invented fresh).
_NAME_SIMILARITY_CUTOFF = 0.82

_PROVIDER_NAME = "mysportsfeeds"


class PlayerIdentityActivationError(Exception):
    """Raised only for a genuine infra/read failure this wrapper cannot
    itself classify into one of the four documented quarantine cases
    (e.g. a non-2xx response reading players/player_identity_quarantine
    itself). Never raised for a normal quarantine outcome -- those are
    always returned as an ActivationResult, per Rule I."""


@dataclass(frozen=True)
class ActivationResult:
    """Returned for every player, resolved or quarantined -- never both
    branches signaled by raising, so a caller can always inspect
    `outcome` and move on to the next player (Rule I)."""

    outcome: str  # "resolved" | "quarantined"
    player_id: str | None = None
    quarantine_id: str | None = None
    conflict_type: str | None = None


def _identity_key(provider_player_id: str | None, raw_player_name: str | None) -> str:
    """Mirrors the migration's own partial unique index expression
    exactly: provider_player_id when present, else a disclosed
    name-based fallback for the one case with no provider_player_id to
    key on at all (malformed_identity)."""
    return provider_player_id or f"~malformed~{raw_player_name or 'unknown'}"


async def _find_open_quarantine(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    identity_key: str,
) -> dict | None:
    response = await client.get(
        "/rest/v1/player_identity_quarantine",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "status": "eq.open",
            "select": "id,provider_player_id,raw_player_name,conflict_type",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PlayerIdentityActivationError(
            f"failed to read player_identity_quarantine for game {game_id}: "
            f"{response.status_code} {response.text}"
        )
    for row in response.json():
        if _identity_key(row.get("provider_player_id"), row.get("raw_player_name")) == identity_key:
            return row
    return None


async def _quarantine(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_player_id: str | None,
    provider_team_id: str | None,
    raw_player_name: str | None,
    raw_position: str | None,
    conflict_type: str,
    candidate_player_id: str | None = None,
    raw_capture_id: str | None = None,
) -> ActivationResult:
    """Idempotent, duplicate-preventing quarantine creation (Rule J +
    HQ's explicit "prevent duplicate unresolved cases" requirement):
    check-then-insert first, with the DB's own partial unique index
    (`idx_player_identity_quarantine_open_identity`) as defense-in-depth
    against a genuine concurrent-caller race -- a 409 from that index is
    caught and resolved by re-reading the now-existing row, never raised
    past this function."""
    identity_key = _identity_key(provider_player_id, raw_player_name)

    existing = await _find_open_quarantine(client, headers, game_id=game_id, identity_key=identity_key)
    if existing is not None:
        return ActivationResult(
            outcome="quarantined", quarantine_id=existing["id"], conflict_type=existing["conflict_type"]
        )

    insert_response = await client.post(
        "/rest/v1/player_identity_quarantine",
        json={
            "game_id": game_id,
            "provider_name": _PROVIDER_NAME,
            "provider_player_id": provider_player_id,
            "provider_team_id": provider_team_id,
            "raw_player_name": raw_player_name,
            "raw_position": raw_position,
            "conflict_type": conflict_type,
            "candidate_player_id": candidate_player_id,
            "raw_capture_id": raw_capture_id,
        },
        headers={**headers, "Prefer": "return=representation"},
    )
    if insert_response.status_code == 409:
        existing = await _find_open_quarantine(client, headers, game_id=game_id, identity_key=identity_key)
        if existing is not None:
            return ActivationResult(
                outcome="quarantined", quarantine_id=existing["id"], conflict_type=existing["conflict_type"]
            )
    if insert_response.status_code not in (200, 201):
        raise PlayerIdentityActivationError(
            f"failed to create player_identity_quarantine row for game {game_id}: "
            f"{insert_response.status_code} {insert_response.text}"
        )
    return ActivationResult(
        outcome="quarantined", quarantine_id=insert_response.json()[0]["id"], conflict_type=conflict_type
    )


async def _find_ambiguous_candidate(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    team_id: str,
    raw_player_name: str | None,
) -> str | None:
    """Rule F/G: name similarity is a SAFETY SIGNAL only, checked only
    against existing canonical players on the resolved team that do NOT
    yet carry a mysportsfeeds mapping (a player who already has one was
    already handled by the Rule B reuse check upstream, on a different
    provider_player_id -- comparing against them again would just be
    re-litigating an already-resolved identity). Never merges; only ever
    returns a candidate for the caller to quarantine against."""
    if not raw_player_name:
        return None

    team_players_response = await client.get(
        "/rest/v1/players",
        params={"team_id": f"eq.{team_id}", "select": "id,name"},
        headers=headers,
    )
    if team_players_response.status_code != 200:
        raise PlayerIdentityActivationError(
            f"failed to read players for team {team_id}: "
            f"{team_players_response.status_code} {team_players_response.text}"
        )
    team_players = team_players_response.json()
    if not team_players:
        return None

    player_ids = [p["id"] for p in team_players]
    mapped_response = await client.get(
        "/rest/v1/player_provider_ids",
        params={
            "provider_name": f"eq.{_PROVIDER_NAME}",
            "player_id": f"in.({','.join(player_ids)})",
            "select": "player_id",
        },
        headers=headers,
    )
    if mapped_response.status_code != 200:
        raise PlayerIdentityActivationError(
            f"failed to read player_provider_ids for team {team_id}: "
            f"{mapped_response.status_code} {mapped_response.text}"
        )
    already_mapped = {row["player_id"] for row in mapped_response.json()}

    for candidate in team_players:
        if candidate["id"] in already_mapped:
            continue
        similarity = SequenceMatcher(None, candidate["name"].lower(), raw_player_name.lower()).ratio()
        if similarity >= _NAME_SIMILARITY_CUTOFF:
            return candidate["id"]
    return None


async def activate_msf_player(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_player_id: str | None,
    provider_team_id: str | None,
    raw_player_name: str | None,
    raw_position: str | None,
    raw_capture_id: str | None = None,
) -> ActivationResult:
    """Permanent wrapper around the provider-ID-first `ensure_player`
    behavior, decided player-by-player. `provider_team_id` must be the
    identifier scheme `team_provider_ids` already has a mysportsfeeds
    mapping for (the abbreviation scheme, e.g. "NE"/"SEA" -- the scheme
    `parse_game_boxscore`'s own `PlayerStatLine.team` field carries; the
    numeric scheme is a different, out-of-scope identifier this module
    never touches).
    """
    # Rule H (malformed_identity): the provider payload itself lacks a
    # usable provider_player_id -- nothing else can be checked safely.
    if not provider_player_id:
        return await _quarantine(
            client,
            headers,
            game_id=game_id,
            provider_player_id=provider_player_id,
            provider_team_id=provider_team_id,
            raw_player_name=raw_player_name,
            raw_position=raw_position,
            conflict_type="malformed_identity",
            raw_capture_id=raw_capture_id,
        )

    # Rule B: provider_player_id already maps uniquely -- reuse, no new
    # evidence needed, no team/name checks performed at all.
    existing = await resolve_player_ids(
        client, headers, provider_name=_PROVIDER_NAME, provider_player_ids=[provider_player_id]
    )
    player_id = existing.get(provider_player_id)
    if player_id is not None:
        return ActivationResult(outcome="resolved", player_id=player_id)

    # Rule C/D: a genuinely unseen provider_player_id must resolve team
    # identity through the persisted MSF team mapping -- never create a
    # player with unresolved or conflicting team identity.
    if not provider_team_id:
        return await _quarantine(
            client,
            headers,
            game_id=game_id,
            provider_player_id=provider_player_id,
            provider_team_id=provider_team_id,
            raw_player_name=raw_player_name,
            raw_position=raw_position,
            conflict_type="team_unresolved",
            raw_capture_id=raw_capture_id,
        )

    team_map = await resolve_team_ids(
        client, headers, provider_name=_PROVIDER_NAME, provider_team_ids=[provider_team_id]
    )
    team_id = team_map.get(provider_team_id)
    if team_id is None:
        return await _quarantine(
            client,
            headers,
            game_id=game_id,
            provider_player_id=provider_player_id,
            provider_team_id=provider_team_id,
            raw_player_name=raw_player_name,
            raw_position=raw_position,
            conflict_type="team_unresolved",
            raw_capture_id=raw_capture_id,
        )

    # Rule F/G: name similarity may only ever act as a safety signal --
    # a plausible existing duplicate on this team means quarantine, never
    # auto-merge.
    candidate_player_id = await _find_ambiguous_candidate(
        client, headers, team_id=team_id, raw_player_name=raw_player_name
    )
    if candidate_player_id is not None:
        return await _quarantine(
            client,
            headers,
            game_id=game_id,
            provider_player_id=provider_player_id,
            provider_team_id=provider_team_id,
            raw_player_name=raw_player_name,
            raw_position=raw_position,
            conflict_type="ambiguous_match",
            candidate_player_id=candidate_player_id,
            raw_capture_id=raw_capture_id,
        )

    # Rule A/E: create fresh, provider-ID-first -- name/position are
    # stored alongside the new row, never used to establish identity.
    insert_response = await client.post(
        "/rest/v1/players",
        json={"name": raw_player_name, "team_id": team_id, "position": raw_position},
        headers={**headers, "Prefer": "return=representation"},
    )
    if insert_response.status_code not in (200, 201):
        raise PlayerIdentityActivationError(
            f"failed to create player {raw_player_name!r}: "
            f"{insert_response.status_code} {insert_response.text}"
        )
    new_player_id = insert_response.json()[0]["id"]

    try:
        await link_provider_player_id(
            client,
            headers,
            player_id=new_player_id,
            provider_name=_PROVIDER_NAME,
            provider_player_id=provider_player_id,
        )
    except PlayerIdentityError:
        # Rule H (id_collision): the initial resolve_player_ids check
        # found nothing, but creating the mapping just hit a real
        # uniqueness conflict on (provider_name, provider_player_id) --
        # link_provider_player_id's own upsert only covers
        # (player_id, provider_name), so this is a genuine race or
        # data-integrity anomaly, never silently adopted. Compensating
        # rollback of the orphan players row: the two PostgREST calls
        # aren't transactional, so the row this branch just created must
        # be removed explicitly rather than left as an unlinked orphan.
        await client.delete(
            "/rest/v1/players",
            params={"id": f"eq.{new_player_id}"},
            headers=headers,
        )
        return await _quarantine(
            client,
            headers,
            game_id=game_id,
            provider_player_id=provider_player_id,
            provider_team_id=provider_team_id,
            raw_player_name=raw_player_name,
            raw_position=raw_position,
            conflict_type="id_collision",
            raw_capture_id=raw_capture_id,
        )

    return ActivationResult(outcome="resolved", player_id=new_player_id)


__all__ = ["ActivationResult", "PlayerIdentityActivationError", "activate_msf_player"]
