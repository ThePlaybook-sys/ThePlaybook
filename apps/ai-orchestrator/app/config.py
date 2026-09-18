"""Environment-variable (Railway) configuration reads (Milestone 4.9).
Kept separate from `app.persistence` -- these are process-level
variables, never database rows."""
from __future__ import annotations

import os


class ConfigError(Exception):
    """Raised when a required environment variable is missing or
    malformed -- never silently defaulted."""


def reference_sportsbook_preference() -> list[str]:
    """`REFERENCE_SPORTSBOOK_PREFERENCE` -- a comma-separated, ordered
    list of sportsbook names (e.g. `"draftkings,fanduel"`), exactly the
    `reference_sportsbook_preference` list `app.features.
    candidate_generation.generate_candidates_for_game` expects
    (Milestone 4.9, Decision 1). Raises `ConfigError` rather than
    silently defaulting to an arbitrary book when unset or empty -- an
    unconfigured reference sportsbook must block candidate generation
    loudly, never guess a book."""
    raw = os.environ.get("REFERENCE_SPORTSBOOK_PREFERENCE", "")
    books = [b.strip() for b in raw.split(",") if b.strip()]
    if not books:
        raise ConfigError(
            "REFERENCE_SPORTSBOOK_PREFERENCE is not set or empty -- cannot generate candidates "
            "without a configured reference sportsbook preference"
        )
    return books


#: Hard ceiling on outbound model requests for ONE game's recommendation.
#: Enforced at the adapter boundary by `app.models.budget`, not by
#: arithmetic over an assumed fan-out shape.
#:
#: **DERIVED from the committee's own maximum shape**, and deliberately
#: set AT that maximum rather than above it, so the ceiling is a true
#: statement of what the design can legitimately need: 6 game-level agents
#: + 6 candidates (3 V1 markets x 2 sides) x (3 shared-chain + 1 Meta +
#: 1 Elite second pass) + Bankroll Coach per active subscriber per
#: candidate. At dev's 2 active subscribers that is 6 + 6x5 + 12 = 48.
#:
#: The subscriber term is the one that genuinely grows with the business,
#: which is exactly why this is an env var: raising it is a deliberate,
#: reviewable act rather than something that happens silently as users
#: sign up. **Flagged for HQ** -- when real subscriber counts grow, this
#: number must be raised consciously, and a breach is the signal to do so.
DEFAULT_MAX_LLM_CALLS_PER_GAME = 48


def max_llm_calls_per_game() -> int:
    """`MAX_LLM_CALLS_PER_GAME` when set to a positive integer, otherwise
    `DEFAULT_MAX_LLM_CALLS_PER_GAME`. A malformed or non-positive value
    falls back to the default rather than raising: this is a safety
    ceiling, and a typo in it must never itself become the outage."""
    raw = os.environ.get("MAX_LLM_CALLS_PER_GAME", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_LLM_CALLS_PER_GAME
    return value if value > 0 else DEFAULT_MAX_LLM_CALLS_PER_GAME
