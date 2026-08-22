"""The shared base for the two Milestone 4.7 review agents (Meta Agent,
Elite Reconciliation Agent) -- parallels `ContextDataAgent`/
`SequentialDecisionAgent`'s prompt-construction pattern exactly, but over
`ConsensusReviewContext`. Both review the committee's already-computed
output rather than reasoning about the game or a betting decision
directly, so neither fits the two existing agent bases.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.agents.contract import MetaAgentOutput
from app.agents.consensus_review_context import ConsensusReviewContext
from app.models.types import ModelMessage

_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, reviewing The Playbook's committee output for one \
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

_META_HARD_RULE = "Hard rule: confidence_adjustment can only ever be zero or negative -- you may only hold or lower confidence, never raise it."
_ELITE_HARD_RULE = "Hard rule: confidence_adjustment can only ever be zero or negative -- reconciliation may preserve or reduce confidence, never increase it."

_META_SCHEMA = """{
  "agent_name": "<this agent's name>",
  "polarization_score": 0.0,
  "uncertainty_flag": false,
  "confidence_adjustment": 0.0,
  "reasoning": "plain-language summary of committee health for this candidate"
}"""

_ELITE_SCHEMA = """{
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

    def build_messages(self, context: ConsensusReviewContext) -> list[ModelMessage]:
        evidence = self.build_evidence(context)
        hard_rule = _META_HARD_RULE if self.response_model is MetaAgentOutput else _ELITE_HARD_RULE
        schema = _META_SCHEMA if self.response_model is MetaAgentOutput else _ELITE_SCHEMA
        system = _SYSTEM_PROMPT_TEMPLATE.format(agent_name=self.agent_name, hard_rule=hard_rule, schema=schema)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)]
