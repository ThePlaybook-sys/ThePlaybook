"""Deterministic Kelly-stake math (Milestone 4.6, Decision D) --
application code, never the LLM. Standard closed-form Kelly, quarter-Kelly
per Volume 4 Section 2.5.

**`RISK_TOLERANCE_MULTIPLIERS` are product-policy configuration, not
Kelly mathematics** -- Mac's explicit instruction (2026-08-22): no risk
profile may exceed quarter-Kelly in V1. `conservative`=1/8 Kelly,
`moderate`=3/16 Kelly, `aggressive`=full quarter-Kelly. These are initial
defaults, tunable later via the same evidence-gated process Volume 4
Section 6 already requires for agent weights -- never treated as
mathematically authoritative.

`preferred_unit_size` is deliberately unused here -- Volume 4 Section
2.5's own stake formula never actually references it despite naming
"unit size" as an input, and no exact role for it has been decided.
Inventing one would be exactly the kind of unauthorized decision this
project's discipline exists to avoid.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Policy configuration, not math -- see module docstring. Values are
#: fractions of quarter-Kelly (e.g. 0.50 => half of quarter-Kelly = 1/8
#: Kelly), never exceeding 1.00 (full quarter-Kelly) in V1.
RISK_TOLERANCE_MULTIPLIERS: dict[str, float] = {
    "conservative": 0.50,
    "moderate": 0.75,
    "aggressive": 1.00,
}


class InvalidKellyInputError(ValueError):
    """Raised for a structurally invalid probability or net-odds value --
    never silently clamped."""


@dataclass(frozen=True)
class KellyResult:
    full_kelly_fraction: float | None
    quarter_kelly_fraction: float | None
    risk_tolerance_multiplier: float | None
    stake: float | None


def compute_full_kelly(p_model: float, decimal_odds: float) -> float:
    """Standard closed-form Kelly fraction: `(b*p - q) / b`, where
    `b = decimal_odds - 1` (net odds) and `q = 1 - p`. Algebraically
    `b*p - q == p*decimal_odds - 1 == ev_per_dollar` -- full-Kelly
    fraction is exactly EV-per-dollar divided by `b`, asserted directly
    in tests as a cross-check against `app.features.expected_value`."""
    if not 0.0 <= p_model <= 1.0:
        raise InvalidKellyInputError(f"p_model must be within [0.0, 1.0], got {p_model!r}")
    b = decimal_odds - 1
    if b <= 0:
        raise InvalidKellyInputError(f"decimal_odds must imply positive net odds, got {decimal_odds!r}")
    q = 1 - p_model
    return (b * p_model - q) / b


def compute_stake(
    p_model: float,
    decimal_odds: float | None,
    *,
    bankroll: float | None,
    risk_tolerance: str | None,
) -> KellyResult:
    """`decimal_odds is None` (no priced candidate) degrades every field
    to `None`. Otherwise the Kelly fractions are always computed (even
    with no bankroll/risk_tolerance) -- only the final dollar `stake`
    depends on those two, per the null-not-neutral discipline applied
    per-field, not all-or-nothing. A negative-or-zero full-Kelly fraction
    floors `quarter_kelly_fraction` at `0.0`, never a negative stake."""
    if decimal_odds is None:
        return KellyResult(full_kelly_fraction=None, quarter_kelly_fraction=None, risk_tolerance_multiplier=None, stake=None)

    full_kelly = compute_full_kelly(p_model, decimal_odds)
    quarter_kelly = max(full_kelly, 0.0) * 0.25
    multiplier = RISK_TOLERANCE_MULTIPLIERS.get(risk_tolerance) if risk_tolerance else None

    stake = None
    if bankroll is not None and bankroll > 0 and multiplier is not None:
        raw_stake = bankroll * quarter_kelly * multiplier
        stake = round(min(max(raw_stake, 0.0), bankroll), 2)

    return KellyResult(
        full_kelly_fraction=full_kelly,
        quarter_kelly_fraction=quarter_kelly,
        risk_tolerance_multiplier=multiplier,
        stake=stake,
    )
