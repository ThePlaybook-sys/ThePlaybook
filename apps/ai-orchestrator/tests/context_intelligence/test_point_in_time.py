"""Tests for app.context_intelligence.point_in_time (Phase 8 Point-in-
Time Context Retrieval pass, 2026-09-09) -- pure function, no I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.context_intelligence.point_in_time import (
    PointInTimeResult,
    resolve_injury_point_in_time,
    resolve_lineup_point_in_time,
    resolve_point_in_time,
    resolve_weather_point_in_time,
)

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)


def _row(entity_id_field: str, entity_id: str, *, captured_at: datetime, payload: dict | None = None) -> dict:
    row = {entity_id_field: entity_id, "captured_at": captured_at.isoformat()}
    row.update(payload or {})
    return row


def _resolve(rows: list[dict], *, entity_id: str = "game-1", target: datetime = KICKOFF) -> PointInTimeResult:
    return resolve_point_in_time(
        rows,
        table="test_snapshots",
        entity_id_field="game_id",
        entity_id=entity_id,
        timestamp_field="captured_at",
        target_event_timestamp=target,
        now=NOW,
    )


# ---------------------------------------------------------------------------
# Test A -- exact prior observation
# ---------------------------------------------------------------------------


def test_exact_prior_observation_resolves_joined():
    row = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(hours=2), payload={"temp": 40})
    result = _resolve([row])

    assert result.completeness == "joined"
    assert result.data == row
    assert result.reason is None
    assert result.provenance.eligible_row_count == 1
    assert result.provenance.candidate_row_count == 1


# ---------------------------------------------------------------------------
# Test B -- multiple observations: the LATEST eligible one wins, never the
# earliest, never a naive first-match.
# ---------------------------------------------------------------------------


def test_multiple_observations_selects_the_latest_eligible_one():
    earliest = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(days=3), payload={"temp": 10})
    middle = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(days=1), payload={"temp": 20})
    latest_eligible = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(hours=1), payload={"temp": 30})
    # Deliberately out of chronological order in the input list -- proves
    # selection is by captured_at, never by input/arrival order.
    result = _resolve([middle, latest_eligible, earliest])

    assert result.completeness == "joined"
    assert result.data == latest_eligible
    assert result.provenance.candidate_row_count == 3
    assert result.provenance.eligible_row_count == 3
    assert result.provenance.observed_at == (KICKOFF - timedelta(hours=1)).isoformat()


# ---------------------------------------------------------------------------
# Test C -- no observation before event: honest UNAVAILABLE, never a
# fabricated result, never an exception.
# ---------------------------------------------------------------------------


def test_no_observation_before_event_is_honestly_unavailable():
    result = _resolve([])

    assert result.completeness == "unavailable"
    assert result.data is None
    assert result.reason is not None
    assert "game-1" in result.reason
    assert result.provenance.candidate_row_count == 0
    assert result.provenance.eligible_row_count == 0
    assert result.provenance.observed_at is None


def test_only_a_different_entitys_rows_exist_is_also_unavailable():
    """A row exists, but for a different game_id entirely -- must not be
    mistaken for this entity's own history."""
    other_entity_row = _row("game_id", "game-99", captured_at=KICKOFF - timedelta(hours=1))
    result = _resolve([other_entity_row], entity_id="game-1")

    assert result.completeness == "unavailable"
    assert result.data is None
    assert result.provenance.candidate_row_count == 0


# ---------------------------------------------------------------------------
# Test D -- future observation must not leak backward.
# ---------------------------------------------------------------------------


def test_only_a_future_observation_exists_never_leaks_backward():
    """The one and only row postdates the target event -- the audited
    rule must exclude it entirely, never fall back to "the only row we
    have." This is the direct, unambiguous proof no silent fallback to a
    later/current row exists anywhere in this function."""
    future_row = _row("game_id", "game-1", captured_at=KICKOFF + timedelta(days=1), payload={"temp": 999})
    result = _resolve([future_row])

    assert result.completeness == "unavailable"
    assert result.data is None
    assert result.data != future_row
    assert result.provenance.candidate_row_count == 1
    assert result.provenance.eligible_row_count == 0


def test_future_observation_alongside_a_real_eligible_one_is_disclosed_as_partial():
    """A real eligible observation exists AND a later one also exists.
    The resolved data must be the eligible one (the future row's payload
    must never appear) -- but this is disclosed as `partial`, not
    silently indistinguishable from the clean `joined` case, since a
    reader may want to know a newer (correctly unused) observation
    exists."""
    eligible = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(hours=1), payload={"temp": 35})
    future_row = _row("game_id", "game-1", captured_at=KICKOFF + timedelta(hours=1), payload={"temp": 999})
    result = _resolve([eligible, future_row])

    assert result.completeness == "partial"
    assert result.data == eligible
    assert result.data != future_row
    assert result.provenance.candidate_row_count == 2
    assert result.provenance.eligible_row_count == 1


def test_multiple_eligible_rows_with_no_future_row_stays_joined():
    """Contrast case for the partial test above: several eligible rows,
    but nothing postdating the target -- must resolve `joined`, not
    `partial`. Proves `partial` is driven specifically by the presence
    of an excluded future row, not merely by there being more than one
    row."""
    earlier = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(days=1))
    later_but_still_eligible = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(minutes=5))
    result = _resolve([earlier, later_but_still_eligible])

    assert result.completeness == "joined"
    assert result.data == later_but_still_eligible


# ---------------------------------------------------------------------------
# Test E -- timestamp/provenance preservation: event time, observation
# time, and retrieval time never conflated.
# ---------------------------------------------------------------------------


def test_event_observation_and_retrieval_timestamps_are_all_preserved_distinctly():
    observed_at = KICKOFF - timedelta(hours=3)
    row = _row("game_id", "game-1", captured_at=observed_at, payload={"temp": 22})
    result = _resolve([row])

    provenance = result.provenance
    assert provenance.target_event_timestamp == KICKOFF.isoformat()
    assert provenance.observed_at == observed_at.isoformat()
    assert provenance.retrieved_at == NOW.isoformat()
    # All three are genuinely distinct values in this scenario -- proves
    # they are three separate fields, not one timestamp reused three ways.
    assert len({provenance.target_event_timestamp, provenance.observed_at, provenance.retrieved_at}) == 3
    assert provenance.table == "test_snapshots"
    assert provenance.entity_id_field == "game_id"
    assert provenance.entity_id == "game-1"


def test_provenance_preserved_on_the_unavailable_path_too():
    result = _resolve([])
    provenance = result.provenance

    assert provenance.target_event_timestamp == KICKOFF.isoformat()
    assert provenance.retrieved_at == NOW.isoformat()
    assert provenance.observed_at is None
    assert provenance.table == "test_snapshots"


def test_accepts_an_iso_string_target_timestamp_not_only_a_datetime():
    row = _row("game_id", "game-1", captured_at=KICKOFF - timedelta(hours=1))
    result = resolve_point_in_time(
        [row],
        table="test_snapshots",
        entity_id_field="game_id",
        entity_id="game-1",
        timestamp_field="captured_at",
        target_event_timestamp=KICKOFF.isoformat(),
        now=NOW,
    )
    assert result.completeness == "joined"
    assert result.provenance.target_event_timestamp == KICKOFF.isoformat()


# ---------------------------------------------------------------------------
# Dimension-specific wrappers -- prove each wires the correct table/entity
# field, not just that the generic core function works.
# ---------------------------------------------------------------------------


def test_resolve_weather_point_in_time_uses_game_id_and_weather_snapshots():
    row = {"game_id": "game-1", "captured_at": (KICKOFF - timedelta(hours=1)).isoformat(), "weather_data": {"temp_f": 40}}
    result = resolve_weather_point_in_time([row], game_id="game-1", target_event_timestamp=KICKOFF, now=NOW)

    assert result.completeness == "joined"
    assert result.data == row
    assert result.provenance.table == "weather_snapshots"
    assert result.provenance.entity_id_field == "game_id"


def test_resolve_injury_point_in_time_uses_game_id_and_injury_reports():
    row = {"game_id": "game-1", "captured_at": (KICKOFF - timedelta(hours=1)).isoformat(), "report_data": {"status": "questionable"}}
    result = resolve_injury_point_in_time([row], game_id="game-1", target_event_timestamp=KICKOFF, now=NOW)

    assert result.completeness == "joined"
    assert result.data == row
    assert result.provenance.table == "injury_reports"
    assert result.provenance.entity_id_field == "game_id"


def test_resolve_lineup_point_in_time_uses_team_id_not_game_id_and_depth_chart_snapshots():
    """Depth chart snapshots are team-scoped (Phase 8.2 redesign), unlike
    weather/injuries -- this wrapper must key on `team_id`, never
    `game_id`."""
    row = {"team_id": "team-1", "captured_at": (KICKOFF - timedelta(hours=1)).isoformat(), "depth_chart_data": {}}
    unrelated_game_scoped_row = {"game_id": "game-1", "captured_at": (KICKOFF - timedelta(hours=1)).isoformat()}
    result = resolve_lineup_point_in_time(
        [row, unrelated_game_scoped_row], team_id="team-1", target_event_timestamp=KICKOFF, now=NOW
    )

    assert result.completeness == "joined"
    assert result.data == row
    assert result.provenance.table == "depth_chart_snapshots"
    assert result.provenance.entity_id_field == "team_id"
    assert result.provenance.entity_id == "team-1"
    # The unrelated game-scoped row must never have been treated as a
    # candidate for this team_id lookup at all.
    assert result.provenance.candidate_row_count == 1
