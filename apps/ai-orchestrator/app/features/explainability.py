"""Deterministic Explainability Engine domain logic (Milestone 5.2). Pure
functions only -- no I/O, mirroring every other `app.features` module.
No live model call, no `FakeModelAdapter` call even -- this module is
100% deterministic templates over already-frozen Phase 4/Milestone 5.1
facts (Decision, 2026-08-25: Milestone 5.2 is Deterministic V1; the
optional LLM narrative layer is explicitly NOT built here).

**Read-only with respect to every decision (the one rule this whole
module exists to prove, not just claim):** every function here takes
already-computed `app.features.strategy` output (`SlateStrategyResult`,
`GameDecision`, `EvaluatedCandidate`, `RejectedCandidate`) and already-read
Phase 4 persistence rows as INPUT, and returns only text/structured
explanation content as OUTPUT. Nothing here returns or mutates a
`recommendation_type`, a ranking, an EV, a confidence value, an
eligibility verdict, a stake, or a recommendation status -- there is no
function signature in this module capable of it.

**Contributing agents are the GAME-LEVEL committee only** (Injury
Intelligence, Weather, Vegas Line, Closing Line Movement, Travel &
Fatigue, Rest Days) -- the same `agent_rows` shape
`app.features.consensus.compute_consensus` already consumes (`candidate_key
IS NULL` rows). Probability Modeling, Expected Value, Risk Manager, and
Bankroll Coach are candidate-level, sequential, and never vote on
direction (Milestone 4.6/4.9) -- they are consumed separately (EV/
confidence already frozen on `recommendation_legs`; Risk Manager's own
deterministic payload read back explicitly for `biggest_risks`).

**`would_change_mind_if` is never synthesized.** Volume 4 §8 itself names
the mechanism: "aggregated `would_change_mind_if` fields from top-
contributing agents." This module verbatim-quotes the single highest-
weighted SUPPORTING committee agent's own `would_change_mind_if` field --
already-frozen agent output captured for exactly this purpose since
Milestone 4.2 (`app.agents.contract.AgentOutput`) -- never inventing a
new one. `None` when no supporting agent exists, per Mac's explicit "NULL
is preferable to invented intelligence" instruction.

**Historical bet-type variance is always disclosed as unavailable**
(`RiskAssessment.historical_bet_type_variance` is permanently `None`,
Milestone 4.6) -- never silently omitted from `biggest_risks`.

**Contributing agents never include a configured-but-failed, deferred, or
non-participating agent** -- `build_contributing_agents` only ever sees
rows that exist in `recommendation_agent_outputs`, and a failed/deferred
agent never produces one (Milestone 4.4's own fan-out isolation
guarantee) -- so filtering to voting rows (non-`None` `lean_factor`)
already excludes them structurally, not by an added check.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.features.consensus import lean_factor
from app.features.strategy import EvaluatedCandidate, RejectedCandidate

#: Milestone 5.3 (Decision AX) -- the Explainability Engine logic version,
#: frozen directly onto the actual `recommendation_product_explanations`/
#: `recommendation_leg_explanations` rows this module's callers persist,
#: never onto a separate/inferred location -- so a future reconstruction
#: can tell "same evidence, same explanation algorithm" from "same
#: evidence, the algorithm changed" for any historical explanation. A
#: future deliberate change to how this module builds `why_this_shape`/
#: `why_selected`/etc. must bump this constant; it is never inferred.
EXPLAINABILITY_VERSION = "v1"

#: Unconditional -- these three categories are confirmed, by direct
#: repository/schema inspection, to have no data source anywhere in this
#: system today (Volume 3 §4.1: `public_betting`/`sharp_money` stay
#: `null`, vendor-blocked; no Referee Tendencies Agent has ever been
#: built). Disclosed every time, never conditionally checked against a
#: flag that doesn't exist.
ALWAYS_UNAVAILABLE_DISCLOSURE = (
    "Sharp Money and Public Betting data are not yet available in this system "
    "(Volume 3 §4.1) and were not used in this analysis. Referee tendency data "
    "is not yet available and was not used in this analysis."
)


@dataclass(frozen=True)
class AgentContribution:
    """One voting game-level committee agent's role in a candidate's
    consensus -- a rendered, frozen-at-write snapshot of an already
    first-class `recommendation_agent_outputs` row (Volume 3 §5A's own
    `recommendation_snapshots.agent_outputs_snapshot` precedent for this
    exact kind of denormalization). `supports` is derived, not persisted
    verbatim -- see `to_json` below for the exact persisted shape."""

    agent_name: str
    weight_applied: float
    confidence: float
    directional_lean: str
    evidence_classification: str
    participation_status: str  # always "successful" -- see module docstring
    supports: bool  # True = lean_factor 1.0 (supports); False = 0.3 (opposes)
    #: Pre-Phase-6 Operational Readiness Gate (Section 10, 2026-08-27) --
    #: the same per-agent prompt/model provenance already frozen on
    #: `recommendation_agent_outputs` since Milestone 4.8 (prompt_name/
    #: prompt_version) and Milestone 5.3 (model_name/provider/
    #: used_fallback), now threaded through so reconstruction can surface
    #: it without a second, undocumented join. All five are `None` for
    #: any historical row written before the corresponding column
    #: existed -- never inferred or backfilled.
    prompt_name: str | None = None
    prompt_version: int | None = None
    model_name: str | None = None
    provider: str | None = None
    used_fallback: bool | None = None


def build_contributing_agents(agent_rows: list[dict], *, candidate_direction: str | None) -> list[AgentContribution]:
    """`agent_rows` is the SAME flattened game-level shape
    `app.features.consensus.compute_consensus` already consumes (`{
    "agent_name", "directional_lean", "confidence", "evidence_classification",
    "weight_applied", ...}`, `candidate_key IS NULL` rows only). Returns
    only VOTING agents (non-`None` `lean_factor`) -- never a non-
    participating one, and never a player-prop candidate's agents either
    (Decision I: `candidate_direction` is always `None` for props, which
    makes `lean_factor` `None` for every row, per
    `app.features.consensus`'s own three-state rule)."""
    contributions: list[AgentContribution] = []
    for row in agent_rows:
        factor = lean_factor(row["directional_lean"], candidate_direction)
        if factor is None:
            continue
        contributions.append(
            AgentContribution(
                agent_name=row["agent_name"],
                weight_applied=row["weight_applied"],
                confidence=row["confidence"],
                directional_lean=row["directional_lean"],
                evidence_classification=row["evidence_classification"],
                participation_status="successful",
                supports=factor == 1.0,
                prompt_name=row.get("prompt_name"),
                prompt_version=row.get("prompt_version"),
                model_name=row.get("model_name"),
                provider=row.get("provider"),
                used_fallback=row.get("used_fallback"),
            )
        )
    return contributions


def contributing_agents_to_json(contributions: list[AgentContribution]) -> list[dict]:
    """The exact, approved persisted shape -- agent identity, weight_applied,
    agent confidence, directional lean, evidence classification,
    participation status, and (Pre-Phase-6 Operational Readiness Gate,
    Section 10) prompt/model provenance. `supports` (an internal derived
    convenience, not part of the approved field list) is deliberately
    excluded here."""
    return [
        {
            "agent_name": c.agent_name,
            "weight_applied": c.weight_applied,
            "confidence": c.confidence,
            "directional_lean": c.directional_lean,
            "evidence_classification": c.evidence_classification,
            "participation_status": c.participation_status,
            "prompt_name": c.prompt_name,
            "prompt_version": c.prompt_version,
            "model_name": c.model_name,
            "provider": c.provider,
            "used_fallback": c.used_fallback,
        }
        for c in contributions
    ]


def select_would_change_mind_if(agent_rows: list[dict], *, candidate_direction: str | None) -> str | None:
    """Verbatim-quotes the highest-weighted SUPPORTING committee agent's
    own `would_change_mind_if` field. `None` when no supporting agent
    exists -- never fabricated (Mac's explicit instruction)."""
    supporting = [row for row in agent_rows if lean_factor(row["directional_lean"], candidate_direction) == 1.0]
    if not supporting:
        return None
    top = max(supporting, key=lambda row: row["weight_applied"])
    return top.get("would_change_mind_if")


def build_strongest_evidence(contributions: list[AgentContribution], *, top_n: int = 3) -> str:
    """Names the top-`top_n` supporting agents by `weight_applied`. Never
    a fabricated statement when no supporting agent exists -- degrades to
    an explicit insufficient-data disclosure instead."""
    supporting = sorted((c for c in contributions if c.supports), key=lambda c: c.weight_applied, reverse=True)
    if not supporting:
        return "Insufficient committee agreement data was available to identify supporting evidence for this candidate."
    named = ", ".join(f"{c.agent_name} (weight {c.weight_applied:.2f}, confidence {c.confidence:.2f})" for c in supporting[:top_n])
    return f"The strongest supporting evidence came from: {named}."


def build_biggest_risks(risk_raw_output: dict | None) -> str:
    """`risk_raw_output` is the Risk Manager candidate-level
    `recommendation_agent_outputs.raw_output` value (shape:
    `{"agent_output": {...}, "deterministic": {"bernoulli_outcome_variance":
    ..., "historical_bet_type_variance": None}}`), or `None` if that
    agent failed/was never attempted this cycle -- never fabricated
    either way; the permanent unavailability disclosure is unconditional."""
    if risk_raw_output is None:
        variance_text = "Risk Manager analysis was unavailable for this candidate this cycle."
    else:
        variance = risk_raw_output.get("deterministic", {}).get("bernoulli_outcome_variance")
        variance_text = (
            f"Modeled outcome variance: {variance:.4f}." if variance is not None else "Modeled outcome variance unavailable."
        )
    return (
        f"{variance_text} Historical bet-type variance data is not yet available for this market "
        "and was not used in this analysis."
    )


def build_why_selected(
    candidate: EvaluatedCandidate,
    *,
    rank_position: int,
    total_qualifying: int,
    beat_same_market_conflict: bool,
) -> str:
    """`rank_position` is 1-based (1 = best by the Decision AM hierarchy).
    Always states the two qualification facts; the ranking/conflict
    sentences only appear when they're actually meaningful (a slate of
    exactly one qualifying candidate has no "ranked #1 of 1" to report)."""
    parts = [
        f"This candidate satisfied both required gates: final aggregate confidence "
        f"{candidate.final_aggregate_confidence:.4f} met or exceeded the 0.55 floor, and expected value "
        f"{candidate.ev_per_dollar:.4f} per dollar was positive."
    ]
    if total_qualifying > 1:
        parts.append(f"It ranked #{rank_position} of {total_qualifying} qualifying candidates this slate by expected value.")
    if beat_same_market_conflict:
        parts.append(
            "It was selected over the opposing side of the same market after applying the ranking hierarchy "
            "(expected value, then confidence, then candidate identifier)."
        )
    return " ".join(parts)


def build_why_this_shape(outcome: str, *, leg_count: int = 0, game_count: int = 0) -> str:
    """`outcome` is a `recommendation_products.recommendation_type` value.
    Templates only -- no LLM, no synthesis beyond the counts Strategy
    Engine already produced."""
    if outcome == "single":
        return "Exactly one candidate across the evaluated slate satisfied both the confidence and expected-value requirements; it is presented as a single recommendation."
    if outcome == "multiple_singles":
        return (
            f"{leg_count} independent candidates across the evaluated slate satisfied both requirements; each is "
            "presented as its own separate wager rather than combined, since parlay combination is not currently active."
        )
    if outcome == "no_bet":
        return "No candidate evaluated for this game satisfied both the minimum confidence and positive expected-value requirements."
    if outcome == "bankroll_preservation":
        return f"No candidate evaluated anywhere across this slate ({game_count} games) satisfied both requirements."
    raise ValueError(f"unrecognized recommendation_type for why_this_shape: {outcome!r}")


def build_why_not_other_shapes(outcome: str) -> str | None:
    if outcome == "single":
        return "No other qualifying candidate existed this slate, so multiple_singles did not apply; parlay combination is not currently active."
    if outcome == "multiple_singles":
        return "Combining these into a parlay was not performed -- same_game_parlay/multi_game_parlay remain inactive; no correlation or combined-probability calculation exists in this system."
    if outcome in ("no_bet", "bankroll_preservation"):
        return None
    raise ValueError(f"unrecognized recommendation_type for why_not_other_shapes: {outcome!r}")


def build_data_limitations(participation_metadata: dict | None) -> str:
    """Always includes the unconditional disclosure; adds committee-
    completeness detail only when `participation_metadata` is available
    and the committee was genuinely incomplete this cycle -- never implies
    completeness that wasn't confirmed."""
    parts = [ALWAYS_UNAVAILABLE_DISCLOSURE]
    if participation_metadata is not None:
        configured = participation_metadata.get("configured_agents") or []
        built = participation_metadata.get("built_agents") or []
        deferred = participation_metadata.get("deferred_agents") or []
        failed = participation_metadata.get("failed_agents") or []
        if configured and len(built) < len(configured):
            missing = sorted(set(deferred) | set(failed))
            detail = f"{len(built)} of {len(configured)} configured committee agents were available this cycle"
            parts.append(detail + (f"; missing: {', '.join(missing)}." if missing else "."))
    return " ".join(parts)


def rejected_alternatives_to_json(rejected: list[RejectedCandidate]) -> list[dict]:
    return [
        {
            "candidate_key": r.candidate.candidate_key,
            "market_type": r.candidate.market_type,
            "selection": r.candidate.selection,
            "reasons": list(r.reasons),
        }
        for r in rejected
    ]
