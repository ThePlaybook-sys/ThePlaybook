"""Phase 8.5 Pass 1/2/3 (HQ-authorized): the canonical, deterministic
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

**Terminology guardrail (HQ-mandated, Phase 8.5 Part 14, extended
Pass 2/3):** this module recognizes "highest confidence" and "highest
value" phrasing ONLY, as two genuinely distinct selection modes -- it
must never treat "safest"/"guaranteed"/"most likely to win"/"best
pick" as a synonym for either. "highest confidence" ranks by
`final_aggregate_confidence`; "highest value" ranks by `ev_per_dollar`
(verified, Pass 2, to be a genuine expected-value-per-dollar-staked
calculation -- see `docs/ops/phase-8.5-pass2-ev-per-dollar-metric-
verification-2026-09-09.md`) -- these are never interchangeable and
the response layer (`app.recommendations`) must always say which one
was used.

**Market filtering (Pass 3, added 2026-09-09).** `market_type` is a
real, DB-CHECK-enforced, `not null` column on `recommendation_legs`
(`moneyline`/`spread`/`total`/`prop` -- `prop` never actually written,
candidate generation excludes it since Milestone 4.7), normalized at
the earliest possible point (provider ingestion, `apps.sports-intel-
layer.app.adapters.providers.the_odds_api._BULK_MARKET_TYPE`), not
guessed anywhere downstream. Full audit: `docs/ops/phase-8.5-pass3-
market-type-audit-2026-09-09.md`. All three of moneyline/spread/total
have equally clean, unambiguous, schema-enforced canonical values --
the audit found no basis to defer moneyline. A market constraint is
only ever recognized alongside a recognized selection-mode phrase
(never as a standalone request type -- that would expand this pass's
own scope); its absence preserves Pass 1/2 behavior exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Phrases that deterministically resolve to `HIGHEST_CONFIDENCE`.
#: Matched as case-insensitive substrings against the normalized text
#: -- intentionally narrow, per HQ's "do not pretend to support
#: complex requests that are not implemented".
_HIGHEST_CONFIDENCE_PHRASES: tuple[str, ...] = (
    "highest confidence",
    "highest-confidence",
    "most confident",
    "strongest confidence",
)

#: Phrases that deterministically resolve to `HIGHEST_VALUE` (Pass 2).
#: "best value" is HQ's own example phrasing ("show me the best value
#: pick today") -- checked against `_KNOWN_UNSUPPORTED_PHRASES`'s own
#: "best pick" entry below and confirmed non-colliding: "best value
#: pick" never contains "best pick" as a contiguous substring, proven
#: by `test_request_intent.py`'s own collision test.
_HIGHEST_VALUE_PHRASES: tuple[str, ...] = (
    "highest value",
    "highest-value",
    "best value",
)

#: Phrases HQ explicitly named as NOT equivalent to either supported
#: selection mode -- recognized on purpose so a user asking for one of
#: these gets an honest "not yet supported" answer instead of being
#: silently mapped onto a different metric than the one they asked
#: for. "best pick" stays here even after Pass 2, per HQ's explicit
#: instruction: "'Best' remains a broader product decision and should
#: remain unsupported." Checked BEFORE selection-mode matching (Pass 3
#: reordering, see `resolve_intent`) so an unsupported phrase can never
#: be shadowed by a coincidentally-also-present supported phrase.
_KNOWN_UNSUPPORTED_PHRASES: tuple[str, ...] = (
    "safest",
    "safe bet",
    "guarantee",
    "guaranteed",
    "most likely to win",
    "best pick",
    "conservative",
    "aggressive",
    "parlay",
)

#: Market-shaped words that are NOT one of the three supported markets
#: -- recognized explicitly (Pass 3) so a request naming one of these
#: resolves to UNSUPPORTED rather than either silently dropping the
#: constraint (which would answer a different, unasked question) or
#: crashing. "player prop"/"prop"/"props" are excluded from candidate
#: generation entirely (Milestone 4.7) -- there is no real prop
#: recommendation to filter to anyway.
_UNSUPPORTED_MARKET_PHRASES: tuple[str, ...] = (
    "player prop",
    "props",
    "prop",
)

#: Phrase -> canonical `MarketType` value (plain string, converted via
#: `MarketType(...)` in `_match_market_type` below). Checked in this
#: order (longest/most-specific first has no actual effect here since
#: every phrase maps to the market its own substring already implies,
#: but the order is kept deliberate and documented rather than
#: incidental). Every canonical value here is the exact, real,
#: DB-CHECK-enforced `recommendation_legs.market_type` string -- never
#: invented.
_MARKET_TYPE_PHRASES: tuple[tuple[str, str], ...] = (
    ("point spread", "spread"),
    ("spread", "spread"),
    ("money line", "moneyline"),
    ("moneyline", "moneyline"),
    ("over/under", "total"),
    ("over under", "total"),
    ("totals", "total"),
    ("total", "total"),
)


class RequestType(str, Enum):
    RECOMMENDATION_LOOKUP = "recommendation_lookup"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class SelectionMode(str, Enum):
    HIGHEST_CONFIDENCE = "highest_confidence"
    HIGHEST_VALUE = "highest_value"


class MarketType(str, Enum):
    """The exact, real `recommendation_legs.market_type` vocabulary
    that is ever actually written (Pass 3 audit) -- `prop` is a real
    schema-allowed CHECK value but is deliberately excluded here since
    no candidate generation path ever produces one."""

    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"


class ExecutionAction(str, Enum):
    RETRIEVE_HIGHEST_CONFIDENCE_TODAY = "retrieve_highest_confidence_today"
    RETRIEVE_HIGHEST_VALUE_TODAY = "retrieve_highest_value_today"
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
    execution plan's job, immediately below). `market_type` is `None`
    whenever no market constraint was recognized -- preserving Pass
    1/2 behavior exactly for every request that doesn't name one."""

    request_type: RequestType
    selection_mode: SelectionMode | None
    market_type: MarketType | None
    time_scope: str
    unresolved_reason: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    """What the system will actually do about a resolved intent --
    kept separate from intent resolution itself so "what does the user
    want" and "can/should MANSA act on it" never collapse into one
    decision, per the Phase 8.5 audit's explicit four-stage design."""

    action: ExecutionAction
    market_type: MarketType | None = None
    reason: str | None = None


def normalize_request(raw: RawUserInput) -> NormalizedRequest:
    """Pure normalization: lowercases and strips whitespace only. No
    interpretation happens here -- that's `resolve_intent`'s job."""
    return NormalizedRequest(raw_text=raw.text, normalized_text=raw.text.strip().lower())


def _match_selection_mode(text: str) -> SelectionMode | None:
    if any(phrase in text for phrase in _HIGHEST_CONFIDENCE_PHRASES):
        return SelectionMode.HIGHEST_CONFIDENCE
    if any(phrase in text for phrase in _HIGHEST_VALUE_PHRASES):
        return SelectionMode.HIGHEST_VALUE
    return None


def _match_market_type(text: str) -> tuple[MarketType | None, str | None]:
    """Returns `(market_type, unsupported_reason)` -- exactly one is
    non-`None`, or both are `None` when no market word appears at all
    (the "no market constraint" case, which preserves Pass 1/2
    behavior exactly). An unsupported market word (e.g. "prop") is
    checked FIRST so it can never be shadowed by a supported market
    word appearing elsewhere in the same sentence."""
    for phrase in _UNSUPPORTED_MARKET_PHRASES:
        if phrase in text:
            return None, (
                f"MANSA does not yet support '{phrase}' markets through this endpoint. "
                "Supported markets are moneyline, spread, and total."
            )
    for phrase, market_type in _MARKET_TYPE_PHRASES:
        if phrase in text:
            return MarketType(market_type), None
    return None, None


def resolve_intent(normalized: NormalizedRequest) -> ResolvedIntent:
    """Deterministic, rule-based classification -- no LLM call, ever,
    per this module's own header. Time scope is always "today" in this
    pass (Phase 8.5's own contract default) -- there is deliberately
    no branch here that resolves to any other time scope.

    Order (Pass 3 reordering, deliberate): known-unsupported phrases
    are checked FIRST, before selection-mode matching, so an
    unsupported request (e.g. "parlay") can never be shadowed by a
    coincidentally-also-present supported phrase. This reordering was
    verified (by test) to change zero existing Pass 1/2 outcomes --
    no supported phrase collides with any unsupported phrase."""
    text = normalized.normalized_text

    if not text:
        return ResolvedIntent(
            request_type=RequestType.AMBIGUOUS,
            selection_mode=None,
            market_type=None,
            time_scope="today",
            unresolved_reason="The question was empty after normalization.",
        )

    matched_unsupported = next((phrase for phrase in _KNOWN_UNSUPPORTED_PHRASES if phrase in text), None)
    if matched_unsupported is not None:
        return ResolvedIntent(
            request_type=RequestType.UNSUPPORTED,
            selection_mode=None,
            market_type=None,
            time_scope="today",
            unresolved_reason=(
                f"MANSA does not yet support '{matched_unsupported}' requests. "
                "This endpoint currently supports only 'highest-confidence pick' and "
                "'highest-value pick' requests -- MANSA's own model confidence and "
                "expected-value metrics, not claims about objective safety, guarantees, "
                "or win likelihood -- optionally scoped to a moneyline, spread, or total "
                "market."
            ),
        )

    selection_mode = _match_selection_mode(text)
    if selection_mode is None:
        return ResolvedIntent(
            request_type=RequestType.AMBIGUOUS,
            selection_mode=None,
            market_type=None,
            time_scope="today",
            unresolved_reason="MANSA could not determine what kind of recommendation was requested.",
        )

    market_type, market_unsupported_reason = _match_market_type(text)
    if market_unsupported_reason is not None:
        return ResolvedIntent(
            request_type=RequestType.UNSUPPORTED,
            selection_mode=None,
            market_type=None,
            time_scope="today",
            unresolved_reason=market_unsupported_reason,
        )

    return ResolvedIntent(
        request_type=RequestType.RECOMMENDATION_LOOKUP,
        selection_mode=selection_mode,
        market_type=market_type,
        time_scope="today",
    )


def build_execution_plan(intent: ResolvedIntent) -> ExecutionPlan:
    """Maps a resolved intent onto a concrete action. Kept as its own
    stage (rather than folded into `resolve_intent`) because "what the
    user wants" and "what MANSA will do about it" are genuinely
    different questions -- collapsing them would make a future
    capability-check layer (Phase 8.5 Part 10) harder to insert
    without restructuring this module. `market_type` is carried
    through unchanged onto the plan -- filtering happens at retrieval
    time (`app.recommendations`), never here (this module has no I/O)."""
    if intent.request_type == RequestType.RECOMMENDATION_LOOKUP and intent.selection_mode == SelectionMode.HIGHEST_CONFIDENCE:
        return ExecutionPlan(action=ExecutionAction.RETRIEVE_HIGHEST_CONFIDENCE_TODAY, market_type=intent.market_type)
    if intent.request_type == RequestType.RECOMMENDATION_LOOKUP and intent.selection_mode == SelectionMode.HIGHEST_VALUE:
        return ExecutionPlan(action=ExecutionAction.RETRIEVE_HIGHEST_VALUE_TODAY, market_type=intent.market_type)
    if intent.request_type == RequestType.UNSUPPORTED:
        return ExecutionPlan(action=ExecutionAction.REJECT_UNSUPPORTED, reason=intent.unresolved_reason)
    return ExecutionPlan(action=ExecutionAction.REJECT_AMBIGUOUS, reason=intent.unresolved_reason)
