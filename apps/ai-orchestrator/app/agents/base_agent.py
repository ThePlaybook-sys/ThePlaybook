"""The shared Context & Data agent base (Milestone 4.4). Every concrete
agent supplies only `agent_name`/`task_type`/`build_evidence` -- prompt
construction and the model call itself are identical across all of them,
matching Volume 4 Section 2.1's single shared output contract.

**Raw-fact/AI-reasoning separation (Decision 6), enforced structurally,
not just by convention:** `build_evidence` returns a plain dict of
already-computed facts -- copied verbatim into the prompt, never
summarized, reworded, or filled in by this base class. The model is
instructed to reason about significance, never to recompute or
second-guess the evidence values themselves.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.context import AgentContext
from app.models.types import ModelMessage

_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, one independent voice on The Playbook's committee \
of sports-betting analysis agents.

You will be given a JSON object of already-computed facts. Do not recompute, guess, or invent any \
numeric or factual value -- treat every value in the evidence exactly as given, including any \
"null" value, which means that piece of information is genuinely unavailable, never neutral or \
zero. Reason only about this game's football/betting significance.

Freshness discipline: a fact whose "status" field reads "needs_refresh" or "stale" may still be \
reasoned over, but your evidence_classification and confidence must reflect that staleness risk. \
A "null" fact must never be treated as if it were a neutral/average value -- classify your finding \
as "assumption" and lower your confidence accordingly, naming the specific missing evidence in \
your finding and would_change_mind_if fields.

Return ONLY a JSON object matching this exact shape, with no other text:
{{
  "agent_name": "{agent_name}",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}}"""


class ContextDataAgent(ABC):
    agent_name: str
    task_type: str

    @abstractmethod
    def build_evidence(self, context: AgentContext) -> dict:
        """Returns this agent's raw/derived facts as a plain dict, copied
        directly from `context` -- a missing category must stay `None`
        here, never defaulted, omitted, or coerced to an empty
        placeholder that looks like "nothing to report" rather than
        "unavailable."""
        raise NotImplementedError

    def build_messages(self, context: AgentContext) -> list[ModelMessage]:
        evidence = self.build_evidence(context)
        system = _SYSTEM_PROMPT_TEMPLATE.format(agent_name=self.agent_name)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)]
