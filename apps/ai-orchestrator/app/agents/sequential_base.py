"""The shared Decision & Advisory (sequential) agent base (Milestone 4.6,
Decision A). Parallels `app.agents.base_agent.ContextDataAgent`'s
prompt-construction pattern exactly, but over `SequentialDecisionContext`
instead of `AgentContext` -- these four agents reason over the
committee's own outputs and deterministic downstream math, never raw
per-game facts, so forcing them into `ContextDataAgent` would be
structurally wrong (Mac's explicit instruction).

`response_model` defaults to `AgentOutput` (Expected Value/Risk
Manager/Bankroll Coach all use the ordinary shared contract -- their own
`confidence` field legitimately means "how sure is this agent in its own
interpretation," which is not the corruption Decision B addresses).
`ProbabilityModelingAgent` overrides it to `ProbabilityModelOutput`
(Decision B) -- the one agent whose numeric output is not
confidence-shaped.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.agents.committee_context import SequentialDecisionContext
from app.agents.contract import AgentOutput
from app.models.types import ModelMessage

_SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, part of The Playbook's sequential \
decision chain -- you reason over the committee's own findings and already-computed deterministic \
numbers, never raw game facts directly.

You will be given a JSON object containing upstream findings and/or already-computed deterministic \
values (probabilities, EV, variance, stake math). Do not recompute, guess, or invent any numeric \
value that is already provided -- treat every given value exactly as given, including any "null" \
value, which means that piece of information is genuinely unavailable, never neutral or zero. \
Reason only about what these already-computed facts mean for this specific wager.

Partial committee participation is normal, not a failure: some upstream agent categories may be \
intentionally deferred (no capability exists yet), which is different from an agent that ran and \
failed this cycle. Weigh only the findings actually present; never fabricate a missing category's \
opinion.

{output_instructions}"""

_AGENT_OUTPUT_INSTRUCTIONS = """Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent's name>",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}"""

_PROBABILITY_OUTPUT_INSTRUCTIONS = """Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent's name>",
  "candidate_key": "<the evaluated candidate's key, exactly as given>",
  "selection": "<which side this probability applies to>",
  "modeled_probability": 0.0,
  "confidence_in_probability": 0.0,
  "reasoning": "plain-language explanation",
  "supporting_evidence": ["specific data points used"],
  "would_change_mind_if": "explicit invalidation condition"
}
modeled_probability is your calibrated estimate that this SPECIFIC candidate wins -- it is a \
different number from confidence_in_probability, which is how strongly you hold that estimate \
given the evidence actually available (e.g. lower confidence_in_probability when committee \
participation is partial)."""


class SequentialDecisionAgent(ABC):
    agent_name: str
    task_type: str
    response_model: type[BaseModel] = AgentOutput

    @abstractmethod
    def build_evidence(self, context: SequentialDecisionContext) -> dict:
        """Returns this agent's evidence as a plain dict -- upstream
        findings and/or deterministic values, copied verbatim, never
        summarized or recomputed here."""
        raise NotImplementedError

    def build_messages(self, context: SequentialDecisionContext) -> list[ModelMessage]:
        evidence = self.build_evidence(context)
        instructions = _PROBABILITY_OUTPUT_INSTRUCTIONS if self.response_model is not AgentOutput else _AGENT_OUTPUT_INSTRUCTIONS
        system = _SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE.format(agent_name=self.agent_name, output_instructions=instructions)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)]
