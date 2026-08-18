"""Tests for app.workers.reconciliation (Phase 3E-8, Decision 5).

Pure-function tests for the approved bounded reconciliation schedule --
+10m/+30m/+2h/+24h/+72h -- and the "no checks after +72h" completion rule.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.workers.reconciliation import CHECKPOINT_OFFSETS, due_checkpoints, is_reconciliation_complete

FINALIZED_AT = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def test_checkpoint_offsets_match_approved_schedule():
    labels = [label for label, _ in CHECKPOINT_OFFSETS]
    assert labels == ["initial", "+10m", "+30m", "+2h", "+24h", "+72h"]


def test_initial_checkpoint_due_immediately():
    due = due_checkpoints(now=FINALIZED_AT, finalized_at=FINALIZED_AT, checks_done=frozenset())
    assert due == ["initial"]


def test_plus_10m_not_due_before_10_minutes():
    now = FINALIZED_AT + timedelta(minutes=9)
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial"}))
    assert due == []


def test_plus_10m_due_at_exactly_10_minutes():
    now = FINALIZED_AT + timedelta(minutes=10)
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial"}))
    assert due == ["+10m"]


def test_plus_30m_due():
    now = FINALIZED_AT + timedelta(minutes=30)
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial", "+10m"}))
    assert due == ["+30m"]


def test_plus_2h_due():
    now = FINALIZED_AT + timedelta(hours=2)
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial", "+10m", "+30m"}))
    assert due == ["+2h"]


def test_plus_24h_due():
    now = FINALIZED_AT + timedelta(hours=24)
    due = due_checkpoints(
        now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial", "+10m", "+30m", "+2h"})
    )
    assert due == ["+24h"]


def test_plus_72h_due_and_is_final_checkpoint():
    now = FINALIZED_AT + timedelta(hours=72)
    checks_done = frozenset({"initial", "+10m", "+30m", "+2h", "+24h"})
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=checks_done)
    assert due == ["+72h"]
    assert not is_reconciliation_complete(checks_done)
    assert is_reconciliation_complete(checks_done | {"+72h"})


def test_no_checks_due_after_reconciliation_closes():
    now = FINALIZED_AT + timedelta(hours=200)  # well past +72h
    all_done = frozenset(label for label, _ in CHECKPOINT_OFFSETS)
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=all_done)
    assert due == []
    assert is_reconciliation_complete(all_done)


def test_multiple_checkpoints_due_at_once_if_worker_missed_a_cycle():
    """If the worker hasn't run in a while, several checkpoints can become
    due simultaneously -- all returned in schedule order, not just the
    next one."""
    now = FINALIZED_AT + timedelta(hours=3)  # past +10m/+30m/+2h all at once
    due = due_checkpoints(now=now, finalized_at=FINALIZED_AT, checks_done=frozenset({"initial"}))
    assert due == ["+10m", "+30m", "+2h"]


def test_naive_now_raises():
    with pytest.raises(ValueError):
        due_checkpoints(now=datetime(2026, 9, 14, 20, 10), finalized_at=FINALIZED_AT, checks_done=frozenset())


def test_naive_finalized_at_raises():
    with pytest.raises(ValueError):
        due_checkpoints(now=FINALIZED_AT, finalized_at=datetime(2026, 9, 14, 20, 0), checks_done=frozenset())
