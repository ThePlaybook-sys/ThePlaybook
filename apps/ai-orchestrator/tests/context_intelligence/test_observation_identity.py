"""Tests for app.context_intelligence.observation_identity (Player
Performance Context Foundation pass, 2026-09-15) -- pure function, no
I/O."""
from __future__ import annotations

import pytest

from app.context_intelligence.observation_identity import resolve_canonical_observation


def test_single_row_is_its_own_canonical_with_no_duplicates():
    row = {"id": "r1", "created_at": "2026-09-10T20:38:42+00:00", "stats": {"a": 1}}
    result = resolve_canonical_observation([row])
    assert result.canonical == row
    assert result.duplicate_row_count == 1
    assert result.all_row_ids == ("r1",)


def test_most_recent_created_at_wins():
    older = {"id": "r1", "created_at": "2026-09-10T20:38:42+00:00", "stats": {"a": 1}}
    newer = {"id": "r2", "created_at": "2026-09-14T23:02:03+00:00", "stats": {"a": 2}}
    result = resolve_canonical_observation([older, newer])
    assert result.canonical == newer
    assert result.duplicate_row_count == 2


def test_order_of_input_does_not_affect_result():
    older = {"id": "r1", "created_at": "2026-09-10T20:38:42+00:00"}
    newer = {"id": "r2", "created_at": "2026-09-14T23:02:03+00:00"}
    result_forward = resolve_canonical_observation([older, newer])
    result_reversed = resolve_canonical_observation([newer, older])
    assert result_forward.canonical == result_reversed.canonical == newer


def test_all_row_ids_preserves_every_raw_row_including_non_canonical():
    older = {"id": "r1", "created_at": "2026-09-10T20:38:42+00:00"}
    newer = {"id": "r2", "created_at": "2026-09-14T23:02:03+00:00"}
    result = resolve_canonical_observation([older, newer])
    assert set(result.all_row_ids) == {"r1", "r2"}


def test_empty_input_raises_value_error():
    with pytest.raises(ValueError):
        resolve_canonical_observation([])


def test_custom_tie_break_field_is_respected():
    a = {"id": "a", "ingested_at": 1}
    b = {"id": "b", "ingested_at": 2}
    result = resolve_canonical_observation([a, b], tie_break_field="ingested_at")
    assert result.canonical == b
