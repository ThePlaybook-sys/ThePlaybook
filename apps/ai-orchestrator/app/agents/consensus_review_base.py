"""The shared base for the two Milestone 4.7 review agents (Meta Agent,
Elite Reconciliation Agent) -- parallels `ContextDataAgent`/
`SequentialDecisionAgent`'s prompt-construction pattern exactly, but over
`ConsensusReviewContext`. Both review the committee's already-computed
output rather than reasoning about the game or a betting decision
directly, so neither fits the two existing agent bases.

**Milestone 4.8, Option C:** `build_messages` takes an already-resolved
`system_prompt` string (see `app.agents.base_agent`'s identical note).
Neither Meta Agent's nor Elite Reconciliation Agent's output is persisted
as a `recommendation_agent_outputs` row today (unchanged by Milestone
4.8 -- out of its approved scope), so their resolved prompt provenance is
used to build the model call but has no persisted home yet, same as
their raw output itself.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.agents.contract import MetaAgentOutput
from app.agents.consensus_review_context import ConsensusReviewContext
from app.models.types import ModelMessage

#: Preserved verbatim -- source wording for the Milestone 4.8
#: prompt_registry seed rows (meta_agent, consensus_reconciliation_agent).
#: No longer read at runtime.
_LEGACY_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, reviewing The Playbook's committee output for one \
specific betting candidate -- you do not analyze the game or the candidate directly, only the \
committee's already-computed findings and consensus result given to you.

You will be given the fan-out committee's findings (grouped by functional category) and the \
deterministic aggregate_confidence/agreement_variance already computed for this candidate. Do not \
recompute, guess, or invent any numeric value that is already provided -- treat every given value \
exactly as given. Partial committee participation is normal: some agent categories may be \
intentionally deferred (no capability exists yet), which is different from an agent that ran and \
failed this cycle -- weigh only the findings actually present.

{hard_rule}

Return ONLY a JSON object matching this exact shape, with no other text:
{schema}"""

_LEGACY_META_HARD_RULE = "Hard rule: confidence_adjustment can only ever be zero or negative -- you may only hold or lower confidence, never raise it."
_LEGACY_ELITE_HARD_RULE = "Hard rule: confidence_adjustment can only ever be zero or negative -- reconciliation may preserve or reduce confidence, never increase it."

_LEGACY_META_SCHEMA = """{
  "agent_name": "<this agent's name>",
  "polarization_score": 0.0,
  "uncertainty_flag": false,
  "confidence_adjustment": 0.0,
  "reasoning": "plain-language summary of committee health for this candidate"
}"""

_LEGACY_ELITE_SCHEMA = """{
  "agent_name": "<this agent's name>",
  "candidate_key": "<the candidate key, exactly as given>",
  "reasoning": "reconciliation reasoning",
  "confidence_adjustment": 0.0,
  "supporting_evidence": ["specific disagreement points reconciled"],
  "would_change_mind_if": "explicit invalidation condition"
}"""


class ConsensusReviewAgent(ABC):
    agent_name: str
    task_type: str
    response_model: type[BaseModel]

    @abstractmethod
    def build_evidence(self, context: ConsensusReviewContext) -> dict:
        raise NotImplementedError

    def build_messages(self, context: ConsensusReviewContext, *, system_prompt: str) -> list[ModelMessage]:
        """`system_prompt` is this agent's exact, already-resolved
        canonical text (see `app.agents.base_agent.ContextDataAgent.
        build_messages`'s identical note) -- required keyword arg, no
        default, no implicit fallback."""
        evidence = self.build_evidence(context)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system_prompt), ModelMessage(role="user", content=user)]
