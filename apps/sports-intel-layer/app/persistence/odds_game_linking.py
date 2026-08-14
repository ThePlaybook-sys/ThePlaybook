"""Deterministic The Odds API event -> internal `games.id` resolution
(Phase 3E-4C).

Promotes the fixture-proven mechanism from the 3E-3 pre-implementation
audit (`tests/test_odds_game_linking_audit.py`) into a real production
module the Odds Worker and Player Props Worker actually call, instead of
each re-deriving the same logic inline (or two independently-drifting
copies of it).

**Pipeline (Mac's exact wording, 3E-4 checkpoint):** "The Odds API event
-> provider-specific home/away identities -> team_provider_ids -> canonical
teams.id identities -> SportsDataIO team identities where required by the
current games schema -> candidate internal game -> scheduled-start
validation -> games.id."

**No fuzzy matching, ever.** An event resolves to exactly one game or is
treated as UNRESOLVED -- never guessed, never paired with the "closest"
candidate, and never allowed to create a second game when identity is
ambiguous. This module only ever *reads* `games`; it never writes one --
creating/updating a `games` row remains Schedule/Master Refresh's job
(Phase 3E-1/3E-2). It also never assumes `games.home_team`/`.away_team`
are FK columns -- they are SportsDataIO abbreviation *text* (Phase 3E-1
finding), so matching them against The Odds API's own team identity
requires the two-hop `team_provider_ids` comparison below, never a raw
string comparison.

**Explicit failure modes this module distinguishes** (all become
"unresolved, with a reason" via `UnresolvedEvent` rather than an
exception -- except malformed input / infra failure, which raises
`GameLinkingError` so `resolve_and_link_odds_events` can isolate that one
event without losing why, per Mac's "isolate failure by game/event where
practical" instruction):

- **unknown team**: The Odds API's own `home_team`/`away_team` string has
  no `team_provider_ids` mapping at all.
- **zero matching games**: no candidate in the scheduled-start window.
- **multiple matching games**: more than one candidate matches on
  `{home_team_id, away_team_id}` within kickoff tolerance -- ambiguous,
  never guessed.
- **reversed home/away**: naturally handled, not a special case -- this
  module matches strictly `home == home` and `away == away`, never an
  unordered/set comparison, so a reversed pairing simply fails to match
  rather than false-matching a different game.
- **kickoff-time mismatch**: team identity matches but no candidate's
  stored `scheduled_start` falls within tolerance of the event's own
  `commence_time` -- guards against two same-pair games existing across
  a season (bye-week rematches), rare in the NFL but never assumed
  impossible.
- **rescheduled game**: our stored `scheduled_start` has since moved --
  naturally unresolved (a kickoff-time mismatch) until Master Refresh's
  next Schedule fetch updates it; this module never guesses across a
  schedule change instead of waiting for the data to catch up.
- **malformed provider event**: a lookup itself fails (Supabase-side
  error) -- raises `GameLinkingError`, caught and isolated per-event by
  `resolve_and_link_odds_events`.

**Observability** (per Mac's "smallest architecture consistent with
existing logging/error conventions" instruction -- the only existing
precedent in this codebase is `app.adapters.cache`'s module-scoped
`logging.getLogger(...)`): every unresolved event is logged at WARNING
with its specific reason, and also returned in `LinkingResult.unresolved`
so a caller (worker-run metrics, a future diagnostics endpoint) can act on
it without scraping logs. No new monitoring subsystem.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from app.persistence.game_identity import GameIdentityError, link_provider_id
from app.persistence.games import GamesQueryError, list_games_in_window
from app.persistence.team_identity import TeamIdentityError, resolve_team_ids

_logger = logging.getLogger("sports-intel-layer.odds_game_linking")

_PROVIDER_NAME = "the_odds_api"
_SPORTSDATAIO_PROVIDER_NAME = "sportsdataio"

#: Candidate-game date window around an event's commence_time -- matches
#: the +/-1 day window proven in the 3E-3 audit test.
_CANDIDATE_WINDOW = timedelta(days=1)

#: Tightest allowed gap between a team-matched candidate's stored
#: scheduled_start and the event's own commence_time before the match is
#: rejected as a kickoff-time mismatch. ASSUMED: no Blueprint-specified
#: number exists for this tolerance -- 6 hours comfortably absorbs
#: same-day flex/time-slot placement while still catching a genuinely
#: different game (e.g. a rescheduled game whose stored time hasn't
#: caught up yet). Flagged to Mac in the 3E-4 completion report as an
#: engineering judgment call, not a confirmed Blueprint number.
KICKOFF_TOLERANCE = timedelta(hours=6)


class GameLinkingError(Exception):
    """Raised for a Supabase-side read/write failure during resolution --
    never for a legitimate, well-formed-but-unresolved event, which
    returns an `UnresolvedEvent` instead of raising."""


@dataclass(frozen=True)
class ProviderEventIdentity:
    """The minimal, provider-neutral shape this module needs to attempt a
    resolution -- deliberately not `OddsLine`/`PlayerProp` themselves, so
    this module has no dependency on which adapter category produced the
    event (both carry these same four fields as of Phase 3E-4B)."""

    provider_game_id: str
    home_team: str
    away_team: str
    commence_time: datetime


@dataclass(frozen=True)
class LinkedEvent:
    provider_game_id: str
    game_id: str


@dataclass(frozen=True)
class UnresolvedEvent:
    provider_game_id: str
    reason: str


@dataclass
class LinkingResult:
    linked: list[LinkedEvent]
    unresolved: list[UnresolvedEvent]


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


async def resolve_odds_event_game_id(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    provider_game_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
) -> LinkedEvent | UnresolvedEvent:
    """Resolves one The Odds API event to `games.id`, deterministically.

    Does NOT write `game_provider_ids` itself -- see
    `resolve_and_link_odds_events`, which performs resolve-then-link as a
    batch. This function is the pure resolution step on its own, so it's
    directly testable (and reusable) without forcing a write.
    """
    try:
        odds_team_ids = await resolve_team_ids(
            client, headers, provider_name=_PROVIDER_NAME, provider_team_ids=[home_team, away_team]
        )
    except TeamIdentityError as exc:
        raise GameLinkingError(f"team identity lookup failed for event {provider_game_id}: {exc}") from exc

    event_home_team_id = odds_team_ids.get(home_team)
    event_away_team_id = odds_team_ids.get(away_team)
    if event_home_team_id is None or event_away_team_id is None:
        unknown = [name for name in (home_team, away_team) if name not in odds_team_ids]
        reason = f"unknown team(s), no team_provider_ids mapping: {unknown}"
        _logger.warning("odds event %s unresolved: %s", provider_game_id, reason)
        return UnresolvedEvent(provider_game_id=provider_game_id, reason=reason)

    try:
        candidate_games = await list_games_in_window(
            client,
            headers,
            start=(commence_time - _CANDIDATE_WINDOW).date(),
            end=(commence_time + _CANDIDATE_WINDOW).date(),
        )
    except GamesQueryError as exc:
        raise GameLinkingError(f"candidate game lookup failed for event {provider_game_id}: {exc}") from exc

    if not candidate_games:
        reason = "zero candidate games in the scheduled-start window"
        _logger.warning("odds event %s unresolved: %s", provider_game_id, reason)
        return UnresolvedEvent(provider_game_id=provider_game_id, reason=reason)

    sdio_abbrevs = sorted({g["home_team"] for g in candidate_games} | {g["away_team"] for g in candidate_games})
    try:
        sdio_team_ids = await resolve_team_ids(
            client, headers, provider_name=_SPORTSDATAIO_PROVIDER_NAME, provider_team_ids=sdio_abbrevs
        )
    except TeamIdentityError as exc:
        raise GameLinkingError(
            f"sportsdataio team identity lookup failed for event {provider_game_id}: {exc}"
        ) from exc

    # Strict, ordered comparison -- home must match home and away must
    # match away. A reversed-home/away event simply produces zero matches
    # here rather than false-matching against a different game.
    matched = [
        g
        for g in candidate_games
        if sdio_team_ids.get(g["home_team"]) == event_home_team_id
        and sdio_team_ids.get(g["away_team"]) == event_away_team_id
    ]

    if not matched:
        reason = "zero games match on {home_team_id, away_team_id}"
        _logger.warning("odds event %s unresolved: %s", provider_game_id, reason)
        return UnresolvedEvent(provider_game_id=provider_game_id, reason=reason)

    within_tolerance = [
        g for g in matched if abs(_parse_datetime(g["scheduled_start"]) - commence_time) <= KICKOFF_TOLERANCE
    ]

    if len(within_tolerance) != 1:
        reason = (
            f"ambiguous: {len(matched)} team-matched candidate(s), "
            f"{len(within_tolerance)} within {KICKOFF_TOLERANCE} of commence_time"
        )
        _logger.warning("odds event %s unresolved: %s", provider_game_id, reason)
        return UnresolvedEvent(provider_game_id=provider_game_id, reason=reason)

    return LinkedEvent(provider_game_id=provider_game_id, game_id=within_tolerance[0]["id"])


async def resolve_and_link_odds_events(
    client: httpx.AsyncClient,
    headers: dict,
    events: list[ProviderEventIdentity],
) -> LinkingResult:
    """Batch entry point: resolves every event, persists a
    `game_provider_ids` link (idempotent -- `link_provider_id`'s own
    upsert-on-conflict) for each one that resolves, and isolates failures
    per-event -- one malformed/unlookupable event never aborts the batch
    or hides why the others succeeded or failed (Mac's 3E-4D isolation
    requirement, applied here since this is the shared step both the Odds
    Worker and Player Props Worker call before persisting).
    """
    linked: list[LinkedEvent] = []
    unresolved: list[UnresolvedEvent] = []

    for event in events:
        try:
            result = await resolve_odds_event_game_id(
                client,
                headers,
                provider_game_id=event.provider_game_id,
                home_team=event.home_team,
                away_team=event.away_team,
                commence_time=event.commence_time,
            )
        except GameLinkingError as exc:
            reason = f"lookup failure: {exc}"
            _logger.warning("odds event %s unresolved: %s", event.provider_game_id, reason)
            unresolved.append(UnresolvedEvent(provider_game_id=event.provider_game_id, reason=reason))
            continue

        if isinstance(result, UnresolvedEvent):
            unresolved.append(result)
            continue

        try:
            await link_provider_id(
                client,
                headers,
                game_id=result.game_id,
                provider_name=_PROVIDER_NAME,
                provider_game_id=result.provider_game_id,
            )
        except GameIdentityError as exc:
            reason = f"resolved but failed to persist link: {exc}"
            _logger.warning("odds event %s unresolved: %s", event.provider_game_id, reason)
            unresolved.append(UnresolvedEvent(provider_game_id=event.provider_game_id, reason=reason))
            continue

        linked.append(result)

    return LinkingResult(linked=linked, unresolved=unresolved)
