"""Deterministic risk math (Milestone 4.6, Decision E). Application code,
never the LLM.

**Naming discipline, exactly as approved:** Volume 4 Section 2.5 names
the Risk Manager's primary input as "historical variance by bet type" --
confirmed by direct schema grep to not exist anywhere (no table stores
per-bet-type historical outcome variance; `consensus_snapshots.
agreement_variance` is a completely different concept -- agent
*disagreement*, not bet-outcome variance). That input is genuinely
BLOCKED, not merely stale.

`bernoulli_outcome_variance` (`p * (1-p)`) is a real, computable
statistical fact derived purely from this one candidate's own modeled
probability -- it is NOT a substitute for the missing historical signal
and must never be presented as one. `historical_bet_type_variance` is
always `None`, explicitly reported as unavailable rather than silently
omitted, until real historical recommendation/outcome data exists.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAssessment:
    bernoulli_outcome_variance: float | None
    historical_bet_type_variance: None  # permanently None until real data exists -- see module docstring


def compute_outcome_variance(p_model: float | None) -> float | None:
    """`p_model is None` (no modeled probability available) degrades to
    `None` -- never a fabricated variance."""
    if p_model is None:
        return None
    if not 0.0 <= p_model <= 1.0:
        raise ValueError(f"p_model must be within [0.0, 1.0], got {p_model!r}")
    return p_model * (1 - p_model)


def build_risk_assessment(p_model: float | None) -> RiskAssessment:
    return RiskAssessment(
        bernoulli_outcome_variance=compute_outcome_variance(p_model),
        historical_bet_type_variance=None,
    )
