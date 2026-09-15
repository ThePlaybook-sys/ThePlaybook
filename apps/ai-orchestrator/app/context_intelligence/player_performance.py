"""Historical player-performance Context Intelligence dimension. Built as
a standalone foundation in the Player Performance Context Foundation pass
(2026-09-15, "MANSA -- PHASE 8 PLAYER PERFORMANCE CONTEXT FOUNDATION") and
**registered as a real, official `engine.py` `SUPPORTED_DIMENSIONS` entry**
in the Player Performance Engine Integration pass (2026-09-15,
HQ-authorized "MANSA -- PHASE 8 PLAYER PERFORMANCE ENGINE INTEGRATION",
same day) -- see `engine.py`'s own module docstring for exactly how it is
now reached through `build_contextual_intelligence`'s normal
supported-dimension path. **Still not wired into `build_evidence()` or
any recommendation path** -- that remains a separate, later,
explicitly-deferred decision per this pass's own explicit boundary.

**This is a ONE-GAME foundation, not the multi-game Context Assembly
Proof.** The 2026-09-15 readiness reassessment found, live, that every
real MSF-confirmed-complete game belongs to the same NFL week -- zero
players anywhere have more than one real historical game yet. This
module is built to be correct and safe THE MOMENT a second real game
exists for any player, without further code changes (see "Future
multi-game path" below); it does not manufacture a second game to prove
that today.

**What this module is responsible for, and what it deliberately is
not:**
- Reads real `player_stats` rows only -- never invents a stat, never
  computes a derived metric the source data doesn't already carry
  (e.g. no yards-per-target ratio synthesized here; `passYardsPerAtt`
  etc. are only ever surfaced when MSF's own payload already computed
  them).
- Resolves exactly one canonical observation per real (player_id,
  game_id) pair via `observation_identity.resolve_canonical_observation`
  -- see that module's own docstring for the live-investigated root
  cause of the known SEA@NE duplicate-row case and why "most recent
  `created_at` wins" is the chosen rule. No row is ever deleted;
  duplicates are disclosed via `duplicate_raw_row_count`, never hidden.
- Enforces point-in-time safety using the historical game's own
  `scheduled_start` (event chronology) compared against an explicit
  `target_event_timestamp` -- never `player_stats.created_at` (an
  ingestion timestamp, not an observation timestamp; see
  `observation_identity.py`'s own docstring for why reusing it for
  eligibility, rather than tie-breaking, would be unsafe). A historical
  game whose own kickoff is not strictly before the target event is
  excluded outright, never included with a caveat -- see `PLAYER_
  PERFORMANCE_POINT_IN_TIME_LIMITATION` for the one honestly-labeled
  gap this rule cannot close (same-day/near-simultaneous proximity,
  since `player_stats` carries no true capture timestamp to verify
  against).
- Populates the new `data_completeness` field (`models.py`,
  `DATA_COMPLETENESS_VALUES`) -- `"joined"` when at least one real,
  point-in-time-eligible, deduplicated observation exists for the
  target player; `"unavailable"` otherwise. Never `"partial"` from this
  module -- exactly like `point_in_time.py`'s own established
  discipline, "partial" is reserved for a judgment about which required
  evidence *components* are missing, which this module does not attempt
  to make at the dimension level (individual observations' own
  `reliability_limitations` carry that nuance instead).
- Reuses `scoring.py`'s existing `INSUFFICIENT_SAMPLE_FLOOR`/
  `MIN_SAMPLE_FOR_FULL_CONFIDENCE`/`recency_weight` verbatim, applied to
  a different population than every other dimension: not "how many
  OTHER comparable games exist," but "how many of THIS PLAYER's own real
  historical games exist" -- exactly the distinction the 2026-09-09
  design doc flagged and deferred to whoever built this. With
  `sample_size` always 1 today (see above), `insufficient_evidence` is
  always `True` and `confidence`/`similarity_score` are always `None` --
  this is the correct, honest behavior of the existing shared floor
  applied to a real, if small, population, not a special case coded for
  this pass.
- `similarity_score` is always `None` from this dimension, deliberately
  -- a player's own performance history has no "similarity to other
  games" concept the way weather/market/news/venue's contextual pools
  do; documented here rather than silently left unexplained.
- `RECENCY_HALF_LIFE_DAYS` (14.0, `scoring.py`) is reused as-is per the
  2026-09-09 design doc's own instruction to flag, not resolve: a
  player's recent-form signal plausibly wants a shorter half-life than
  weather/venue/market's cross-game similarity halflife, since role and
  usage can change week to week in a way a stadium's roof type does not.
  Not changed by this pass.

**Opponent identity (Engine Integration pass fix)** no longer reads
`games.home_team`/`away_team` free text at all -- see
`resolve_opponent_by_team_id`'s and `extract_msf_team_provider_ids`'s own
docstrings below for the real, deterministic, provider-identity-based
replacement for the prior pass's text-matching approach, which the JSN
proof showed fails on real rows.

**Boundary (per this pass's explicit HQ instruction):** does not modify
`app.agents.probability_modeling.ProbabilityModelingAgent.build_evidence`,
does not change recommendation behavior, makes no provider calls, and
does not touch injuries/lineup-breadth/game-state-PBP or add any trend-
scoring methodology (each independently confirmed unsolved/deferred by
the 2026-09-15 reassessment and the prior foundation pass).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.context_intelligence.models import ContextualDimensionResult, ProvenanceRef
from app.context_intelligence.observation_identity import resolve_canonical_observation
from app.context_intelligence.scoring import INSUFFICIENT_SAMPLE_FLOOR, parse_ts, recency_weight

#: Real, reliable volume/usage fields this module will surface as
#: `role_usage_signals` when present in a canonical row's own `stats`
#: payload -- every one of these is a field MSF's real box-score response
#: already computes; nothing here is derived by this module. Grouped by
#: stat category exactly as the source payload groups them.
_ROLE_USAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "passing": ("passAttempts", "passCompletions", "passYards", "passTD", "passInt"),
    "rushing": ("rushAttempts", "rushYards", "rushTD"),
    "receiving": ("targets", "receptions", "recYards", "recTD"),
}

#: Always present, regardless of sample size -- this dimension measures a
#: player's OWN history, never a cross-game similarity pool; stated
#: explicitly so a reader never mistakes `data_completeness="joined"` for
#: a trend/consistency claim (that is what `insufficient_evidence`/
#: `confidence` are for, and both stay honest -- see module docstring).
_STANDING_CONFOUNDER = (
    "This dimension describes a specific player's own real historical game(s), never a "
    "predictive or outcome-linked claim, and never a comparison to other players' or other "
    "games' performance."
)

#: The one honestly-labeled point-in-time gap this module's rule cannot
#: close -- always included in `reliability_limitations`, per this pass's
#: explicit instruction to label rather than pretend.
PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION = (
    "Eligibility is determined by comparing the historical game's own kickoff "
    "(games.scheduled_start) against the target event timestamp -- player_stats itself carries "
    "no observation/ingestion timestamp, so this guarantees a historical game occurring at or "
    "after the target event is never included, but cannot verify finer-grained timing (e.g. "
    "whether the box score was actually captured before the target event, for two events on the "
    "same real day). Treat this as 'no game-level look-ahead,' not as sub-day precision."
)


@dataclass(frozen=True)
class PlayerGameObservation:
    """One real, deduplicated, point-in-time-eligible player/game
    observation -- the atomic unit this module produces. Every field
    required by this pass's own directive is present; any field this
    module cannot honestly populate is `None` (or an empty tuple),
    never a fabricated placeholder."""

    player_id: str
    game_id: str
    event_timestamp: str  # ISO -- the historical game's own scheduled_start
    player_name: str | None
    position: str | None  # players.position -- current/static, see reliability_limitations
    opponent: str | None  # None when games.home_team/away_team could not be matched to a real team name
    home_or_away: str | None  # "home" | "away" | None
    stats: dict  # the full, real, verbatim canonical row's stats payload -- nothing stripped
    role_usage_signals: dict  # curated real subset of `stats`, excluding source-flagged-unreliable fields
    unreliable_fields: tuple[str, ...]  # read from stats["_unreliable_fields"], never invented here
    reliability_limitations: tuple[str, ...]
    provenance: tuple[ProvenanceRef, ...]
    duplicate_raw_row_count: int  # 1 == no duplicate; >1 discloses a real known duplicate case
    canonical_row_id: str | None

    def to_json(self) -> dict:
        return {
            "player_id": self.player_id,
            "game_id": self.game_id,
            "event_timestamp": self.event_timestamp,
            "player_name": self.player_name,
            "position": self.position,
            "opponent": self.opponent,
            "home_or_away": self.home_or_away,
            "stats": self.stats,
            "role_usage_signals": self.role_usage_signals,
            "unreliable_fields": list(self.unreliable_fields),
            "reliability_limitations": list(self.reliability_limitations),
            "provenance": [
                {
                    "table": p.table,
                    "source": p.source,
                    "row_count": p.row_count,
                    "earliest_at": p.earliest_at,
                    "latest_at": p.latest_at,
                }
                for p in self.provenance
            ],
            "duplicate_raw_row_count": self.duplicate_raw_row_count,
            "canonical_row_id": self.canonical_row_id,
        }


def _extract_role_usage_signals(stats: dict) -> tuple[dict, tuple[str, ...]]:
    """Splits a real `stats` payload into (a) the curated, reliable
    role/usage subset this module will surface, and (b) the field names
    the SOURCE PIPELINE ITSELF already flags as unreliable (`stats.
    _unreliable_fields`, e.g. `snapCounts`) -- never re-derived or
    guessed here, only read and respected. A flagged top-level category
    (e.g. `"snapCounts"`) excludes that whole category from the curated
    subset; the raw values remain fully visible in the observation's own
    `stats` field, never deleted."""
    unreliable = tuple(stats.get("_unreliable_fields", ()))
    signals: dict = {}
    for category, field_names in _ROLE_USAGE_FIELDS.items():
        if category in unreliable:
            continue
        category_stats = stats.get(category)
        if not isinstance(category_stats, dict):
            continue
        values = {name: category_stats[name] for name in field_names if name in category_stats}
        if values:
            signals[category] = values
    return signals, unreliable


#: Real, deterministic opponent identity resolution (Player Performance
#: Engine Integration pass, 2026-09-15, HQ-authorized "MANSA -- PHASE 8
#: PLAYER PERFORMANCE ENGINE INTEGRATION"). Replaces the prior pass's
#: `games.home_team`/`away_team` free-text matching, which the JSN proof
#: showed fails for real rows (`"SEA"`/`"NE"` vs. `teams.name`'s
#: `"Seattle Seahawks"`/`"New England Patriots"`) -- **not fixed by
#: guessing or by a hardcoded abbreviation table**, but by routing through
#: real, already-persisted, provider-scoped canonical identity data this
#: project already has:
#:
#:   game_events.raw_payload (MySportsFeeds game_boxscore raw capture)
#:       -> body.game.homeTeam.id / body.game.awayTeam.id
#:       (real MySportsFeeds numeric team identifiers, live-confirmed:
#:        homeTeam.id=79/awayTeam.id=50 for the real SEA@NE capture)
#:   -> team_provider_ids (provider_name='mysportsfeeds', provider_team_id)
#:       -> team_id -> teams.name
#:       (the SAME real mapping table `app.persistence.team_stats`/other
#:       sports-intel-layer identity modules already rely on)
#:
#: This chain is exact-match-only (numeric provider-id equality, never a
#: fuzzy/name-similarity heuristic) and names no team, abbreviation, or
#: player literally anywhere in this module's own code -- every value
#: compared is read from a real row. `extract_msf_team_provider_ids` is
#: the one MySportsFeeds-shape-specific piece (isolated here, not
#: pretended to be provider-generic); `resolve_opponent_by_team_id` is
#: fully generic, operating only on already-resolved real team_ids.


def extract_msf_team_provider_ids(raw_payload: dict) -> tuple[str, str] | None:
    """Pure, no I/O. Reads the real MySportsFeeds numeric team identifiers
    a genuine `game_boxscore` raw capture already carries at `body.game.
    homeTeam.id`/`body.game.awayTeam.id` -- live-confirmed against the
    real SEA@NE `game_events` row (2026-09-15). Returns `None` (never a
    guess, never a partial tuple) for any payload that doesn't have this
    exact real MSF shape -- a different provider's raw payload, a
    malformed/incomplete capture, or a missing key all resolve the same
    honest way: 'not extractable,' handled by the caller as 'opponent
    unavailable for this game,' never silently worked around."""
    try:
        game_block = raw_payload["body"]["game"]
        home_id = game_block["homeTeam"]["id"]
        away_id = game_block["awayTeam"]["id"]
    except (KeyError, TypeError):
        return None
    if home_id is None or away_id is None:
        return None
    return str(home_id), str(away_id)


def resolve_opponent_by_team_id(
    identity: dict | None, *, player_team_id: str | None
) -> tuple[str | None, str | None]:
    """Fully generic, provider-agnostic, pure -- operates only on
    already-resolved real `team_id`s (never provider-specific ids, never
    free text). `identity` is one game's resolved `{"home_team_id",
    "home_team_name", "away_team_id", "away_team_name"}` entry (built by
    `app.persistence.context_intelligence_reads.resolve_team_identity_for_games`,
    which does the real, provider-specific work this function deliberately
    doesn't do). Exact `team_id` equality only -- no fuzzy matching
    anywhere in this function, matching this pass's explicit instruction.
    Returns `(None, None)`, honestly, when identity wasn't resolvable for
    this game, or the player's own team_id is unknown, or (a genuine
    anomaly) it matches neither side -- never a guess in any of these
    cases."""
    if identity is None or player_team_id is None:
        return None, None
    if player_team_id == identity.get("home_team_id"):
        return identity.get("away_team_name"), "home"
    if player_team_id == identity.get("away_team_id"):
        return identity.get("home_team_name"), "away"
    return None, None


_NO_PLAYER_REQUESTED_REASON = "no player_id was provided for this contextual intelligence request"


def no_player_requested_result() -> ContextualDimensionResult:
    """Returned by `engine.py` when `build_contextual_intelligence` is
    called without a `player_id` -- a legitimately different reason than
    any `unsupported.py` stub (those mean 'no real data/code path exists
    at all'; this means 'no data path exists for THIS call because no
    player was named'), so it is not borrowed from that module."""
    return ContextualDimensionResult(
        dimension="player_performance",
        context_dimensions_used=(),
        sample_size=0,
        similarity_score=None,
        recency_weighting=None,
        confidence=None,
        confounders=(_NO_PLAYER_REQUESTED_REASON,),
        insufficient_evidence=True,
        insufficient_evidence_reason=_NO_PLAYER_REQUESTED_REASON,
        provenance=(),
        facts={},
        data_completeness="unavailable",
    )


def resolve_player_game_observations(
    player_stats_rows: list[dict],
    games_by_id: dict[str, dict],
    *,
    player_id: str,
    target_event_timestamp: datetime | str,
    player_name: str | None = None,
    position: str | None = None,
    player_team_id: str | None = None,
    team_identity_by_game: dict[str, dict] | None = None,
    now: datetime | None = None,
) -> list[PlayerGameObservation]:
    """Pure function over already-fetched rows -- no I/O, directly
    unit-testable, matching every other dimension module's own
    convention. `player_stats_rows` may hold rows for many players/games
    at once (the "download once" shape); this function filters to
    `player_id` itself. `games_by_id` must map `game_id -> {"scheduled_
    start"}` (only the kickoff is required for point-in-time safety --
    `home_team`/`away_team` text is no longer read by this function at
    all, see `resolve_opponent_by_team_id`'s own docstring for why).
    `team_identity_by_game`, when provided, must map `game_id ->
    {"home_team_id", "home_team_name", "away_team_id", "away_team_name"}`
    -- real, already-resolved team identity (built by
    `app.persistence.context_intelligence_reads.resolve_team_identity_for_games`),
    used only for opponent/home-away resolution. A game missing from
    `games_by_id` is excluded entirely (point-in-time safety cannot be
    verified without its kickoff, so it is never included with a caveat
    -- the same "exclude, never guess" discipline `point_in_time.py`
    already establishes for missing data); a game missing from
    `team_identity_by_game` still produces an observation, just with
    `opponent=None` and a disclosed reliability limitation, since
    opponent identity is a nice-to-have, not a point-in-time-safety
    requirement.

    Returns one `PlayerGameObservation` per real, point-in-time-eligible,
    deduplicated (player_id, game_id) pair -- ordered oldest-event-first,
    the same convention `select_unenrolled_eligible_games`/`select_due_
    msf_postgame_games` already use elsewhere in this project (oldest-
    first is always the safest default ordering for anything eventually
    consumed under a per-tick/per-call cap)."""
    now = now or datetime.now(timezone.utc)
    target_ts = parse_ts(target_event_timestamp)

    rows_by_game: dict[str, list[dict]] = {}
    for row in player_stats_rows:
        if row.get("player_id") != player_id:
            continue
        rows_by_game.setdefault(row["game_id"], []).append(row)

    observations: list[PlayerGameObservation] = []
    for game_id, rows in rows_by_game.items():
        game = games_by_id.get(game_id)
        if game is None or not game.get("scheduled_start"):
            continue

        event_ts = parse_ts(game["scheduled_start"])
        if not (event_ts < target_ts):
            continue

        resolution = resolve_canonical_observation(rows, id_field="id", tie_break_field="created_at")
        canonical_row = resolution.canonical
        stats = canonical_row.get("stats") or {}

        role_usage_signals, unreliable_fields = _extract_role_usage_signals(stats)
        identity = (team_identity_by_game or {}).get(game_id)
        opponent, home_or_away = resolve_opponent_by_team_id(identity, player_team_id=player_team_id)

        limitations: list[str] = [PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION]
        if resolution.duplicate_row_count > 1:
            limitations.append(
                f"{resolution.duplicate_row_count} raw player_stats rows exist for this "
                f"(player_id, game_id) pair; the most recently created row "
                f"(id={canonical_row.get('id')!r}) was selected as canonical per this module's "
                f"deterministic observation-identity rule (observation_identity.py). The other "
                f"{resolution.duplicate_row_count - 1} row(s) remain preserved, untouched, in "
                f"player_stats -- nothing was deleted or overwritten."
            )
        if unreliable_fields:
            limitations.append(
                f"Source pipeline flags {list(unreliable_fields)} as unreliable at this ingestion "
                f"tier ({stats.get('_unreliable_fields_reason', 'no reason recorded')}) -- excluded "
                f"from role_usage_signals, retained verbatim in this observation's own `stats` field."
            )
        if opponent is None:
            limitations.append(
                "Opponent/home-away could not be determined via real provider identity data: "
                "this requires a real MySportsFeeds game_events raw capture for this game "
                "(providing body.game.homeTeam.id/awayTeam.id) AND a team_provider_ids mapping "
                "for both teams AND a resolvable player_team_id -- when any of these is missing, "
                "or the player's own team_id matches neither resolved side, opponent stays "
                "unresolved rather than guessed (never a fuzzy/text match)."
            )
        if position is None:
            limitations.append("No position on file for this player (players.position is null).")
        else:
            limitations.append(
                "Position is sourced from players.position, a current/static field -- not tracked "
                "historically per game, used here as a reasonable proxy since position rarely "
                "changes within a season, not independently verified as-of this specific game."
            )

        provenance = (
            ProvenanceRef(
                table="player_stats",
                source=None,  # no provider_name column on this table -- see ProvenanceRef's own docstring rule
                row_count=resolution.duplicate_row_count,
                earliest_at=None,
                latest_at=None,
            ),
        )

        observations.append(
            PlayerGameObservation(
                player_id=player_id,
                game_id=game_id,
                event_timestamp=event_ts.isoformat(),
                player_name=player_name,
                position=position,
                opponent=opponent,
                home_or_away=home_or_away,
                stats=stats,
                role_usage_signals=role_usage_signals,
                unreliable_fields=unreliable_fields,
                reliability_limitations=tuple(limitations),
                provenance=provenance,
                duplicate_raw_row_count=resolution.duplicate_row_count,
                canonical_row_id=canonical_row.get("id"),
            )
        )

    observations.sort(key=lambda obs: obs.event_timestamp)
    return observations


def compute_player_performance_context(
    player_stats_rows: list[dict],
    games_by_id: dict[str, dict],
    *,
    player_id: str,
    target_event_timestamp: datetime | str,
    player_name: str | None = None,
    position: str | None = None,
    player_team_id: str | None = None,
    team_identity_by_game: dict[str, dict] | None = None,
    now: datetime | None = None,
) -> ContextualDimensionResult:
    """Wraps `resolve_player_game_observations` into the shared
    `ContextualDimensionResult` shape every other dimension already
    returns -- see module docstring for why `similarity_score` is always
    `None`, `data_completeness` is never `"partial"` from this function,
    and `insufficient_evidence`/`confidence` are governed by the same
    `INSUFFICIENT_SAMPLE_FLOOR` every other dimension already uses,
    applied to a different population (this player's own real games)."""
    now = now or datetime.now(timezone.utc)
    observations = resolve_player_game_observations(
        player_stats_rows,
        games_by_id,
        player_id=player_id,
        target_event_timestamp=target_event_timestamp,
        player_name=player_name,
        position=position,
        player_team_id=player_team_id,
        team_identity_by_game=team_identity_by_game,
        now=now,
    )

    provenance = (
        ProvenanceRef(
            table="player_stats",
            source=None,
            row_count=sum(obs.duplicate_raw_row_count for obs in observations),
            earliest_at=observations[0].event_timestamp if observations else None,
            latest_at=observations[-1].event_timestamp if observations else None,
        ),
    )

    if not observations:
        return ContextualDimensionResult(
            dimension="player_performance",
            context_dimensions_used=(),
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER,),
            insufficient_evidence=True,
            insufficient_evidence_reason=(
                f"no real, point-in-time-eligible player_stats observation exists for "
                f"player_id={player_id!r} before {parse_ts(target_event_timestamp).isoformat()}"
            ),
            provenance=provenance,
            facts={},
            data_completeness="unavailable",
        )

    sample_size = len(observations)
    most_recent = observations[-1]
    recency = recency_weight(parse_ts(most_recent.event_timestamp), now=now)

    #: The real stat categories actually populated across the included
    #: observations (e.g. "receiving", "rushing") -- never a fixed list,
    #: since which categories a real player's own games carry varies.
    dimensions_used = tuple(
        sorted({category for obs in observations for category in obs.role_usage_signals})
    )

    confounders = [_STANDING_CONFOUNDER]
    if sample_size < INSUFFICIENT_SAMPLE_FLOOR:
        confounders.append(
            f"fewer than {INSUFFICIENT_SAMPLE_FLOOR} real historical games exist for this player yet "
            f"({sample_size} available) -- no trend or consistency claim is possible from this alone."
        )

    return ContextualDimensionResult(
        dimension="player_performance",
        context_dimensions_used=dimensions_used,
        sample_size=sample_size,
        similarity_score=None,
        recency_weighting=round(recency, 4),
        # Always None from this dimension -- no trend/consistency methodology has been designed
        # yet even for sample_size >= INSUFFICIENT_SAMPLE_FLOOR (a future, separate pass; see
        # module docstring's "Future multi-game path"), so nothing here would be honest to report.
        confidence=None,
        confounders=tuple(confounders),
        insufficient_evidence=sample_size < INSUFFICIENT_SAMPLE_FLOOR,
        insufficient_evidence_reason=(
            None
            if sample_size >= INSUFFICIENT_SAMPLE_FLOOR
            else f"only {sample_size} real historical game(s) available (minimum {INSUFFICIENT_SAMPLE_FLOOR} required)"
        ),
        provenance=provenance,
        facts={"game_count": sample_size, "observations": [obs.to_json() for obs in observations]},
        data_completeness="joined",
    )


__all__ = [
    "PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION",
    "PlayerGameObservation",
    "extract_msf_team_provider_ids",
    "resolve_opponent_by_team_id",
    "no_player_requested_result",
    "resolve_player_game_observations",
    "compute_player_performance_context",
]
