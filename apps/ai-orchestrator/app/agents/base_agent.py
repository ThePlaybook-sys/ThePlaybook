"""The shared Context & Data agent base (Milestone 4.4; `build_messages`
reworked Milestone 4.8). Every concrete agent supplies only
`agent_name`/`task_type`/`build_evidence` -- prompt construction and the
model call itself are identical across all of them, matching Volume 4
Section 2.1's single shared output contract.

**Raw-fact/AI-reasoning separation (Decision 6), enforced structurally,
not just by convention:** `build_evidence` returns a plain dict of
already-computed facts -- copied verbatim into the prompt, never
summarized, reworded, or filled in by this base class. The model is
instructed to reason about significance, never to recompute or
second-guess the evidence values themselves.

**Milestone 4.8, Option C (Mac's approved direction):** `build_messages`
now takes an already-resolved `system_prompt` string rather than
formatting it from a module constant itself -- prompt resolution
(`app.persistence.model_config.resolve_active_prompt`) happens at the
orchestration/harness boundary (`app.orchestration.fanout.run_agent`),
never inside this class via its own Supabase/network I/O.
`_LEGACY_SYSTEM_PROMPT_TEMPLATE` below is preserved verbatim as the exact
wording seeded into `prompt_registry` as every Context & Data agent's
initial v1 canonical prompt (per-agent, with `{agent_name}` substituted
at seed-authoring time, not at runtime -- `agent_name` never actually
varies per execution once a prompt is scoped to one agent) -- it is not
read by this class and must never become an implicit runtime fallback."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.context import AgentContext
from app.models.types import ModelMessage

#: Preserved verbatim from Milestone 4.4 -- source wording for the
#: Milestone 4.8 prompt_registry seed rows (see
#: scripts/generate_prompt_registry_seed.py). No longer read at runtime.
_LEGACY_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, one independent voice on The Playbook's committee \
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

    def build_messages(self, context: AgentContext, *, system_prompt: str) -> list[ModelMessage]:
        """`system_prompt` is the exact, already-resolved canonical text
        for this agent (production: `resolve_active_prompt`'s
        `.prompt_text`, verbatim, no further formatting -- the
        `prompt_registry` row already has `{agent_name}` baked in as
        literal text, since it never varies per execution. Tests supply
        their own literal string directly -- required keyword arg, no
        default, so no call site can silently omit it and fall back to
        anything)."""
        evidence = self.build_evidence(context)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system_prompt), ModelMessage(role="user", content=user)]
