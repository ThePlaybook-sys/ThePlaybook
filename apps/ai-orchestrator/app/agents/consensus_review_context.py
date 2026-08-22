"""The shared context for the two Milestone 4.7 review agents (Meta
Agent, Elite Reconciliation Agent) -- neither consumes `AgentContext`
(per-game raw facts, Milestone 4.4) nor `SequentialDecisionContext`
(the Probability->EV->Risk->Bankroll chain, Milestone 4.6). Both instead
review the fan-out committee's own already-persisted findings plus the
deterministic consensus result computed for one specific candidate."""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.committee_context import ParticipationMetadata


@dataclass(frozen=True)
class ConsensusReviewContext:
    game_id: str
    correlation_id: str
    candidate_key: str
    #: Flattened, already-persisted game-level fan-out outputs -- each a
    #: plain dict: `agent_name`, `category`, `finding`, `confidence`,
    #: `directional_lean`, `evidence_classification`. Read back from
    #: `recommendation_agent_outputs` (Decision J), never re-run live.
    agent_findings: tuple[dict, ...]
    aggregate_confidence: float
    agreement_variance: float
    participation: ParticipationMetadata
    #: Populated only for the Elite Reconciliation Agent, per Volume 4
    #: Section 4.3's own text: "given all 21 fan-out agents' raw outputs
    #: plus the Meta Agent's reasoning field." `None` for the Meta
    #: Agent's own review, which runs first and has no Meta output yet.
    meta_reasoning: str | None = None
