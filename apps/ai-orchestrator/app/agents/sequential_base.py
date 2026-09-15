"""The shared Decision & Advisory (sequential) agent base (Milestone 4.6,
Decision A; `build_messages` reworked Milestone 4.8). Parallels
`app.agents.base_agent.ContextDataAgent`'s prompt-construction pattern
exactly, but over `SequentialDecisionContext` instead of `AgentContext`
-- these four agents reason over the committee's own outputs and
deterministic downstream math, never raw per-game facts, so forcing them
into `ContextDataAgent` would be structurally wrong (Mac's explicit
instruction).

`response_model` defaults to `AgentOutput` (Expected Value/Risk
Manager/Bankroll Coach all use the ordinary shared contract -- their own
`confidence` field legitimately means "how sure is this agent in its own
interpretation," which is not the corruption Decision B addresses).
`ProbabilityModelingAgent` overrides it to `ProbabilityModelOutput`
(Decision B) -- the one agent whose numeric output is not
confidence-shaped.

**Milestone 4.8, Option C:** `build_messages` takes an already-resolved
`system_prompt` string (see `app.agents.base_agent`'s identical note) --
`_LEGACY_SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE`/`_LEGACY_*_INSTRUCTIONS`
below are preserved verbatim only as the source wording for each
concrete agent's Milestone 4.8 `prompt_registry` seed row (`{agent_name}`
and `{output_instructions}` both fully baked in per agent at
seed-authoring time -- neither is a runtime variable once a prompt is
scoped to one agent with one fixed `response_model`)."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.agents.committee_context import SequentialDecisionContext
from app.agents.contract import AgentOutput
from app.models.types import ModelMessage

_LEGACY_SEQUENTIAL_SYSTEM_PROMPT_TEMPLATE = """You are the {agent_name}, part of The Playbook's sequential \
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

_LEGACY_AGENT_OUTPUT_INSTRUCTIONS = """Return ONLY a JSON object matching this exact shape, with no other text:
{
  "agent_name": "<this agent's name>",
  "finding": "short plain-language summary",
  "supporting_evidence": ["specific data points used"],
  "evidence_classification": "data_backed | inference | assumption",
  "directional_lean": "home | away | over | under | none",
  "confidence": 0.0,
  "would_change_mind_if": "explicit invalidation condition"
}"""

#: Appended to `_LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS` by plain string concatenation (never
#: `.format()`) wherever the two are combined -- the instructions string above contains literal
#: JSON `{`/`}` characters that `.format()` would misread as its own placeholders.
_LEGACY_CONTEXTUAL_EVIDENCE_GUARDRAILS = """If the evidence includes a "contextual_evidence" key, treat it as SUPPORTING evidence only -- \
it is never permission to invent a numeric adjustment. Follow these rules exactly:
- Do not assign an arbitrary weight or point value to any contextual_evidence dimension. There is \
no calibrated formula for how much any dimension should move your probability; if you cannot \
articulate a specific, evidence-grounded reason tied to THIS candidate, do not let that dimension \
move your number at all.
- "completeness" (joined/partial/unavailable) describes how much evidence exists, not how \
confident you should be. Never treat a "joined" dimension as inherently more persuasive than a \
"partial" one just because more data rows back it -- judge the actual facts, not the completeness \
label.
- A dimension with completeness "partial" must be treated cautiously -- weigh it, if at all, less \
than a "joined" dimension with an equivalent fact pattern.
- A dimension with completeness "unavailable" (or omitted entirely) contributes NOTHING to your \
probability. Do not infer, guess, or fill in what unavailable evidence might have shown.
- contextual_evidence.player_performance with sample_size 1 is exactly one historical observation \
-- never describe or treat it as a trend, tendency, or pattern. A single game proves nothing about \
repeatability.
- HARD RULE, evidence floor (this is a floor, not a weight): contextual_evidence.player_performance \
with sample_size 1 must NOT change your modeled_probability in either direction, by any amount. You \
MAY cite it in your reasoning, and you MAY describe the role or usage it shows. Your \
modeled_probability must nevertheless be exactly the number you would have produced had that \
dimension been absent entirely. It must never be the reason your estimate crosses the candidate's \
own break-even price, and it must never be what creates an apparent edge. One game sits below the \
evidentiary floor for moving a number at all -- it is not a small effect to be weighed, it is no \
effect. This restriction applies only at sample_size 1; it does not apply once sample_size is 2 or \
more.
- Do not change your probability merely because contextual_evidence.weather or \
contextual_evidence.venue data exists. Existence of data is not evidence of an effect; only cite \
it if the specific facts given plausibly affect THIS candidate.
- contextual_evidence.venue evidence is normally informational/neutral. Only let it move your \
probability if the evidence itself describes an independently-supported performance effect at \
that venue -- not merely that the game is being played there.
- The target game's own moneyline/spread/total line and any market-movement findings from \
upstream committee agents (e.g. a Vegas Line or Closing Line Movement finding) already reflect the \
target game's market. If contextual_evidence.market repeats those same target-game facts, that \
repetition is NOT independent confirmation and must not receive additional influence beyond what \
you already gave the upstream market evidence -- only a genuinely new fact (e.g. the cross-game \
comparable-pool statistics) may be weighed on its own.
- If an upstream weather finding (e.g. a Weather Agent finding) already covers the same conditions \
contextual_evidence.weather describes, that is one piece of evidence observed twice, not two \
independent confirmations -- do not double-count it.
- In general, do not count the same underlying fact more than once just because it appears under \
more than one key in the evidence you were given.
- Never copy a sportsbook's implied probability (from odds, a line, or a market finding) directly \
into modeled_probability. modeled_probability is YOUR calibrated estimate; it may agree with the \
market, but it must be your own reasoned judgment, not a restated market number.
- Your reasoning must name which SPECIFIC, UNIQUE piece of evidence actually affected your \
judgment -- not a category of evidence you merely had access to. If contextual_evidence was \
present but did not change your estimate, say so plainly rather than listing it as if it \
mattered."""

_LEGACY_PROBABILITY_OUTPUT_INSTRUCTIONS = """Return ONLY a JSON object matching this exact shape, with no other text:
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

    def build_messages(self, context: SequentialDecisionContext, *, system_prompt: str) -> list[ModelMessage]:
        """`system_prompt` is this agent's exact, already-resolved
        canonical text (see `app.agents.base_agent.ContextDataAgent.
        build_messages`'s identical note) -- required keyword arg, no
        default, no implicit fallback."""
        evidence = self.build_evidence(context)
        user = json.dumps(evidence, default=str)
        return [ModelMessage(role="system", content=system_prompt), ModelMessage(role="user", content=user)]
