"""Phase 8, MANSA directive "PHASE 8 CONTEXT PROBABILITY CONTROL + COMPARISON"
(2026-09-15), Part B: a deterministic CONTROL-vs-CONTEXT comparison harness for
`ProbabilityModelingAgent`. Runs the SAME `SequentialDecisionContext` through
`build_evidence()` + one model call twice -- once with `context_package` stripped
(CONTROL) and once as given (CONTEXT) -- holding the candidate, upstream findings,
and participation metadata identical between the two runs. Never touches
persistence (unlike `app.orchestration.cycle.run_candidate_evaluation`); this module
only observes, it does not write a `recommendations`/`recommendation_agent_outputs`
row for either run, and it never changes which candidate would be recommended.

**Boundary, exactly as authorized:** no deterministic context weight is computed
or applied anywhere in this module; no aggregate movement cap; no EV/Kelly/Risk
recomputation; no provider call is made BY this module itself (the caller supplies
an already-constructed `AdapterRegistry` -- every real usage of this module during
this pass uses `FakeModelAdapter` with a clearly-labeled synthetic or scripted-real
script, per the directive's "no provider calls" constraint, so this pass observes
harness MECHANISM, never genuine live-model behavioral tendencies).

**Safety flags are heuristic pattern-matching over the model's own `reasoning`/
`supporting_evidence` text, never a semantic understanding of what the model
"really meant."** Each flag is disclosed as exactly the substring/keyword check it
is; a flag firing is a prompt for human review, never an automatic correction --
this module never rewrites `modeled_probability` or any other field.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import httpx

from app.agents.committee_context import SequentialDecisionContext
from app.agents.probability_modeling import ADMITTED_CONTEXT_DIMENSIONS, ProbabilityModelingAgent
from app.features.probability import InvalidOddsError, implied_probability
from app.models.retry_policy import RetryEngine
from app.models.router import AdapterRegistry
from app.orchestration.sequential import SequentialAgentRunResult, run_sequential_agent

#: Audited double-counting risk ("PHASE 8 CONTEXTUAL PROBABILITY DESIGN + PLAYER
#: IDENTITY", 2026-09-15, Part C): which `BUILT_AGENTS` fan-out agents already expose
#: the SAME target-game facts an admitted `contextual_evidence` dimension carries.
#: `venue`/`player_performance` map to no real agent today (genuinely new signal,
#: audited NONE/LOW risk); `market`/`weather` each overlap a real, built upstream
#: agent (audited HIGH/MEDIUM risk) -- see that pass's ops doc for the full finding.
DIMENSION_OVERLAPPING_AGENTS: dict[str, frozenset[str]] = {
    "market": frozenset({"vegas_line_agent", "closing_line_movement_agent"}),
    "weather": frozenset({"weather_agent"}),
    "venue": frozenset(),
    "player_performance": frozenset(),
}

#: Deliberately plain, disclosed keyword list -- not NLP, not a trend-classifier.
#: A reasoning string containing any of these words while player_performance's own
#: sample_size is 1 is flagged for human review, nothing more.
TREND_LANGUAGE_KEYWORDS: tuple[str, ...] = (
    "trend", "trending", "tendency", "pattern", "consistently", "typically", "usually", "historically",
)

#: Negation cues scanned in the window immediately BEFORE a matched keyword
#: (2026-09-15, after the real 6-call experiment). Both flags that fired in that
#: run were false positives: the model named dimensions precisely in order to say
#: it had NOT used them ("No venue, weather, or market contextual dimensions were
#: provided, so nothing there moved my estimate") and called a single observation
#: "exactly one game, not a trend or tendency" -- plain substring matching read
#: both as violations. This narrows that failure mode; it does not eliminate it,
#: since these flags remain disclosed keyword heuristics, never semantic analysis.
NEGATION_CUES: tuple[str, ...] = (
    "no ", "not ", "n't ", "never", "nothing", "none ", "without", "absent", "rather than",
    "instead of", "did not", "does not", "cannot", "declined", "excluded", "ignored",
)

#: How many characters before a keyword match are scanned for a negation cue.
#: Wide enough for "not a trend", "never a tendency", "no venue, weather, or
#: market"; narrow enough not to swallow an unrelated earlier clause.
NEGATION_WINDOW_CHARS = 48

#: How close `modeled_probability` must land to the candidate's own book-implied
#: probability (vig-inclusive, `app.features.probability.implied_probability`)
#: before this module flags "looks copied" for human review. Not a statistically
#: derived threshold -- a small, disclosed, conservative band, same convention as
#: `app.context_intelligence.scoring`'s own disclosed-not-derived constants.
SPORTSBOOK_COPY_EPSILON = 0.005


@dataclass(frozen=True)
class SafetyFlags:
    """Every field is a heuristic pattern-match, never a semantic judgment --
    see module docstring. Flags only; nothing here ever mutates a probability."""

    probability_moved_without_unique_contextual_reason: bool
    duplicated_evidence_appears_additionally_influential: bool
    unavailable_evidence_affects_probability: bool
    venue_alone_causes_unsupported_movement: bool
    player_history_described_as_trend: bool
    sportsbook_probability_appears_copied: bool

    @property
    def any_triggered(self) -> bool:
        return any(
            (
                self.probability_moved_without_unique_contextual_reason,
                self.duplicated_evidence_appears_additionally_influential,
                self.unavailable_evidence_affects_probability,
                self.venue_alone_causes_unsupported_movement,
                self.player_history_described_as_trend,
                self.sportsbook_probability_appears_copied,
            )
        )


@dataclass(frozen=True)
class ContextProbabilityComparisonResult:
    game_id: str
    candidate_key: str
    #: `probability_modeling_agent` run with `context_package` stripped.
    control: SequentialAgentRunResult
    #: `probability_modeling_agent` run with `context_package` exactly as given.
    #: Identical object to `control` when `context.context_package` was already
    #: `None` -- there is nothing to compare, so no second model call is spent.
    context: SequentialAgentRunResult
    control_evidence: dict
    context_evidence: dict
    #: Admitted dimensions actually present in `context_evidence["contextual_evidence"]`.
    admitted_dimensions_present: tuple[str, ...]
    #: Admitted dimensions NOT present (unavailable, or `context_package` had none).
    admitted_dimensions_unavailable: tuple[str, ...]
    #: Present dimensions whose target-game facts overlap a BUILT upstream agent
    #: already in `context.upstream_outputs` (`DIMENSION_OVERLAPPING_AGENTS`).
    duplicated_dimensions: tuple[str, ...]
    #: Present dimensions the CONTEXT run's own reasoning/supporting_evidence text
    #: actually names (keyword match -- see `_dimension_mentioned`).
    claimed_dimensions: tuple[str, ...]
    #: `context.modeled_probability - control.modeled_probability`. `None` when
    #: either run failed (nothing to compare) or context was never attached.
    probability_delta: float | None
    #: `None` when either run failed -- nothing to evaluate.
    safety_flags: SafetyFlags | None


def _negated_at(text_blob: str, index: int) -> bool:
    """True when a negation cue appears in the window immediately before
    `index` -- i.e. the keyword there is being denied, not asserted."""
    window = text_blob[max(0, index - NEGATION_WINDOW_CHARS) : index]
    return any(cue in window for cue in NEGATION_CUES)


def _mentioned_affirmatively(term: str, text_blob: str) -> bool:
    """True when `term` occurs at least once WITHOUT a negation cue in front of
    it. A term that appears only inside negated phrasing ("not a trend", "no
    venue data was provided") does not count as mentioned -- see NEGATION_CUES
    for why, and for this check's disclosed limits."""
    start = 0
    while True:
        index = text_blob.find(term, start)
        if index == -1:
            return False
        if not _negated_at(text_blob, index):
            return True
        start = index + len(term)


def _dimension_mentioned(dimension: str, text_blob: str) -> bool:
    return _mentioned_affirmatively(dimension, text_blob) or _mentioned_affirmatively(
        dimension.replace("_", " "), text_blob
    )


def _sample_size(evidence: dict, dimension: str) -> int | None:
    entry = evidence.get("contextual_evidence", {}).get("dimensions", {}).get(dimension)
    return entry["sample_size"] if entry is not None else None


def _detect_safety_flags(
    *,
    text_blob: str,
    moved: bool,
    admitted_present: tuple[str, ...],
    admitted_unavailable: tuple[str, ...],
    duplicated: tuple[str, ...],
    claimed: tuple[str, ...],
    player_performance_sample_size: int | None,
    modeled_probability: float,
    american_odds: int | None,
) -> SafetyFlags:
    sportsbook_probability_appears_copied = False
    if american_odds is not None:
        try:
            book_implied = implied_probability(american_odds)
        except InvalidOddsError:
            book_implied = None
        if book_implied is not None:
            sportsbook_probability_appears_copied = abs(modeled_probability - book_implied) < SPORTSBOOK_COPY_EPSILON

    return SafetyFlags(
        probability_moved_without_unique_contextual_reason=moved and not claimed,
        duplicated_evidence_appears_additionally_influential=moved and any(d in claimed for d in duplicated),
        unavailable_evidence_affects_probability=moved and any(_dimension_mentioned(d, text_blob) for d in admitted_unavailable),
        venue_alone_causes_unsupported_movement=(moved and admitted_present == ("venue",) and "venue" in claimed),
        player_history_described_as_trend=(
            player_performance_sample_size == 1
            and "player_performance" in claimed
            and any(_mentioned_affirmatively(kw, text_blob) for kw in TREND_LANGUAGE_KEYWORDS)
        ),
        sportsbook_probability_appears_copied=sportsbook_probability_appears_copied,
    )


async def run_context_probability_comparison(
    context: SequentialDecisionContext,
    *,
    client: httpx.AsyncClient,
    headers: dict,
    routing_rule: dict,
    adapter_registry: AdapterRegistry,
    model_providers: dict[str, str] | None = None,
    retry_engine: RetryEngine | None = None,
) -> ContextProbabilityComparisonResult:
    """Runs `probability_modeling_agent` CONTROL (context_package stripped) then
    CONTEXT (context_package exactly as given), against the SAME candidate/
    upstream_outputs/participation -- everything held constant except that one
    field. When `context.context_package` is already `None`, CONTROL and CONTEXT
    are the same evidence by construction and only one model call is made
    (the caller's `adapter_registry` need only script one response for that case).

    Never persists anything, never recomputes EV/Kelly/Risk, never changes which
    candidate would be recommended -- pure observation of what
    `ProbabilityModelingAgent.build_evidence` + one model call actually produce."""
    retry_engine = retry_engine or RetryEngine()
    agent = ProbabilityModelingAgent()

    control_context = context if context.context_package is None else dataclasses.replace(context, context_package=None)
    control_evidence = agent.build_evidence(control_context)
    control_result = await run_sequential_agent(
        agent,
        control_context,
        client=client,
        headers=headers,
        routing_rule=routing_rule,
        model_providers=model_providers,
        adapter_registry=adapter_registry,
        retry_engine=retry_engine,
    )

    if context.context_package is None:
        context_result = control_result
        context_evidence = control_evidence
    else:
        context_evidence = agent.build_evidence(context)
        context_result = await run_sequential_agent(
            agent,
            context,
            client=client,
            headers=headers,
            routing_rule=routing_rule,
            model_providers=model_providers,
            adapter_registry=adapter_registry,
            retry_engine=retry_engine,
        )

    admitted_present = tuple(sorted(context_evidence.get("contextual_evidence", {}).get("dimensions", {})))
    admitted_unavailable = tuple(sorted(set(ADMITTED_CONTEXT_DIMENSIONS) - set(admitted_present)))

    upstream_agent_names = {output.agent_name for output in context.upstream_outputs}
    duplicated_dimensions = tuple(
        sorted(dim for dim in admitted_present if DIMENSION_OVERLAPPING_AGENTS.get(dim, frozenset()) & upstream_agent_names)
    )

    probability_delta: float | None = None
    safety_flags: SafetyFlags | None = None
    claimed_dimensions: tuple[str, ...] = ()

    if control_result.status == "success" and context_result.status == "success":
        control_probability = control_result.output.modeled_probability
        context_probability = context_result.output.modeled_probability
        probability_delta = context_probability - control_probability

        text_blob = " ".join([context_result.output.reasoning, *context_result.output.supporting_evidence]).lower()
        claimed_dimensions = tuple(sorted(dim for dim in admitted_present if _dimension_mentioned(dim, text_blob)))

        safety_flags = _detect_safety_flags(
            text_blob=text_blob,
            moved=abs(probability_delta) > 1e-9,
            admitted_present=admitted_present,
            admitted_unavailable=admitted_unavailable,
            duplicated=duplicated_dimensions,
            claimed=claimed_dimensions,
            player_performance_sample_size=_sample_size(context_evidence, "player_performance"),
            modeled_probability=context_probability,
            american_odds=context.candidate.american_odds,
        )

    return ContextProbabilityComparisonResult(
        game_id=context.game_id,
        candidate_key=control_evidence["candidate"]["candidate_key"],
        control=control_result,
        context=context_result,
        control_evidence=control_evidence,
        context_evidence=context_evidence,
        admitted_dimensions_present=admitted_present,
        admitted_dimensions_unavailable=admitted_unavailable,
        duplicated_dimensions=duplicated_dimensions,
        claimed_dimensions=claimed_dimensions,
        probability_delta=probability_delta,
        safety_flags=safety_flags,
    )


def render_comparison_report(result: ContextProbabilityComparisonResult, *, label: str) -> str:
    """Plain-text rendering of one comparison run -- used to build this pass's
    ops-doc comparison report section verbatim from real harness output, never
    hand-transcribed."""
    lines = [f"=== {label} ===", f"game_id={result.game_id} candidate_key={result.candidate_key}"]
    lines.append(f"control status={result.control.status}")
    lines.append(f"context status={result.context.status}")
    lines.append(f"admitted_dimensions_present={result.admitted_dimensions_present}")
    lines.append(f"admitted_dimensions_unavailable={result.admitted_dimensions_unavailable}")
    lines.append(f"duplicated_dimensions={result.duplicated_dimensions}")
    lines.append(f"claimed_dimensions={result.claimed_dimensions}")
    if result.probability_delta is None:
        lines.append("probability_delta=N/A (a run failed)")
    else:
        lines.append(
            f"control_probability={result.control.output.modeled_probability} "
            f"context_probability={result.context.output.modeled_probability} "
            f"delta={result.probability_delta:+.4f}"
        )
    if result.safety_flags is None:
        lines.append("safety_flags=N/A (a run failed)")
    else:
        for field in dataclasses.fields(result.safety_flags):
            lines.append(f"safety_flag.{field.name}={getattr(result.safety_flags, field.name)}")
    return "\n".join(lines)
