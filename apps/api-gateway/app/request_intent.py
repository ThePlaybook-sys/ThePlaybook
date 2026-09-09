"""Phase 8.5 Pass 1 (HQ-authorized): the canonical, deterministic
request-to-answer pipeline for `POST /v1/recommendations/ask` --
RAW INPUT -> NORMALIZED REQUEST -> RESOLVED INTENT -> EXECUTION PLAN.

Every function here is pure (no I/O, no database, no HTTP, no LLM call)
and independently unit-testable, per the Phase 8.5 audit's own explicit
instruction not to collapse these stages into one opaque function. The
route handler (`app.recommendations`) owns the one I/O-touching stage
(retrieval) and calls these in sequence.

**Deterministic only, by design.** Per this project's established
"never delegate to an LLM what deterministic code can reliably do"
principle (`app.features.market`/`grading`/`consensus` follow the same
discipline) -- no model call anywhere in this module. An unrecognized
request resolves to AMBIGUOUS or UNSUPPORTED, honestly, rather than
guessed.

**Terminology guardrail (HQ-mandated, Phase 8.5 Part 14):** this
module recognizes "highest confidence" phrasing only -- it must never
treat "safest"/"guaranteed"/"most likely to win" as synonyms for
`highest_confidence`. Those phrases are recognized explicitly, below,
specifically so they resolve to UNSUPPORTED with an honest reason
rather than silently mapping onto the confidence metric.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Phrases that deterministically resolve to the one supported request
#: this pass implements. Matched as case-insensitive substrings against
#: the normalized text -- intentionally narrow, per HQ's "do not
#: pretend to support complex requests that are not implemented".
_HIGHEST_CONFIDENCE_PHRASES: tuple[str, ...] = (
    "highest confidence",
    "highest-confidence",
    "most confident",
    "strongest confidence",
)

#: Phrases HQ explicitly named as NOT equivalent to highest-confidence
#: -- recognized on purpose so a user asking for one of these gets an
#: honest "not yet supported" answer instead of being silently mapped
#: onto a different metric than the one they asked for.
_KNOWN_UNSUPPORTED_PHRASES: tuple[str, ...] = (
    "safest",
    "safe bet",
    "guarantee",
    "guaranteed",
    "most likely to win",
    "best pick",
    "highest value",
    "highest-value",
    "conservative",
    "aggressive",
    "parlay",
    "player prop",
)


class RequestType(str, Enum):
    RECOMMENDATION_LOOKUP = "recommendation_lookup"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class SelectionMode(str, Enum):
    HIGHEST_CONFIDENCE = "highest_confidence"


class ExecutionAction(str, Enum):
    RETRIEVE_HIGHEST_CONFIDENCE_TODAY = "retrieve_highest_confidence_today"
    REJECT_UNSUPPORTED = "reject_unsupported"
    REJECT_AMBIGUOUS = "reject_ambiguous"


@dataclass(frozen=True)
class RawUserInput:
    """Exactly what arrived, preserved verbatim -- the audit-trail
    stage. Never mutated by any later stage."""

    text: str


@dataclass(frozen=True)
class NormalizedRequest:
    """The one shape both natural-language and (future) structured-UI
    input converge to -- Phase 8.5 Part 2/6. Pass 1 only has an NL
    input path; `normalized_text` is what every later stage pattern-
    matches against, `raw_text` is preserved for audit/reconstruction."""

    raw_text: str
    normalized_text: str


@dataclass(frozen=True)
class ResolvedIntent:
    """What the deterministic resolver concluded the user wants --
    distinct from whether MANSA can actually honor it (that's the
    execution plan's job, immediately below)."""

    request_type: RequestType
    selection_mode: SelectionMode | None
    time_scope: str
    unresolved_reason: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    """What the system will actually do about a resolved intent --
    kept separate from intent resolution itself so "what does the user
    want" and "can/should MANSA act on it" never collapse into one
    decision, per the Phase 8.5 audit's explicit four-stage design."""

    action: ExecutionAction
    reason: str | None = None


def normalize_request(raw: RawUserInput) -> NormalizedRequest:
    """Pure normalization: lowercases and strips whitespace only. No
    interpretation happens here -- that's `resolve_intent`'s job."""
    return NormalizedRequest(raw_text=raw.text, normalized_text=raw.text.strip().lower())


def resolve_intent(normalized: NormalizedRequest) -> ResolvedIntent:
    """Deterministic, rule-based classification -- no LLM call, ever,
    per this module's own header. Time scope is always "today" in this
    pass (Phase 8.5's own contract default, and the only time scope
    Pass 1 implements) -- there is deliberately no branch here that
    resolves to any other time scope."""
    text = normalized.normalized_text

    if not text:
        return ResolvedIntent(
            request_type=RequestType.AMBIGUOUS,
            selection_mode=None,
            time_scope="today",
            unresolved_reason="The question was empty after normalization.",
        )

    if any(phrase in text for phrase in _HIGHEST_CONFIDENCE_PHRASES):
        return ResolvedIntent(
            request_type=RequestType.RECOMMENDATION_LOOKUP,
            selection_mode=SelectionMode.HIGHEST_CONFIDENCE,
            time_scope="today",
        )

    matched_unsupported = next((phrase for phrase in _KNOWN_UNSUPPORTED_PHRASES if phrase in text), None)
    if matched_unsupported is not None:
        return ResolvedIntent(
            request_type=RequestType.UNSUPPORTED,
            selection_mode=None,
            time_scope="today",
            unresolved_reason=(
                f"MANSA does not yet support '{matched_unsupported}' requests. "
                "This endpoint currently supports only 'highest-confidence pick' "
                "requests -- MANSA's own model confidence metric, not a claim about "
                "objective safety, value, or win likelihood."
            ),
        )

    return ResolvedIntent(
        request_type=RequestType.AMBIGUOUS,
        selection_mode=None,
        time_scope="today",
        unresolved_reason="MANSA could not determine what kind of recommendation was requested.",
    )


def build_execution_plan(intent: ResolvedIntent) -> ExecutionPlan:
    """Maps a resolved intent onto a concrete action. Kept as its own
    stage (rather than folded into `resolve_intent`) because "what the
    user wants" and "what MANSA will do about it" are genuinely
    different questions -- today they happen to be in lockstep for the
    one supported request type, but collapsing them would make a
    future capability-check layer (Phase 8.5 Part 10) harder to insert
    without restructuring this module."""
    if intent.request_type == RequestType.RECOMMENDATION_LOOKUP and intent.selection_mode == SelectionMode.HIGHEST_CONFIDENCE:
        return ExecutionPlan(action=ExecutionAction.RETRIEVE_HIGHEST_CONFIDENCE_TODAY)
    if intent.request_type == RequestType.UNSUPPORTED:
        return ExecutionPlan(action=ExecutionAction.REJECT_UNSUPPORTED, reason=intent.unresolved_reason)
    return ExecutionPlan(action=ExecutionAction.REJECT_AMBIGUOUS, reason=intent.unresolved_reason)
