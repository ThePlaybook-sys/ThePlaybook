"""Tests for app.context_intelligence.player_performance (Player
Performance Context Foundation pass, 2026-09-15). Pure functions, no I/O.

Two groups: synthetic mechanism tests (dedup/point-in-time/completeness
behavior, using small invented fixtures to exercise each rule in
isolation), and the real proof (`TestJSNSeaNeRealProof`) -- built from
the EXACT live `player_stats`/`games`/`players` values queried against
DEV on 2026-09-15, not synthesized, proving this module's real behavior
against the real SEA@NE duplicate-row case end to end."""
from __future__ import annotations

from datetime import datetime, timezone

from app.context_intelligence.player_performance import (
    PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION,
    compute_player_performance_context,
    resolve_player_game_observations,
)
from app.context_intelligence.scoring import INSUFFICIENT_SAMPLE_FLOOR

GAME_A = "game-a"
GAME_B = "game-b"
GAME_FUTURE = "game-future"
PLAYER = "player-1"


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
    GAME_A: {"scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"},
    GAME_B: {"scheduled_start": "2026-09-13T17:00:00+00:00", "home_team": "Seattle Seahawks", "away_team": "New England Patriots"},
    GAME_FUTURE: {"scheduled_start": "2026-09-21T17:00:00+00:00", "home_team": "SEA", "away_team": "DEN"},
}

TARGET_TS = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# resolve_player_game_observations -- mechanism tests
# --------------------------------------------------------------------------


def test_single_real_observation_exposes_every_required_field():
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_name="Test Player", position="WR", player_team_name="Seattle Seahawks",
    )
    assert len(observations) == 1
    obs = observations[0]
    assert obs.player_id == PLAYER
    assert obs.game_id == GAME_A
    assert obs.event_timestamp == "2026-09-10T00:20:00+00:00"
    assert obs.player_name == "Test Player"
    assert obs.position == "WR"
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


def test_opponent_resolves_on_exact_team_name_match():
    rows = [_row(row_id="r1", game_id=GAME_B, created_at="2026-09-13T18:00:00+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_team_name="Seattle Seahawks",
    )
    obs = observations[0]
    assert obs.opponent == "New England Patriots"
    assert obs.home_or_away == "home"


def test_opponent_stays_none_on_format_mismatch_rather_than_guessing():
    """The live-confirmed SEA@NE shape: games.home_team/away_team store
    short codes ('SEA'/'NE'), not teams.name's full names -- must not be
    fuzzy-matched, must be disclosed as a real, named limitation."""
    rows = [_row(row_id="r1", game_id=GAME_A, created_at="2026-09-10T20:38:42+00:00")]
    observations = resolve_player_game_observations(
        rows, GAMES, player_id=PLAYER, target_event_timestamp=TARGET_TS,
        player_team_name="Seattle Seahawks",  # games.home_team is "SEA", not this
    )
    obs = observations[0]
    assert obs.opponent is None
    assert obs.home_or_away is None
    assert any("could not be determined" in note for note in obs.reliability_limitations)


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
    )
    assert result.sample_size == 2
    assert result.insufficient_evidence is False
    assert result.data_completeness == "joined"
    # confidence is still None -- no trend/consistency methodology exists yet even above the floor.
    assert result.confidence is None


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


# --------------------------------------------------------------------------
# Real proof: Jaxon Smith-Njigba, SEA@NE (2026-09-10) -- verbatim live DEV
# values, queried 2026-09-15. Not synthesized.
# --------------------------------------------------------------------------

JSN_PLAYER_ID = "c9b7de10-b380-45e4-90a3-f98444dce258"
SEA_NE_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"

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

SEA_NE_GAME = {"scheduled_start": "2026-09-10T00:20:00+00:00", "home_team": "SEA", "away_team": "NE"}

#: Real time this proof was run against DEV, per the session's own
#: real-time confirmation -- used as target_event_timestamp so the
#: point-in-time rule is exercised against a real "now," not an
#: artificially early cutoff.
PROOF_TARGET_TS = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)


class TestJSNSeaNeRealProof:
    """Section 5 of the directive: exactly one historical game
    observation, real performance/usage evidence, provenance,
    completeness, known unavailable context, no duplicate inflation --
    proven against the exact live DEV values, not synthetic data."""

    def _observations(self):
        return resolve_player_game_observations(
            JSN_SEA_NE_RAW_ROWS,
            {SEA_NE_GAME_ID: SEA_NE_GAME},
            player_id=JSN_PLAYER_ID,
            target_event_timestamp=PROOF_TARGET_TS,
            player_name="Jaxon Smith-Njigba",
            position="WR",
            player_team_name="Seattle Seahawks",
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
            player_team_name="Seattle Seahawks",
        )
        assert result.data_completeness == "joined"
        assert result.sample_size == 1
        assert result.insufficient_evidence is True  # honestly below the 2-game floor -- not a trend proof
        obs = result.facts["observations"][0]
        # Known unavailable context, disclosed rather than silently omitted:
        assert obs["opponent"] is None  # games.home_team "SEA" != teams.name "Seattle Seahawks"
        assert any("could not be determined" in note for note in obs["reliability_limitations"])
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
