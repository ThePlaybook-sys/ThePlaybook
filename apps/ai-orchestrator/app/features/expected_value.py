"""Deterministic EV/edge math (Milestone 4.6, Decision C) -- application
code, never the LLM, per Blueprint v5.0 Section 1.1. Consumes a
candidate's actual offered American odds (never a synthetic/de-vigged
price) and Probability Modeling's `modeled_probability` for that exact
candidate.

**Terminology, exactly as approved:** `raw_probability_edge` is
VIG-INCLUSIVE (compared against the book's own single-sided implied
probability, not a de-vigged fair-market probability) -- never presented
as a true market edge. `ev_per_dollar` is computed against the actual
offered price, which is correct because it's pricing the actual
wager, not a hypothetical fair one.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.features.probability import american_to_decimal, implied_probability


@dataclass(frozen=True)
class EVResult:
    decimal_odds: float | None
    raw_implied_probability: float | None
    raw_probability_edge: float | None
    ev_per_dollar: float | None


def compute_ev(p_model: float, american_odds: int | None) -> EVResult:
    """`american_odds is None` (missing price) degrades every field to
    `None` -- never a fabricated EV against a guessed price. A
    structurally invalid odds value (e.g. `0`) still raises
    `InvalidOddsError` (via `american_to_decimal`/`implied_probability`)
    -- that's malformed data, not merely missing, and this codebase never
    silently absorbs malformed input."""
    if not 0.0 <= p_model <= 1.0:
        raise ValueError(f"p_model must be within [0.0, 1.0], got {p_model!r}")
    if american_odds is None:
        return EVResult(decimal_odds=None, raw_implied_probability=None, raw_probability_edge=None, ev_per_dollar=None)

    decimal_odds = american_to_decimal(american_odds)
    raw_implied_probability = implied_probability(american_odds)
    raw_probability_edge = p_model - raw_implied_probability
    ev_per_dollar = p_model * decimal_odds - 1
    return EVResult(
        decimal_odds=decimal_odds,
        raw_implied_probability=raw_implied_probability,
        raw_probability_edge=raw_probability_edge,
        ev_per_dollar=ev_per_dollar,
    )
