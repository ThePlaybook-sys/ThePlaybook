"""The Probability Modeling Agent (Milestone 4.6, Decision B). First step
of the sequential Decision & Advisory chain -- consumes the fan-out
committee's own outputs plus honest participation metadata, produces a
`ProbabilityModelOutput` (not `AgentOutput`) scoped to one specific
`MarketCandidate`.

**Context Intelligence integration (2026-09-15, HQ-authorized "MANSA --
PHASE 8 BUILD_EVIDENCE CONTEXT INTEGRATION"), implementing the same-day
Admission Decision (`docs/ops/phase-8-context-probability-model-
admission-decision-2026-09-15.md`).** `build_evidence` now adds one new,
purely additive `contextual_evidence` key when `context.context_package`
is present (`app.context_intelligence.context_package.ContextPackage`,
built upstream -- this module never assembles one itself, matching every
other field on `SequentialDecisionContext`, which are all handed in
already-computed). Every existing field (`candidate`/`upstream_findings`/
`participation`) is untouched; no existing probability calculation,
recommendation-ranking logic, or weight is changed by this pass.

**`ADMITTED_CONTEXT_DIMENSIONS` is the one explicit allowlist gate** --
the Admission Decision's entire point was that admission is a deliberate,
reviewable, per-dimension decision, never an automatic consequence of
`engine.py`'s own `SUPPORTED_DIMENSIONS` growing. A `ContextPackage` may
carry any number of dimensions (today: 4 admitted -- venue,
player_performance, market, weather -- plus 6 blocked: news, injuries,
roster_role, team_performance, depth_lineup, game_state_pbp); only names
in this tuple are ever read out of it here. Widening this tuple requires
a new, explicit admission decision, exactly like the one this pass
implements -- never a silent side effect of a future engine.py change.

**What `contextual_evidence` contains, per admitted dimension present and
not `"unavailable"`:** `completeness` (`"joined"`/`"partial"`, verbatim
from `ContextPackage`, never re-derived here), `sample_size`, `facts`
(the dimension's own real facts, copied verbatim from the underlying
`ContextualDimensionResult` -- for `player_performance` this includes the
full observation list with its own `duplicate_raw_row_count`/
`canonical_row_id`/`reliability_limitations`/provenance, unchanged from
`context_package.py`'s own `to_json()` shape), `provenance` (the
dimension-level `ProvenanceRef` tuple, serialized plain, never flattened
into unlabeled values), `limitations` (the dimension's own standing
`confounders` plus its `insufficient_evidence_reason` when set), and,
for `market`/`weather` only, a `point_in_time_caveat` string (see below).
An `"unavailable"` admitted dimension is simply absent from the payload
-- never zero-filled, never a fabricated empty structure (Admission
Decision Section 5).

**No confidence is ever derived here.** `completeness` describes
evidence availability; nothing in this function reads it as, or converts
it into, a numeric confidence/probability contribution. `contextual_
evidence` carries no top-level score of any kind.

**The market/weather comparable-pool point-in-time caveat is explicit,
not silently assumed safe (Admission Decision Sections 3-5).** Both
dimensions' cross-game comparable pools (`similarity_score`/`confidence`)
are built from whole-table reads with no time filter
(`read_all_odds_snapshots`/`read_all_weather_snapshots`) -- safe only
because this codebase has exactly one real caller shape today: a LIVE
call, where "now" is real time and no future-dated comparable row can
exist. **This module has no mechanism to detect a historical/replay
call** (no such mode exists anywhere in this codebase as of this pass),
so it cannot programmatically withhold comparable-pool evidence in that
case -- instead, every `market`/`weather` entry in `contextual_evidence`
carries an explicit `point_in_time_caveat` string saying exactly this,
so a future caller (or a future replay-mode implementation) is put on
notice rather than silently trusting evidence that was never verified
safe for that use. This is a disclosed limitation, not a resolved one --
seeSection "Remaining limitations" in the pass's own ops report."""
from __future__ import annotations

from app.agents.committee_context import SequentialDecisionContext
from app.agents.probability_output import ProbabilityModelOutput
from app.agents.sequential_base import SequentialDecisionAgent
from app.context_intelligence.context_package import ContextPackage
from app.context_intelligence.models import ProvenanceRef
from app.features.candidate import candidate_key

#: The ONE explicit admission allowlist (Admission Decision, 2026-09-15).
#: A dimension name absent from this tuple can never reach
#: `contextual_evidence`, regardless of what `ContextPackage`/`engine.py`
#: carry -- see module docstring.
ADMITTED_CONTEXT_DIMENSIONS: tuple[str, ...] = (
    "venue",
    "player_performance",
    "market",
    "weather",
)

#: Standing, disclosed point-in-time caveat for the two dimensions whose
#: comparable-pool evidence has no explicit time filter (Admission
#: Decision Sections 3 and 5) -- carried verbatim into every admitted
#: `market`/`weather` entry, never silently omitted.
_COMPARABLE_POOL_LIVE_ONLY_CAVEAT = (
    "This dimension's cross-game comparable-pool evidence (similarity_score/confidence) is built "
    "from a whole-table read with no explicit point-in-time filter. It is authorized for use only "
    "in a live call (target_event_timestamp approx now, where no future-dated comparable observation "
    "can exist) -- this codebase has no historical/replay-mode detection, so this evidence has NOT "
    "been verified safe for backtesting or historical reconstruction and must be withheld or "
    "rejected in any future replay-mode caller rather than trusted silently."
)

#: This player_performance-specific caveat is already carried on every
#: individual observation inside its own `facts` (`reliability_
#: limitations`, via `PLAYER_PERFORMANCE_POINT_IN_TIME_LIMITATION`) --
#: restated here at the dimension level too so a consumer that only reads
#: top-level `point_in_time_caveat` fields (rather than each observation)
#: still sees it.
_PLAYER_PERFORMANCE_POINT_IN_TIME_CAVEAT = (
    "Eligibility is determined by comparing each historical game's own kickoff against the target "
    "event timestamp -- player_stats itself carries no observation/ingestion timestamp, so this "
    "guarantees no game occurring at or after the target event is ever included, but cannot verify "
    "finer-grained (e.g. same-day) timing. See each observation's own reliability_limitations for "
    "the full text."
)

#: venue's own facts (identity, coordinates, roof type) are static/
#: time-invariant -- explicitly stated here (rather than silently
#: omitting a caveat) so a reader never has to guess whether "no caveat"
#: means "safe" or "forgotten."
_VENUE_POINT_IN_TIME_CAVEAT = (
    "Target-game venue facts (identity, coordinates, roof type) are static/time-invariant -- there is "
    "no point-in-time risk for these facts. This does not extend to the comparable-pool sample count "
    "(other real games sharing this venue), which reflects whatever is persisted as of retrieval time."
)


def _provenance_to_json(provenance: tuple[ProvenanceRef, ...]) -> list[dict]:
    return [
        {"table": p.table, "source": p.source, "row_count": p.row_count, "earliest_at": p.earliest_at, "latest_at": p.latest_at}
        for p in provenance
    ]


def _build_contextual_evidence(context_package: ContextPackage) -> dict:
    """Pure, no I/O -- builds the `contextual_evidence` payload from an
    already-assembled `ContextPackage`. Only ever reads dimensions named
    in `ADMITTED_CONTEXT_DIMENSIONS`, and only when that dimension's own
    completeness is not `"unavailable"` -- see module docstring."""
    dimensions: dict = {}
    for name in ADMITTED_CONTEXT_DIMENSIONS:
        dim_completeness = context_package.dimension_completeness.get(name)
        if dim_completeness is None or dim_completeness.completeness == "unavailable":
            continue  # never zero-filled, never fabricated -- simply absent (Admission Decision Section 5)

        result = context_package.intelligence.dimensions[name]
        entry = {
            "completeness": dim_completeness.completeness,  # verbatim -- never re-derived, never "joined" forced
            "sample_size": dim_completeness.sample_size,
            "facts": result.facts,  # verbatim -- includes player_performance's full per-observation provenance
            "provenance": _provenance_to_json(result.provenance),
            "limitations": list(result.confounders) + ([result.insufficient_evidence_reason] if result.insufficient_evidence_reason else []),
        }
        if name in ("market", "weather"):
            entry["point_in_time_caveat"] = _COMPARABLE_POOL_LIVE_ONLY_CAVEAT
        elif name == "player_performance":
            entry["point_in_time_caveat"] = _PLAYER_PERFORMANCE_POINT_IN_TIME_CAVEAT
        elif name == "venue":
            entry["point_in_time_caveat"] = _VENUE_POINT_IN_TIME_CAVEAT
        dimensions[name] = entry

    return {
        "target_event_timestamp": context_package.target_event_timestamp,
        "dimensions": dimensions,
        "known_limitations": list(context_package.known_limitations),
    }


class ProbabilityModelingAgent(SequentialDecisionAgent):
    agent_name = "probability_modeling_agent"
    task_type = "probability_modeling_analysis"
    response_model = ProbabilityModelOutput

    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        evidence = {
            "candidate": {
                "candidate_key": candidate_key(context.candidate),
                "game_id": context.candidate.game_id,
                "sportsbook": context.candidate.sportsbook,
                "market_type": context.candidate.market_type,
                "selection": context.candidate.selection,
                "american_odds": context.candidate.american_odds,
                "point": context.candidate.point,
            },
            "upstream_findings": [output.model_dump(mode="json") for output in context.upstream_outputs],
            "participation": {
                "configured_agent_count": len(context.participation.configured_agents),
                "built_agent_count": len(context.participation.built_agents),
                "deferred_agents": sorted(context.participation.deferred_agents),
                "successful_agents": sorted(context.participation.successful_agents),
                "failed_agents": sorted(context.participation.failed_agents),
                "fan_out_status": context.participation.fan_out_status,
                "committee_completeness": context.participation.committee_completeness,
            },
        }

        if context.context_package is not None:
            evidence["contextual_evidence"] = _build_contextual_evidence(context.context_package)

        return evidence
