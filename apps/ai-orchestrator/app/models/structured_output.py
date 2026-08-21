"""Shared structured-output parsing/validation (Milestone 4.3, requirement
6) -- one implementation every adapter (fake and real alike) calls, so
"malformed output fails validation explicitly, never guessed or filled
in" is enforced identically everywhere rather than reimplemented three
times with a chance of drifting.

Deliberately generic over any Pydantic model, not hardcoded to
`AgentOutput`/`MetaAgentOutput` (Milestone 4.2) -- this module has no
import of either, keeping the model layer provider- *and* contract-
neutral. A caller building a `ModelRequest` for a real fan-out agent
(Milestone 4.4+) will pass `response_model=AgentOutput`; this function
doesn't need to know that to do its job correctly.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from app.models.errors import ModelMalformedOutputError


def parse_structured_output(raw_text: str, response_model: type[BaseModel]) -> BaseModel:
    """Parses `raw_text` as JSON, then validates it against
    `response_model`. Raises `ModelMalformedOutputError` -- never returns
    a partially-filled or guessed instance -- if the text isn't valid
    JSON at all, or is valid JSON that fails the model's own validation
    (missing required field, wrong enum value, out-of-bounds number,
    etc. -- whatever `response_model` itself enforces, e.g. `AgentOutput`
    Milestone 4.2's `extra="forbid"` and field constraints)."""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelMalformedOutputError(f"model output was not valid JSON: {exc}") from exc
    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        raise ModelMalformedOutputError(
            f"model output failed {response_model.__name__} validation: {exc}"
        ) from exc
