"""Deterministic cross-provider canonical game reconciliation (2026-09-15,
HQ-authorized "SPORTSDATAIO CANONICAL GAME RECONCILIATION").

**The problem this exists to solve.** `app.persistence.schedule` resolves a
game's identity solely through `game_provider_ids` on
`(provider_name, game_external_id)`. Found -> PATCH; not found -> INSERT. That is
correct and safe *once a provider has been seen before*. It is catastrophic the
first time a NEW provider describes games that already exist under a different
provider's identity: every entry resolves as not-found, so every real-world game
is inserted a second time.

That was live in dev on 2026-09-15: all 23 canonical games -- including the 16
Week 1 games finalized that day -- carried `balldontlie`/`mysportsfeeds`/
`the_odds_api` mappings and **zero** `sportsdataio` mappings. A full-season
SportsDataIO Schedule refresh would have given each finalized game a second,
`scheduled`, unscored row: canonical identity split in half, which is worse for
odds linking, grading and calibration than the missing week it was meant to fix.

**The authorized amendment (supersedes Decision 2's blanket prohibition, narrowly).**
Provider-specific game ids remain authoritative whenever they are already linked.
Only when a provider has NO mapping for an entry may reconciliation fall back to
deterministic canonical identity: **canonical home team id + canonical away team
id + bounded kickoff alignment**. Fuzzy and name-only reconciliation remain
prohibited, and nothing here relaxes that.

**Team identity is resolved on BOTH sides, never compared as text.** `games`
stores teams as free text (`home_team`/`away_team`), so a raw string comparison
would be exactly the name matching Decision 2 forbids. Instead both sides are put
through the authoritative `team_provider_ids` mapping and compared as canonical
`teams.id` values. A game whose stored team text does not resolve to a canonical
team simply never matches -- it is refused, not guessed at. (Live proof that this
matters: 19 of 23 dev games resolve; the 4 legacy fixtures that store full team
names do not, and must not.)

**What is never used as evidence:** fuzzy or normalized team names, display-text
parsing, scores, market/odds data, and hardcoded matchups. None of those are read
by this module at any point.

**Uniqueness is enforced by the database, not by this code.**
`game_provider_ids` already carries two UNIQUE constraints that make the required
safety properties structural rather than conventional:
  - `UNIQUE (provider_name, provider_game_id)` -- one GameKey can map to at most
    one canonical game;
  - `UNIQUE (game_id, provider_name)` -- one canonical game can hold at most one
    SportsDataIO mapping.
This module adds the one thing those constraints cannot express: a conflicting
re-link must be *loud*. `link_provider_id` upserts with
`resolution=merge-duplicates`, so pointing an already-mapped game at a different
GameKey would silently rewrite it. `link_reconciled_game` refuses instead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from app.persistence.game_identity import GameIdentityError, link_provider_id
from app.persistence.team_identity import resolve_team_ids

_logger = logging.getLogger(__name__)

#: Maximum accepted difference between two providers' stated kickoff for the
#: SAME canonical game, used ONLY after an exact-timestamp match has been tried
#: and found nothing.
#:
#: Sized to absorb timestamp *representation* differences and nothing more:
#: second-level truncation and minute-level rounding (a provider publishing an
#: 8:20pm ET kickoff as :15 or :30). It is deliberately far below one hour so
#: that a genuine timezone or DST error -- SportsDataIO publishes both an
#: Eastern-local `Date` and a `DateTimeUTC`, and confusing them skews by 4-5
#: hours -- can NEVER be absorbed silently. Such an entry fails to match and is
#: reported, which is the correct loud failure.
#:
#: Disclosed-conservative, matching this codebase's convention for numbers that
#: are judgment rather than measurement: it is not derived from a measured
#: distribution of provider disagreement, because no SportsDataIO Schedule
#: response has been ingested yet to measure one from.
KICKOFF_TOLERANCE = timedelta(minutes=15)

SPORTSDATAIO = "sportsdataio"

#: Outcomes. Every entry gets exactly one.
MATCHED_EXACT = "matched_exact_kickoff"
MATCHED_WITHIN_TOLERANCE = "matched_within_kickoff_tolerance"
NO_MATCH_INSERT = "no_match_insert_new_game"
AMBIGUOUS = "ambiguous_multiple_candidates"
UNRESOLVED_TEAMS = "unresolved_provider_team_mapping"


@dataclass(frozen=True)
class CanonicalGame:
    """A candidate canonical game, with its teams already resolved to canonical
    ids. `has_provider_mapping` is True when this game ALREADY carries a
    SportsDataIO mapping, which makes it ineligible to absorb a different
    GameKey (the `UNIQUE (game_id, provider_name)` constraint would reject it,
    and silently rewriting it would be worse)."""

    game_id: str
    home_team_id: str
    away_team_id: str
    scheduled_start: datetime
    finalized_at: str | None = None
    has_provider_mapping: bool = False


@dataclass(frozen=True)
class ReconciliationDecision:
    outcome: str
    game_id: str | None = None
    #: Populated for AMBIGUOUS so the conflict is reportable, never silent.
    candidate_game_ids: list[str] = field(default_factory=list)
    kickoff_delta_seconds: float | None = None


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def decide_reconciliation(
    *,
    entry_home_team_id: str | None,
    entry_away_team_id: str | None,
    entry_scheduled_start: datetime,
    candidates: list[CanonicalGame],
    tolerance: timedelta = KICKOFF_TOLERANCE,
) -> ReconciliationDecision:
    """Pure decision function -- no I/O, so the match rule is testable in
    isolation from every read around it.

    Order of evidence, strictest first:
      1. both provider teams must resolve to canonical team ids, or refuse;
      2. candidates must match BOTH canonical team ids exactly;
      3. prefer an exact `scheduled_start` equality match;
      4. only if that finds nothing, accept a single candidate within
         `tolerance`;
      5. more than one candidate at either step is AMBIGUOUS -- never guessed,
         never inserted as a duplicate.
    """
    if entry_home_team_id is None or entry_away_team_id is None:
        return ReconciliationDecision(outcome=UNRESOLVED_TEAMS)

    same_matchup = [
        c
        for c in candidates
        if c.home_team_id == entry_home_team_id
        and c.away_team_id == entry_away_team_id
        # A game already mapped to a different GameKey cannot absorb this one.
        and not c.has_provider_mapping
    ]
    if not same_matchup:
        return ReconciliationDecision(outcome=NO_MATCH_INSERT)

    exact = [c for c in same_matchup if c.scheduled_start == entry_scheduled_start]
    if len(exact) == 1:
        return ReconciliationDecision(
            outcome=MATCHED_EXACT, game_id=exact[0].game_id, kickoff_delta_seconds=0.0
        )
    if len(exact) > 1:
        return ReconciliationDecision(
            outcome=AMBIGUOUS, candidate_game_ids=sorted(c.game_id for c in exact)
        )

    near = [
        c
        for c in same_matchup
        if abs(c.scheduled_start - entry_scheduled_start) <= tolerance
    ]
    if len(near) == 1:
        delta = (near[0].scheduled_start - entry_scheduled_start).total_seconds()
        return ReconciliationDecision(
            outcome=MATCHED_WITHIN_TOLERANCE, game_id=near[0].game_id, kickoff_delta_seconds=delta
        )
    if len(near) > 1:
        return ReconciliationDecision(
            outcome=AMBIGUOUS, candidate_game_ids=sorted(c.game_id for c in near)
        )

    # Same teams, but no kickoff within tolerance -- a different occurrence
    # (or a real disagreement worth surfacing as a new row rather than hiding).
    return ReconciliationDecision(outcome=NO_MATCH_INSERT)


async def load_reconciliation_candidates(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_name: str = SPORTSDATAIO,
) -> list[CanonicalGame]:
    """Reads every canonical game once, resolves both of its teams through the
    authoritative `team_provider_ids` mapping, and marks which games already
    carry a mapping for `provider_name`.

    One batched read per table, never per entry -- a full-season refresh
    reconciles ~304 entries against this single in-memory candidate set."""
    response = await client.get(
        "/rest/v1/games",
        params={"select": "id,home_team,away_team,scheduled_start,finalized_at", "sport": "eq.nfl"},
        headers=headers,
    )
    if response.status_code != 200:
        raise GameIdentityError(
            f"failed to read canonical games for reconciliation: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        return []

    team_tokens = sorted({r["home_team"] for r in rows} | {r["away_team"] for r in rows})
    team_ids = await resolve_team_ids(
        client, headers, provider_name=provider_name, provider_team_ids=team_tokens
    )

    mapped = await client.get(
        "/rest/v1/game_provider_ids",
        params={"provider_name": f"eq.{provider_name}", "select": "game_id"},
        headers=headers,
    )
    if mapped.status_code != 200:
        raise GameIdentityError(
            f"failed to read existing {provider_name} game mappings: "
            f"{mapped.status_code} {mapped.text}"
        )
    already_mapped = {row["game_id"] for row in mapped.json()}

    candidates: list[CanonicalGame] = []
    for row in rows:
        start = _parse(row.get("scheduled_start"))
        home = team_ids.get(row["home_team"])
        away = team_ids.get(row["away_team"])
        # A game whose teams don't resolve canonically, or whose kickoff can't be
        # parsed, is simply not a candidate. Never matched on weaker evidence.
        if start is None or home is None or away is None:
            continue
        candidates.append(
            CanonicalGame(
                game_id=row["id"],
                home_team_id=home,
                away_team_id=away,
                scheduled_start=start,
                finalized_at=row.get("finalized_at"),
                has_provider_mapping=row["id"] in already_mapped,
            )
        )
    return candidates


async def link_reconciled_game(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    game_id: str,
    provider_game_id: str,
    provider_name: str = SPORTSDATAIO,
) -> None:
    """Attaches a provider GameKey to an existing canonical game, refusing
    loudly if that game already carries a DIFFERENT GameKey for this provider.

    `link_provider_id` upserts on `(game_id, provider_name)` with
    `resolution=merge-duplicates`, which is right for re-ingesting the same
    mapping but would silently rewrite a conflicting one. A canonical game
    whose provider identity changes underneath it is a real integrity problem,
    so it is surfaced rather than merged."""
    existing = await client.get(
        "/rest/v1/game_provider_ids",
        params={
            "game_id": f"eq.{game_id}",
            "provider_name": f"eq.{provider_name}",
            "select": "provider_game_id",
        },
        headers=headers,
    )
    if existing.status_code != 200:
        raise GameIdentityError(
            f"failed to check existing {provider_name} mapping for game {game_id}: "
            f"{existing.status_code} {existing.text}"
        )
    rows = existing.json()
    if rows:
        current = rows[0]["provider_game_id"]
        if current != provider_game_id:
            raise GameIdentityError(
                f"refusing to silently rewrite {provider_name} identity for game {game_id}: "
                f"already mapped to {current!r}, refused {provider_game_id!r}"
            )
        return  # already linked to exactly this GameKey -- idempotent no-op

    await link_provider_id(
        client,
        headers,
        game_id=game_id,
        provider_name=provider_name,
        provider_game_id=provider_game_id,
    )
    _logger.info(
        "reconciled canonical game %s -> %s:%s", game_id, provider_name, provider_game_id
    )
