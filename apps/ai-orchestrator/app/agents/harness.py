"""The validation harness (Milestone 4.2) -- the one entry point any
future agent's raw output must pass through before being wired into the
real pipeline (Milestone 4.4+ builds the agents; this module only ever
validates, never produces, an output).

Wraps `pydantic.ValidationError` in a single project-specific exception,
`AgentContractError`, matching every other module in this codebase's own
convention of one clearly-named exception type per persistence/validation
boundary (`DailyGameIntelligenceReadError`, `GamesReadError`,
`ConfigReadError`) -- a caller only ever needs to catch one exception type
from this package, never `pydantic.ValidationError` directly. The
original Pydantic error is preserved as `__cause__` (via `raise ... from
exc`) so nothing about *why* validation failed is lost, only wrapped.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agents.contract import AgentOutput, MetaAgentOutput


class AgentContractError(Exception):
    """Raised when a raw agent output fails to validate against
    `AgentOutput`/`MetaAgentOutput` -- missing required field, wrong
    type, a value outside the allowed enum/bounds, or an unrecognized
    extra field (the contract is `extra="forbid"`: an agent inventing its
    own field is rejected exactly like a missing required one, never
    silently ignored)."""


def validate_agent_output(raw: dict[str, Any]) -> AgentOutput:
    """Validates one fan-out agent's raw output against the shared
    contract (Volume 4 Section 2.1). Raises `AgentContractError` with a
    clear, field-by-field message on any violation; returns the
    validated, typed `AgentOutput` on success."""
    try:
        return AgentOutput.model_validate(raw)
    except ValidationError as exc:
        raise AgentContractError(f"agent output failed contract validation: {exc}") from exc


def validate_meta_agent_output(raw: dict[str, Any]) -> MetaAgentOutput:
    """Validates the Meta Agent's raw output against its own distinct
    contract (Volume 4 Section 2.6), including the hard
    `confidence_adjustment <= 0` rule. Raises `AgentContractError` on any
    violation; returns the validated, typed `MetaAgentOutput` on success."""
    try:
        return MetaAgentOutput.model_validate(raw)
    except ValidationError as exc:
        raise AgentContractError(f"meta agent output failed contract validation: {exc}") from exc
