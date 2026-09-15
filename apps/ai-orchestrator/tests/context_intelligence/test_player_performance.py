"""Tests for app.context_intelligence.player_performance (Player
Performance Context Foundation pass, 2026-09-15; Engine Integration pass,
2026-09-15). Pure functions, no I/O.

Three groups: synthetic mechanism tests (dedup/point-in-time/completeness
behavior, using small invented fixtures to exercise each rule in
isolation), opponent-identity mechanism tests (the real, deterministic
provider-identity chain, Engine Integration pass), and the real proof
(`TestJSNSeaNeRealProof`) -- built from the EXACT live `player_stats`/
`games`/`game_events`/`team_provider_ids`/`teams` values queried against
DEV on 2026-09-15, not synthesized, proving this module's real behavior
against the real SEA@NE duplicate-row case AND the real opponent-identity
fix end to end."""
from __future__ import annotations

from datetime import datetime, timezone

from app.context_intelligence.player_performance import (
    PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION,
    compute_player_performance_context,
    extract_msf_team_provider_ids,
    no_player_requested_result,
    resolve_opponent_by_team_id,
    resolve_player_game_observations,
)
from app.context_intelligence.scoring import INSUFFICIENT_SAMPLE_FLOOR

GAME_A = "game-a"
GAME_B = "game-b"
GAME_FUTURE = "game-future"
PLAYER = "player-1"
PLAYER_TEAM_ID = "team-seattle"
OPPONENT_TEAM_ID = "team-new-england"


def _stats(*, targets=5, receptions=3, recYards=40, recTD=0, offenseSnaps=30, unreliable=("snapCounts",)):
    return {
        "receiving": {"targets": targets, "receptions": receptions, "recYards": recYards, "recTD": recTD},
        "snapCounts": {"offenseSnaps": offenseSnaps},
        "_unreliable_fields": list(unreliable),
        "_unreliable_fields_reason": "test fixture: snapCounts flagged unreliable by source pipeline",
    }


def _row(*, row_id, game_id, created_at, stats=None):
    return {"id": row_id, "player_id": PLAYER, "game_id": game_id, "created_at": created_at, "stats": stats or _stats()}


GAMES = {
    GAME_A: {"scheduled_start": "2026-09-10T00:20:00+00:00"},
    GAME_B: {"scheduled_start": "2026-09-13T17:00:00+00:00"},
    GAME_FUTURE: {"scheduled_start": "2026-09-21T17:00:00+00:00"},
}

TEAM_IDENTITY = {
    GAME_A: {
        "home_team_id": PLAYER_TEAM_ID, "home_team_name": "Seattle Seahawks",
        "away_team_id": OPPONENT_TEAM_ID, "away_team_name": "New England Patriots",
    },
    GAME_B: {
        "home_team_id": PLAYER_TEAM_ID, "home_team_name": "Seattle Seahawks",
        "away_team_id": OPPONENT_TEAM_ID, "away_team_name": "New England Patriots",
    },
}

TARGET_TS = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# resolve_player_game_observations -- mechanism tests
# --------------------------------------------------------------------------


def test_single_real_observation_exposes_every_required_field():
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_name="Test Player", position="WR",
        player_team_id=PLAYER_TEAM_ID, team_identity_by_game=TEAM_IDENTITY,
    )
    assert len(observations) == 1
    obs = observations[0]
    assert obs.player_id == PLAYER
    assert obs.game_id == GAME_A
    assert obs.event_timestamp == "2026-09-10T00:20:00+00:00"
    assert obs.player_name == "Test Player"
    assert obs.position == "WR"
    assert obs.opponent == "New England Patriots"
    assert obs.home_or_away == "home"
    assert obs.role_usage_signals == {"receiving": {"targets": 5, "receptions": 3, "recYards": 40, "recTD": 0}}
    assert obs.stats["snapCounts"]["offenseSnaps"] == 30  # raw stats never stripped
    assert obs.unreliable_fields == ("snapCounts",)
    assert obs.duplicate_raw_row_count == 1
    assert obs.canonical_row_id == "r1"
    assert PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION in obs.reliability_limitations


def test_game_at_or_after_target_event_is_excluded():
    """The literal point-in-time-safety requirement: a game whose own
    kickoff has not yet occurred relative to the target event must never
    appear as historical evidence."""
    rows = [_row(row_id="r1", game_id=GAME_FUTURE, created_at="2026-09-21T20:00:00+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert observations == []


def test_game_exactly_at_target_timestamp_is_excluded_not_included():
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp="2026-09-10T00:20:00+00:00",
    )
    assert observations == []  # strict less-than, not less-than-or-equal


def test_missing_game_metadata_excludes_the_observation_entirely():
    """No games_by_id entry -> cannot verify point-in-time eligibility ->
    excluded outright, never included with a caveat (same 'exclude, never
    guess' discipline as point_in_time.py for missing data)."""
    rows = [_row(row_id="r1", game_id="unknown-game", created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert observations == []


def test_other_players_rows_are_ignored():
    rows = [{"id": "r1", "player_id": "someone-else", "game_id": GAME_A, "created_at": "2026-09-10T20:38:42+00:00", "stats": _stats()}]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert observations == []


def test_duplicate_rows_collapse_to_exactly_one_observation():
    """The core anti-duplicate-inflation proof, at the mechanism level:
    two raw rows for the same (player, game) must never produce two
    observations, and the discarded row must never be silently forgotten
    -- both are reflected in duplicate_raw_row_count and the disclosed
    reliability_limitations."""
    rows = [
        _row(row_id="old", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00", stats=_stats(offenseSnaps=0)),
        _row(row_id="new", game_id=GAME_A, created_at="2026-09-14T23:02:03+00:00", stats=_stats(offenseSnaps=45)),
    ]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert len(observations) == 1  # ONE observation, not two, despite two raw rows
    obs = observations[0]
    assert obs.canonical_row_id == "new"  # most recent created_at wins
    assert obs.duplicate_raw_row_count == 2
    assert obs.stats["snapCounts"]["offenseSnaps"] == 45  # the newer row's own value, not merged/averaged
    assert any("2 raw player_stats rows exist" in note for note in obs.reliability_limitations)
    assert any("nothing was deleted or overwritten" in note for note in obs.reliability_limitations)


def test_unreliable_fields_excluded_from_role_usage_but_kept_in_raw_stats():
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00", stats=_stats(unreliable=("snapCounts",)))]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    obs = observations[0]
    assert "snapCounts" not in obs.role_usage_signals
    assert "snapCounts" in obs.stats  # never deleted from the raw payload
    assert any("unreliable at this ingestion tier" in note for note in obs.reliability_limitations)


def test_missing_position_is_disclosed_not_fabricated():
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS, position=None,
    )
    obs = observations[0]
    assert obs.position is None
    assert any("No position on file" in note for note in obs.reliability_limitations)


def test_multiple_real_games_ordered_oldest_first():
    rows = [
        _row(row_id="r1", game_id=GAME_B, created_at="2026-09-13T18:00:00+00:00"),
        _row(row_id="r2", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00"),
    ]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert [obs.game_id for obs in observations] == [GAME_A, GAME_B]


# --------------------------------------------------------------------------
# Opponent identity resolution -- deterministic provider-identity chain
# (Engine Integration pass, 2026-09-15). No hardcoded team/abbreviation
# anywhere in these fixtures beyond generic test placeholders.
# --------------------------------------------------------------------------


def test_extract_msf_team_provider_ids_reads_real_payload_shape():
    raw_payload = {"body": {"game": {"id": 163541, "homeTeam": {"id": 79, "abbreviation": "SEA"}, "awayTeam": {"id": 50, "abbreviation": "NE"}}}}
    assert extract_msf_team_provider_ids(raw_payload) == ("79", "50")


def test_extract_msf_team_provider_ids_returns_none_for_unrecognized_shape():
    assert extract_msf_team_provider_ids({}) is None
    assert extract_msf_team_provider_ids({"body": {}}) is None
    assert extract_msf_team_provider_ids({"body": {"game": {"homeTeam": {}}}}) is None
    assert extract_msf_team_provider_ids({"unrelated": "shape"}) is None


def test_extract_msf_team_provider_ids_returns_none_when_either_id_is_null():
    raw_payload = {"body": {"game": {"homeTeam": {"id": None}, "awayTeam": {"id": 50}}}}
    assert extract_msf_team_provider_ids(raw_payload) is None


def test_resolve_opponent_by_team_id_home_side():
    identity = {"home_team_id": PLAYER_TEAM_ID, "home_team_name": "Home Team", "away_team_id": OPPONENT_TEAM_ID, "away_team_name": "Away Team"}
    opponent, home_or_away = resolve_opponent_by_team_id(identity, player_team_id=PLAYER_TEAM_ID)
    assert opponent == "Away Team"
    assert home_or_away == "home"


def test_resolve_opponent_by_team_id_away_side():
    identity = {"home_team_id": OPPONENT_TEAM_ID, "home_team_name": "Home Team", "away_team_id": PLAYER_TEAM_ID, "away_team_name": "Away Team"}
    opponent, home_or_away = resolve_opponent_by_team_id(identity, player_team_id=PLAYER_TEAM_ID)
    assert opponent == "Home Team"
    assert home_or_away == "away"


def test_resolve_opponent_by_team_id_none_when_identity_missing():
    """No real game_events/team_provider_ids resolution existed for this
    game -- honestly unresolved, never guessed."""
    opponent, home_or_away = resolve_opponent_by_team_id(None, player_team_id=PLAYER_TEAM_ID)
    assert opponent is None
    assert home_or_away is None


def test_resolve_opponent_by_team_id_none_when_player_team_id_missing():
    identity = {"home_team_id": PLAYER_TEAM_ID, "home_team_name": "Home Team", "away_team_id": OPPONENT_TEAM_ID, "away_team_name": "Away Team"}
    opponent, home_or_away = resolve_opponent_by_team_id(identity, player_team_id=None)
    assert opponent is None
    assert home_or_away is None


def test_resolve_opponent_by_team_id_none_when_player_team_matches_neither_side():
    """A genuine anomaly (player's own team_id resolves to neither side of
    this game) -- never forced into a guess."""
    identity = {"home_team_id": "team-x", "home_team_name": "X", "away_team_id": "team-y", "away_team_name": "Y"}
    opponent, home_or_away = resolve_opponent_by_team_id(identity, player_team_id="team-z")
    assert opponent is None
    assert home_or_away is None


def test_observation_opponent_stays_none_when_no_identity_resolved_for_game():
    """End-to-end mechanism proof: a game with no entry in
    team_identity_by_game (e.g. no real MySportsFeeds game_events row, or
    no team_provider_ids mapping) produces an observation with
    opponent=None and a disclosed, real reason -- not a text-matching
    guess, not a crash."""
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_team_id=PLAYER_TEAM_ID, team_identity_by_game={},  # nothing resolved for GAME_A
    )
    obs = observations[0]
    assert obs.opponent is None
    assert obs.home_or_away is None
    assert any("could not be determined via real provider identity data" in note for note in obs.reliability_limitations)


# --------------------------------------------------------------------------
# compute_player_performance_context -- dimension-level result
# --------------------------------------------------------------------------


def test_no_observations_is_unavailable_never_zero():
    result = compute_player_performance_context([], GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS)
    assert result.data_completeness == "unavailable"
    assert result.insufficient_evidence is True
    assert result.sample_size == 0
    assert result.confidence is None
    assert result.similarity_score is None
    assert result.facts == {}  # never a fabricated zero-valued facts dict


def test_single_observation_is_joined_but_insufficient_for_a_trend():
    """The exact real-substrate shape today: real evidence found (joined)
    but below INSUFFICIENT_SAMPLE_FLOOR, so no trend/confidence claim is
    made -- these are two different, correctly-independent signals."""
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    result = compute_player_performance_context(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert result.data_completeness == "joined"
    assert result.sample_size == 1
    assert result.insufficient_evidence is True  # 1 < INSUFFICIENT_SAMPLE_FLOOR
    assert result.confidence is None
    assert result.similarity_score is None
    assert result.recency_weighting is not None  # real, computable even with one observation
    assert result.facts["game_count"] == 1
    assert len(result.facts["observations"]) == 1


def test_reaching_the_sample_floor_flips_insufficient_evidence_off():
    """Synthetic-only mechanism proof (two invented games) -- confirms the
    shared INSUFFICIENT_SAMPLE_FLOOR machinery works correctly once a
    second real game exists; NOT a claim that two real games exist today
    (they do not -- see the module's own docstring and the 2026-09-15
    readiness reassessment)."""
    assert INSUFFICIENT_SAMPLE_FLOOR == 2
    rows = [
        _row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00"),
        _row(row_id="r2", game_id=GAME_B, created_at="2026-09-13T18:00:00+00:00"),
    ]
    result = compute_player_performance_context(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_team_id=PLAYER_TEAM_ID, team_identity_by_game=TEAM_IDENTITY,
    )
    assert result.sample_size == 2
    assert result.insufficient_evidence is False
    assert result.data_completeness == "joined"
    # confidence is still None -- no trend/consistency methodology exists yet even above the floor.
    assert result.confidence is None
    # Multi-game architecture proof: each observation is its own real game, both with resolved opponents.
    observations = result.facts["observations"]
    assert [obs["game_id"] for obs in observations] == [GAME_A, GAME_B]
    assert all(obs["opponent"] == "New England Patriots" for obs in observations)


def test_multi_game_still_collapses_correction_rows_within_each_game():
    """The full multi-game architecture proof (directive Section 5):
    TWO distinct real games for the same player, ONE of which also has a
    duplicate correction row -- must produce exactly two observations
    (one per game), with the duplicated game's own sample never inflated."""
    rows = [
        _row(row_id="a-old", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00", stats=_stats(offenseSnaps=0)),
        _row(row_id="a-new", game_id=GAME_A, created_at="2026-09-14T23:02:03+00:00", stats=_stats(offenseSnaps=45)),
        _row(row_id="b-only", game_id=GAME_B, created_at="2026-09-13T18:00:00+00:00"),
    ]
    result = compute_player_performance_context(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert result.sample_size == 2  # two distinct games, not three raw rows
    observations = result.facts["observations"]
    assert [obs["game_id"] for obs in observations] == [GAME_A, GAME_B]
    game_a_obs = observations[0]
    assert game_a_obs["duplicate_raw_row_count"] == 2  # correction row still disclosed within its own game
    assert game_a_obs["canonical_row_id"] == "a-new"
    game_b_obs = observations[1]
    assert game_b_obs["duplicate_raw_row_count"] == 1  # no correction row for this game


def test_duplicate_raw_rows_never_inflate_dimension_level_sample_size():
    """The dimension-level anti-inflation proof: two raw rows for the SAME
    game must produce sample_size=1, not 2."""
    rows = [
        _row(row_id="old", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00"),
        _row(row_id="new", game_id=GAME_A, created_at="2026-09-14T23:02:03+00:00"),
    ]
    result = compute_player_performance_context(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
    )
    assert result.sample_size == 1
    assert result.facts["game_count"] == 1
    assert len(result.facts["observations"]) == 1
    # provenance still discloses both raw rows existed, even though only one observation resulted
    assert result.provenance[0].row_count == 2


def test_no_player_requested_result_is_unavailable_not_a_crash():
    result = no_player_requested_result()
    assert result.dimension == "player_performance"
    assert result.data_completeness == "unavailable"
    assert result.insufficient_evidence is True
    assert result.sample_size == 0
    assert result.facts == {}


# --------------------------------------------------------------------------
# Real proof: Jaxon Smith-Njigba, SEA@NE (2026-09-10) -- verbatim live DEV
# values, queried 2026-09-15. Not synthesized. Includes the real MSF
# game_events raw-payload team-identity block and the real
# team_provider_ids/teams rows that resolve it -- the exact chain
# `app.persistence.context_intelligence_reads.resolve_team_identity_for_games`
# performs for real against Supabase; reproduced verbatim here so this
# test exercises the same real values without needing a live I/O client.
# --------------------------------------------------------------------------

JSN_PLAYER_ID = "c9b7de10-b380-45e4-90a3-f98444dce258"
SEA_NE_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
SEATTLE_TEAM_ID = "3ca09e7e-f92a-4fc8-9ba2-3c3144d58207"
NEW_ENGLAND_TEAM_ID = "918a529e-f9e7-4bf5-8957-de5f39af5ad2"

#: The real MySportsFeeds game_boxscore raw-payload team-identity block,
#: verbatim from the live game_events row for SEA@NE (2026-09-15 query):
#: homeTeam.id=79 (Seattle), awayTeam.id=50 (New England).
SEA_NE_RAW_GAME_EVENT_PAYLOAD = {
    "body": {
        "game": {
            "id": 163541,
            "homeTeam": {"id": 79, "abbreviation": "SEA"},
            "awayTeam": {"id": 50, "abbreviation": "NE"},
        }
    }
}

#: The exact two real player_stats rows confirmed live for JSN/SEA@NE on
#: 2026-09-15 -- the diagnostic-era capture (2026-09-10 20:38:42, real
#: offenseSnaps=0) and the real dispatcher-driven capture (2026-09-14
#: 23:02:03, real offenseSnaps=45). Every other field is byte-identical
#: between the two -- this is the exact live duplicate-row case
#: `observation_identity.py`'s own docstring investigates.
JSN_SEA_NE_STATS = {
    "fumbles": {"fumTD": 0, "fumLost": 0, "fumbles": 0, "offFumTD": 0, "fumForced": 0, "fumOppRec": 0, "fumOwnRec": 0, "fumRecYds": 0, "fumTotalRec": 0},
    "passing": {"passTD": 0, "passAvg": 0, "passInt": 0, "passLng": 0, "passPct": 0, "qbRating": 0, "passSackY": 0, "passSacks": 0, "passTDPct": 0, "passYards": 0, "pass20Plus": 0, "pass40Plus": 0, "passIntPct": 0, "passAttempts": 0, "passCompletions": 0, "passYardsPerAtt": 0},
    "rushing": {"rushTD": 0, "rushLng": 0, "rushYards": 0, "rush20Plus": 0, "rush40Plus": 0, "rushAverage": 0, "rushFumbles": 0, "rush1stDowns": 0, "rushAttempts": 0, "rush1stDownsPct": 0},
    "receiving": {"recTD": 1, "recLng": 45, "targets": 11, "recYards": 122, "rec20Plus": 2, "rec40Plus": 1, "recAverage": 15.2, "recFumbles": 0, "receptions": 8, "rec1stDowns": 5},
    "_unreliable_fields": ["snapCounts", "miscellaneous.gamesStarted"],
    "_unreliable_fields_reason": (
        "Gate B (2026-09-10, game 163541) observed these fields as uniformly zero across all 69 "
        "players and both team totals in a real completed-game payload, including players with "
        "substantial non-zero performance elsewhere in the same response. Schema-present, not "
        "confirmed real participation data at this tier -- do not treat as evidence of zero usage "
        "or as a reliable participation signal."
    ),
}

JSN_SEA_NE_RAW_ROWS = [
    {
        "id": "4026f70f-5b08-483d-88ba-c6a6bb07f07c",
        "player_id": JSN_PLAYER_ID,
        "game_id": SEA_NE_GAME_ID,
        "created_at": "2026-09-10T20:38:42.113431+00:00",
        "stats": {**JSN_SEA_NE_STATS, "snapCounts": {"defenseSnaps": 0, "offenseSnaps": 0, "specialTeamSnaps": 0}, "miscellaneous": {"gamesStarted": 0}},
    },
    {
        "id": "4ee8eae8-e213-4533-b099-3945d0d3fd41",
        "player_id": JSN_PLAYER_ID,
        "game_id": SEA_NE_GAME_ID,
        "created_at": "2026-09-14T23:02:03.657231+00:00",
        "stats": {**JSN_SEA_NE_STATS, "snapCounts": {"defenseSnaps": 0, "offenseSnaps": 45, "specialTeamSnaps": 0}, "miscellaneous": {"gamesStarted": 0}},
    },
]

SEA_NE_GAME = {"scheduled_start": "2026-09-10T00:20:00+00:00"}

#: Real time this proof was run against DEV, per the session's own
#: real-time confirmation -- used as target_event_timestamp so the
#: point-in-time rule is exercised against a real "now," not an
#: artificially early cutoff.
PROOF_TARGET_TS = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)


def _real_team_identity_for_sea_ne() -> dict:
    """Reproduces exactly what `resolve_team_identity_for_games` computes
    for real against Supabase, using the real extraction function plus
    the real, live-confirmed team_provider_ids values (msf 79 ->
    Seattle Seahawks, msf 50 -> New England Patriots) -- proves the real
    extraction step, not just a hand-built dict."""
    home_provider_id, away_provider_id = extract_msf_team_provider_ids(SEA_NE_RAW_GAME_EVENT_PAYLOAD)
    team_by_provider_id = {
        "79": {"team_id": SEATTLE_TEAM_ID, "name": "Seattle Seahawks"},
        "50": {"team_id": NEW_ENGLAND_TEAM_ID, "name": "New England Patriots"},
    }
    home = team_by_provider_id[home_provider_id]
    away = team_by_provider_id[away_provider_id]
    return {"home_team_id": home["team_id"], "home_team_name": home["name"], "away_team_id": away["team_id"], "away_team_name": away["name"]}


class TestJSNSeaNeRealProof:
    """Directive Section 4 (Real Engine Proof): exactly one historical
    game observation, real performance/usage evidence, resolved opponent
    identity via the real provider-identity chain, provenance,
    completeness, known unavailable context, no duplicate inflation --
    proven against the exact live DEV values, not synthetic data."""

    def _team_identity_by_game(self):
        return {SEA_NE_GAME_ID: _real_team_identity_for_sea_ne()}

    def _observations(self):
        return resolve_player_game_observations(
            JSN_SEA_NE_RAW_ROWS,
            {SEA_NE_GAME_ID: SEA_NE_GAME},
            player_id=JSN_PLAYER_ID,
            target_event_timestamp=PROOF_TARGET_TS,
            player_name="Jaxon Smith-Njigba",
            position="WR",
            player_team_id=SEATTLE_TEAM_ID,
            team_identity_by_game=self._team_identity_by_game(),
        )

    def test_exactly_one_observation_despite_two_real_raw_rows(self):
        observations = self._observations()
        assert len(observations) == 1
        assert observations[0].duplicate_raw_row_count == 2  # both real rows counted, never hidden

    def test_real_performance_and_usage_evidence_is_correct(self):
        obs = self._observations()[0]
        assert obs.role_usage_signals["receiving"] == {"targets": 11, "receptions": 8, "recYards": 122, "recTD": 1}
        # the canonical row is the newer, real-dispatcher capture
        assert obs.canonical_row_id == "4ee8eae8-e213-4533-b099-3945d0d3fd41"
        assert obs.stats["snapCounts"]["offenseSnaps"] == 45  # raw value preserved, not deleted
        assert "snapCounts" not in obs.role_usage_signals  # but excluded from the reliable usage view

    def test_resolved_opponent_identity_via_real_provider_chain(self):
        """The opponent-resolution fix, end to end, real values: Seattle's
        (JSN's team) real opponent in this real game is real,
        deterministically resolved New England Patriots -- via
        game_events raw payload -> team_provider_ids -> teams, never
        games.home_team/away_team text, never a guess."""
        obs = self._observations()[0]
        assert obs.opponent == "New England Patriots"
        assert obs.home_or_away == "home"
        # No "could not be determined" limitation should fire once real identity resolves.
        assert not any("could not be determined" in note for note in obs.reliability_limitations)

    def test_provenance_discloses_both_real_rows(self):
        obs = self._observations()[0]
        assert obs.provenance[0].table == "player_stats"
        assert obs.provenance[0].row_count == 2

    def test_completeness_is_joined_with_known_unavailable_context_disclosed(self):
        result = compute_player_performance_context(
            JSN_SEA_NE_RAW_ROWS,
            {SEA_NE_GAME_ID: SEA_NE_GAME},
            player_id=JSN_PLAYER_ID,
            target_event_timestamp=PROOF_TARGET_TS,
            player_name="Jaxon Smith-Njigba",
            position="WR",
            player_team_id=SEATTLE_TEAM_ID,
            team_identity_by_game=self._team_identity_by_game(),
        )
        assert result.data_completeness == "joined"
        assert result.sample_size == 1
        assert result.insufficient_evidence is True  # honestly below the 2-game floor -- not a trend proof
        obs = result.facts["observations"][0]
        assert obs["opponent"] == "New England Patriots"  # now resolved, not unavailable
        # Known unavailable context that remains honestly disclosed:
        assert any("unreliable at this ingestion tier" in note for note in obs["reliability_limitations"])
        assert any("2 raw player_stats rows exist" in note for note in obs["reliability_limitations"])

    def test_no_duplicate_inflation_at_the_dimension_level(self):
        result = compute_player_performance_context(
            JSN_SEA_NE_RAW_ROWS,
            {SEA_NE_GAME_ID: SEA_NE_GAME},
            player_id=JSN_PLAYER_ID,
            target_event_timestamp=PROOF_TARGET_TS,
        )
        assert result.sample_size == 1  # ONE game, not two, despite two real rows
        assert result.facts["game_count"] == 1

    def test_future_kickoff_would_correctly_exclude_this_game(self):
        """Point-in-time safety sanity check for the exact proof game: if
        asked "as of before this game's own kickoff," it must not appear
        at all."""
        before_kickoff = datetime(2026, 9, 9, tzinfo=timezone.utc)
        observations = resolve_player_game_observations(
            JSN_SEA_NE_RAW_ROWS, {SEA_NE_GAME_ID: SEA_NE_GAME},
            player_id=JSN_PLAYER_ID, target_event_timestamp=before_kickoff,
        )
        assert observations == []
