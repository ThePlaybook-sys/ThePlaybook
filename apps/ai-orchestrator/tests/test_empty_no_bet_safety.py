"""HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20).

MANSA's product semantics, as decided by HQ:

- **No Bet** = the analytical/model pipeline completed enough to evaluate at
  least one usable candidate, and nothing qualified.
- **Analysis failure / incomplete** = the pipeline did not produce enough
  usable evidence to make a qualification decision.

An analysis failure is **not** a No Bet. These tests hold that line at the two
places the live defect actually crossed it: the candidate status, and the
completion marker.

The defect these cover consumed two real fixtures (CLE @ TB 2026-09-19,
CIN @ HOU 2026-09-20): every candidate came back with no usable output, the
empty candidate list reached the Strategy Engine, and `if not qualifying`
produced an ACTIVE No Bet with `cycle_completed_at` stamped — permanently
blocking recomputation on a game that had produced no intelligence at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.recommendation_worker import ANALYSIS_INCOMPLETE, _analysis_incomplete


@dataclass
class _Chain:
    """Stand-in for `SharedCandidateChainResult` — only the two fields
    `_analysis_incomplete` reads."""
    status: str
    ev: object | None


class _EV:
    def __init__(self, ev_per_dollar):
        self.ev_per_dollar = ev_per_dollar


_STRATEGY_INPUT = object()  # opaque: the helper only checks "is not None"


# ---------------------------------------------------------------- incomplete
def test_no_strategy_input_and_no_ev_is_incomplete():
    """The live failure shape: the probability -> EV -> risk chain produced
    nothing, so there is no EV at all and nothing to qualify."""
    assert _analysis_incomplete(_Chain(status="failed", ev=None), None) is True


def test_failed_chain_is_incomplete_even_with_partial_label():
    """A chain can report `partial` and still have produced no EV — degraded
    is not the same as usable."""
    assert _analysis_incomplete(_Chain(status="partial", ev=None), None) is True


# ------------------------------------------------------------------ complete
def test_usable_strategy_input_is_never_incomplete():
    """STATE 2: analysis completed and produced something the Strategy
    Engine can act on."""
    assert _analysis_incomplete(_Chain(status="full", ev=_EV(0.04)), _STRATEGY_INPUT) is False


def test_partial_chain_with_surviving_strategy_input_is_not_incomplete():
    """HQ STATE 4: some degradation, but a valid decision survives. The
    degradation stays visible through `shared_chain_status` — it does not
    fail the candidate."""
    assert _analysis_incomplete(_Chain(status="partial", ev=_EV(0.02)), _STRATEGY_INPUT) is False


def test_ev_present_but_no_ev_per_dollar_is_not_incomplete():
    """The documented legitimate case: a candidate with no `american_odds`
    has no computable EV per dollar. The analysis RAN and found nothing
    EV-computable, which is real information, not a failure.

    This is the test that keeps the fix narrow: without it, the obvious
    implementation ("no strategy_input means failure") would start reporting
    perfectly healthy candidates as analysis failures and block their games
    from ever completing.
    """
    assert _analysis_incomplete(_Chain(status="full", ev=_EV(None)), None) is False


# ------------------------------------------------------------------ contract
def test_incomplete_status_is_distinct_from_failed():
    """`failed` already means "this candidate raised an exception". An
    incomplete analysis raised nothing — every step returned, they just
    returned nothing usable. Collapsing the two would lose exactly the
    distinction that let the defect hide."""
    assert ANALYSIS_INCOMPLETE == "analysis_incomplete"
    assert ANALYSIS_INCOMPLETE != "failed"
    assert ANALYSIS_INCOMPLETE != "evaluated"
