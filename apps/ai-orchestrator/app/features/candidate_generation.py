"""V1 pregame `MarketCandidate` generation (Milestone 4.9, Decision 1).

**Scope, exactly as approved:** home moneyline, away moneyline, home
spread, away spread, over total, under total -- six candidates at most,
generated deterministically from already-persisted `odds_snapshots` rows,
never fabricated. **Player props are explicitly DEFERRED from this
module** -- not an oversight: the Player Prop Agent is not built, prop
candidate consensus semantics remain intentionally unresolved
(`app.features.consensus.resolve_candidate_direction` already returns
`None`/excludes `market_type == "prop"` as of Milestone 4.7), and
supporting historical/usage data for props is still incomplete. Phase 5
or a later data-expansion milestone may revisit this; this module simply
never looks at prop rows at all.

**No pre-selection of "the winner" (Mac's explicit instruction):** both
sides of every market are generated as separate, independent candidates
-- home moneyline and away moneyline are two candidates, not one
"the favorite" candidate. This module answers "what could be evaluated,"
never "what should be recommended" -- that remains Phase 5's Recommendation
Strategy Engine, entirely out of scope here.

**Reference sportsbook policy (Mac's approved direction):** one
configurable, ordered sportsbook preference list governs the WHOLE game
-- not a different book chosen independently per market ("book-shopping"
is explicitly out of scope for Milestone 4.9). Reading this module's
`select_reference_sportsbook`: walk the preference list in order, use the
first sportsbook that has ANY fresh, usable market data for this game at
all. Once a sportsbook is selected, an INDIVIDUAL market within it may
still be missing or stale -- that specific market is skipped with an
honest reason, while the other markets from the same book still proceed
(mirrors the Worker's own per-candidate isolation principle: one
market's absence must not block the others). If NO sportsbook in the
preference list has any fresh data at all, candidate generation is
skipped for the whole game, with a reason recorded -- never a random
sportsbook, never fabricated odds.

**Freshness policy (Mac's approved direction):** reuses
`sports-intel-layer`'s own write-side polling-cadence tiers
(`app.workers.windows.classify_window`, Phase 3E-4F) as the read-side
staleness ceiling -- duplicated here rather than imported (separate
deployable services, no shared package, per this codebase's established
convention -- see `app.persistence.games.find_previous_final_game`'s own
docstring for the identical precedent). A snapshot is fresh if its
`captured_at` is no older than however long the Odds Worker itself would
go between polls at the game's current kickoff proximity, **plus an
explicit orchestration grace period** so the Recommendation Worker's own
startup/queueing latency after a valid poll never turns a genuinely fresh
snapshot stale."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.features.candidate import MarketCandidate, candidate_key

#: Duplicated from `app.workers.windows` (sports-intel-layer, Phase
#: 3E-4F) -- the exact same tier boundaries/intervals, read in the
#: opposite direction (a ceiling on snapshot age, not a polling cadence).
_BOUNDARIES: tuple[tuple[timedelta, int], ...] = (
    (timedelta(minutes=5), 120),
    (timedelta(minutes=15), 300),
    (timedelta(minutes=60), 900),
    (timedelta(hours=2), 3600),
)
_FAR_INTERVAL_SECONDS = 86400
#: STOPPED (at/after kickoff) reuses the RAMP_5M interval, mirroring
#: `windows.py`'s own documented choice for its cache-TTL mapping.
_STOPPED_INTERVAL_SECONDS = 120

#: Mac's explicit "grace period" instruction: the Recommendation Worker
#: runs some time after Master Refresh/Odds Worker activity, not
#: instantaneously -- this buffer keeps that orchestration latency from
#: ever turning a genuinely fresh poll into a falsely-stale one.
ORCHESTRATION_GRACE_SECONDS = 300

#: V1 scope, exactly as approved -- no player props.
_V1_MARKET_TYPES = ("moneyline", "spread", "total")


class CandidateGenerationError(Exception):
    """Raised for a malformed input this module cannot safely interpret
    (e.g. a naive datetime) -- never silently guessed."""


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise CandidateGenerationError(f"{name} must be a timezone-aware datetime, got a naive one: {value!r}")


def max_snapshot_age_seconds(*, now: datetime, kickoff: datetime) -> int:
    """The read-side freshness ceiling, in seconds, for this game's
    current kickoff proximity -- the write-side polling interval that
    tier implies, plus `ORCHESTRATION_GRACE_SECONDS`. Mirrors
    `classify_window`'s own DST-safe UTC-normalized subtraction exactly."""
    _require_aware(now, "now")
    _require_aware(kickoff, "kickoff")
    time_to_kickoff = kickoff.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    if time_to_kickoff <= timedelta(0):
        interval = _STOPPED_INTERVAL_SECONDS
    else:
        interval = _FAR_INTERVAL_SECONDS
        for boundary, tier_interval in _BOUNDARIES:
            if time_to_kickoff <= boundary:
                interval = tier_interval
                break
    return interval + ORCHESTRATION_GRACE_SECONDS


def _is_fresh(*, captured_at: datetime, now: datetime, kickoff: datetime) -> bool:
    _require_aware(captured_at, "captured_at")
    ceiling = max_snapshot_age_seconds(now=now, kickoff=kickoff)
    age = (now.astimezone(timezone.utc) - captured_at.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= ceiling


@dataclass(frozen=True)
class SkippedMarket:
    market_type: str
    reason: str  # "no_snapshot" | "stale_snapshot"


@dataclass(frozen=True)
class CandidateGenerationResult:
    sportsbook_used: str | None
    candidates: tuple[MarketCandidate, ...]
    skipped_markets: tuple[SkippedMarket, ...]
    #: Set only when NO configured sportsbook had any usable data at all
    #: -- candidate generation was skipped for the whole game. Distinct
    #: from `skipped_markets`, which can be non-empty even when
    #: `sportsbook_used` is set (a partial book).
    game_skipped_reason: str | None = None


def _latest_row(rows: list[dict], *, sportsbook: str, market_type: str) -> dict | None:
    matching = [r for r in rows if r["sportsbook"] == sportsbook and r["market_type"] == market_type]
    if not matching:
        return None
    return max(matching, key=lambda r: r["captured_at"])


def select_reference_sportsbook(
    odds_rows: list[dict],
    *,
    reference_sportsbook_preference: list[str],
    now: datetime,
    kickoff: datetime,
) -> str | None:
    """Walks `reference_sportsbook_preference` in order, returns the
    first sportsbook with at least one FRESH V1-market snapshot for this
    game. Returns `None` if no configured sportsbook qualifies -- never a
    random/arbitrary sportsbook."""
    for sportsbook in reference_sportsbook_preference:
        for market_type in _V1_MARKET_TYPES:
            row = _latest_row(odds_rows, sportsbook=sportsbook, market_type=market_type)
            if row is not None and _is_fresh(captured_at=row["captured_at"], now=now, kickoff=kickoff):
                return sportsbook
    return None


def _candidates_from_row(
    row: dict, *, game_id: str, sportsbook: str, market_type: str, home_team: str, away_team: str
) -> list[MarketCandidate]:
    outcomes = row["line_data"].get("outcomes", [])
    observed_at = row["captured_at"]
    candidates = []
    for outcome in outcomes:
        selection = outcome["name"]
        # Player-prop rows never reach this function (V1_MARKET_TYPES
        # excludes "prop"); moneyline/spread selections are team names
        # (validated against home_team/away_team elsewhere, at consensus
        # time by app.features.consensus.resolve_candidate_direction --
        # this module does not duplicate that validation, it only carries
        # the raw provider-reported selection through unchanged).
        candidates.append(
            MarketCandidate(
                game_id=game_id,
                sportsbook=sportsbook,
                market_type=market_type,
                selection=selection,
                american_odds=outcome.get("price"),
                point=outcome.get("point"),
                observed_at=observed_at,
            )
        )
    return candidates


def generate_candidates_for_game(
    *,
    game_id: str,
    home_team: str,
    away_team: str,
    kickoff: datetime,
    now: datetime,
    odds_rows: list[dict],
    reference_sportsbook_preference: list[str],
) -> CandidateGenerationResult:
    """`odds_rows` is every already-persisted `odds_snapshots` row for
    this game (any sportsbook, any market_type, any age) -- this function
    does the sportsbook selection, freshness filtering, and V1 market
    scoping itself; callers pass the raw read-back, not a pre-filtered
    set."""
    sportsbook = select_reference_sportsbook(
        odds_rows, reference_sportsbook_preference=reference_sportsbook_preference, now=now, kickoff=kickoff
    )
    if sportsbook is None:
        return CandidateGenerationResult(
            sportsbook_used=None,
            candidates=(),
            skipped_markets=(),
            game_skipped_reason="no_configured_sportsbook_has_fresh_data",
        )

    candidates: list[MarketCandidate] = []
    skipped: list[SkippedMarket] = []
    seen_keys: set[str] = set()

    for market_type in _V1_MARKET_TYPES:
        row = _latest_row(odds_rows, sportsbook=sportsbook, market_type=market_type)
        if row is None:
            skipped.append(SkippedMarket(market_type=market_type, reason="no_snapshot"))
            continue
        if not _is_fresh(captured_at=row["captured_at"], now=now, kickoff=kickoff):
            skipped.append(SkippedMarket(market_type=market_type, reason="stale_snapshot"))
            continue
        for candidate in _candidates_from_row(
            row, game_id=game_id, sportsbook=sportsbook, market_type=market_type, home_team=home_team, away_team=away_team
        ):
            key = candidate_key(candidate)
            if key in seen_keys:  # defensive dedup -- see module docstring
                continue
            seen_keys.add(key)
            candidates.append(candidate)

    return CandidateGenerationResult(
        sportsbook_used=sportsbook, candidates=tuple(candidates), skipped_markets=tuple(skipped)
    )
