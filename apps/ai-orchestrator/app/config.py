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
