"""Tests for app.adapters.providers.mysportsfeeds_game_boxscore (MANSA
Phase 8 Player-Game Persistence Design + Implementation Pass, 2026-09-10).

Every test uses the real, committed Gate B fixture
(`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`) --
the exact, real HTTP 200 payload Gate B's one authorized MSF request
captured for completed game 163541 (NE @ SEA). NO live MySportsFeeds
calls are made anywhere in this file or by the module it tests, per HQ's
explicit "do not make any new provider calls in this pass" instruction --
`parse_game_boxscore` is a pure function over an already-fetched dict.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.models import PlayerStatLine
from app.adapters.providers.mysportsfeeds_game_boxscore import (
    UNRELIABLE_FIELD_PATHS,
    parse_game_boxscore,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "ops"
    / "fixtures"
    / "gate-b-msf-game-boxscore-163541-2026-09-10.json"
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def test_parses_the_real_fixture_into_69_player_stat_lines():
    """34 away (NE) + 35 home (SEA) = 69 real players, exactly matching
    Gate B's own reported player count."""
    result = parse_game_boxscore(_load_fixture())

    assert result.source == "mysportsfeeds"
    assert len(result.value) == 69
    assert all(isinstance(line, PlayerStatLine) for line in result.value)


def test_game_external_id_is_the_real_msf_game_id_for_every_line():
    """Every single line must carry the SAME game id -- this is a single
    completed game's boxscore, never conflated with a season aggregate or
    another game."""
    result = parse_game_boxscore(_load_fixture())

    game_ids = {line.game_external_id for line in result.value}
    assert game_ids == {"163541"}


def test_team_assignment_uses_the_real_abbreviations():
    result = parse_game_boxscore(_load_fixture())

    teams = {line.team for line in result.value}
    assert teams == {"NE", "SEA"}
    away_count = sum(1 for line in result.value if line.team == "NE")
    home_count = sum(1 for line in result.value if line.team == "SEA")
    assert away_count == 34
    assert home_count == 35


def test_real_non_zero_player_stats_are_extracted_correctly():
    """Drake Maye's real, non-zero, single-game stats -- proves this
    adapter extracts genuine performance data, not just identity
    scaffolding. 178 pass yards / 47 rush yards independently confirmed
    live during Gate B's own payload inspection."""
    result = parse_game_boxscore(_load_fixture())

    maye = next(line for line in result.value if line.player_external_id == "133837")
    assert maye.player_name == "Drake Maye"
    assert maye.team == "NE"
    assert maye.stats["passing"]["passYards"] == 178
    assert maye.stats["rushing"]["rushYards"] == 47


def test_provider_player_id_is_a_stable_string_join_key():
    result = parse_game_boxscore(_load_fixture())

    ids = [line.player_external_id for line in result.value]
    assert all(isinstance(pid, str) and pid.isdigit() for pid in ids)
    assert len(ids) == len(set(ids))  # no duplicate provider ids


def test_unreliable_fields_are_flagged_not_dropped_not_silently_trusted():
    """snapCounts/miscellaneous.gamesStarted are Gate B-confirmed
    unreliable (uniformly zero) -- this adapter must never strip them
    (provenance-preserving) and must never let them pass through
    unflagged (HQ's explicit "do not convert zero-valued provider
    placeholders into evidence of zero usage")."""
    result = parse_game_boxscore(_load_fixture())

    maye = next(line for line in result.value if line.player_external_id == "133837")
    # Raw MSF values are untouched -- still present, still real (zero, in
    # this real capture).
    assert maye.stats["snapCounts"] == {"offenseSnaps": 0, "defenseSnaps": 0, "specialTeamSnaps": 0}
    assert maye.stats["miscellaneous"]["gamesStarted"] == 0
    # And structurally, unmissably flagged as unreliable.
    assert maye.stats["_unreliable_fields"] == UNRELIABLE_FIELD_PATHS
    assert "not confirmed real participation" in maye.stats["_unreliable_fields_reason"]

    # Every one of the 69 lines carries the same disclosure -- not just
    # the sampled player.
    assert all(line.stats.get("_unreliable_fields") == UNRELIABLE_FIELD_PATHS for line in result.value)


def test_provider_reported_at_is_the_real_lastupdatedon_field():
    result = parse_game_boxscore(_load_fixture())

    assert result.provider_reported_at is not None
    assert result.provider_reported_at.isoformat().startswith("2026-09-10T12:45:08")


def test_real_player_position_is_extracted_from_the_raw_payload():
    """Position-contract fix (2026-09-11, Permanent Box Score Worker Build):
    MySportsFeeds' real player object carries `position` directly (e.g.
    Julian Ashby, id 166956, "LS") -- this must now surface on
    `PlayerStatLine.position`, not be silently dropped."""
    result = parse_game_boxscore(_load_fixture())

    maye = next(line for line in result.value if line.player_external_id == "133837")
    assert maye.position == "QB"

    ashby = next(line for line in result.value if line.player_external_id == "166956")
    assert ashby.position == "LS"


def test_every_real_player_line_has_a_real_non_empty_position():
    """All 69 real Gate B players carry a real, non-empty position string
    in the raw fixture -- proves this isn't a one-player coincidence."""
    result = parse_game_boxscore(_load_fixture())

    assert all(isinstance(line.position, str) and line.position for line in result.value)


def test_missing_position_is_null_never_invented():
    """A player row that genuinely lacks a `position` key must produce
    `position=None` -- never a default/guessed value (e.g. never "" or
    an arbitrary placeholder string)."""
    fixture = _load_fixture()
    entry = fixture["stats"]["away"]["players"][0]
    assert "position" in entry["player"]  # sanity: real fixture always has one
    del entry["player"]["position"]

    result = parse_game_boxscore(fixture)

    line = next(line for line in result.value if line.player_external_id == str(entry["player"]["id"]))
    assert line.position is None


def test_blank_position_string_is_treated_as_absent_not_invented():
    """A provider row with an empty-string position is evidence-free, not
    a real position value -- treated the same as a missing key, never
    passed through as an empty string."""
    fixture = _load_fixture()
    entry = fixture["stats"]["away"]["players"][0]
    entry["player"]["position"] = ""

    result = parse_game_boxscore(fixture)

    line = next(line for line in result.value if line.player_external_id == str(entry["player"]["id"]))
    assert line.position is None


def test_position_change_does_not_alter_persisted_stats_semantics():
    """Adding `position` to PlayerStatLine must not change the `stats`
    dict's own content in any way -- existing persisted stat semantics
    (Volume 3 `player_stats.stats`) are untouched by this fix."""
    result = parse_game_boxscore(_load_fixture())

    maye = next(line for line in result.value if line.player_external_id == "133837")
    assert "position" not in maye.stats
    assert maye.stats["passing"]["passYards"] == 178
    assert maye.stats["_unreliable_fields"] == UNRELIABLE_FIELD_PATHS


def test_malformed_player_row_is_skipped_not_guessed():
    fixture = _load_fixture()
    fixture["stats"]["away"]["players"] = fixture["stats"]["away"]["players"] + [
        {"player": {"id": 999999}, "playerStats": []},  # empty playerStats -- malformed
        {"player": {}, "playerStats": [{"passing": {}}]},  # missing player id -- malformed
    ]

    result = parse_game_boxscore(fixture)

    # Still exactly the 69 well-formed lines -- both malformed rows skipped.
    assert len(result.value) == 69
    assert "999999" not in {line.player_external_id for line in result.value}


def test_empty_payload_produces_no_lines_not_an_exception():
    result = parse_game_boxscore({"game": {"id": 163541}, "stats": {}, "lastUpdatedOn": None})

    assert result.value == []
    assert result.provider_reported_at is None
