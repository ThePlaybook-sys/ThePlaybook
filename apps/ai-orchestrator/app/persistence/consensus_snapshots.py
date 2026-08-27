"""Consensus-snapshot persistence (Milestone 4.7).

**Real schema conflict found and resolved via the established pattern,
not a new invented rule (per Mac's "stop and report instead of
improvising" instruction) -- documented here rather than silently
worked around:** `consensus_snapshots.aggregate_confidence` is `NOT
NULL` (the original Phase-1 column, predating this milestone).
`app.features.consensus.compute_consensus` can legitimately return
`aggregate_confidence=None` (zero voting agents, zero successful
fan-out participants, or a player-prop candidate whose direction can't
be resolved) -- per the null-not-neutral discipline, this must never be
persisted as a fabricated `0.0`. **Resolution: when `aggregate_confidence`
is `None`, no `consensus_snapshots` row is written at all** -- exactly
the same "no result -> no row, never a placeholder" pattern already
established for a failed fan-out agent (`recommendation_agent_outputs`,
Milestones 4.4/4.5). The absence of a row is the honest record that
consensus could not be computed for that candidate this cycle.
"""
from __future__ import annotations

import httpx


class ConsensusSnapshotsError(Exception):
    """Raised when a consensus-snapshot read/write fails on Supabase's
    side."""


async def read_game_level_agent_outputs(client: httpx.AsyncClient, headers: dict, *, recommendation_id: str) -> list[dict]:
    """Reads back the game-level (non-candidate) fan-out outputs already
    persisted for this recommendation cycle (`candidate_key IS NULL`) --
    Decision J: consensus always sources the FROZEN `weight_applied`
    already written at fan-out time, never a fresh `agents.
    current_weight` join. Embeds each output's `agents(name, category)`
    via PostgREST's FK-based embedding (`agent_id -> agents.id`) so the
    Meta Agent's functional-group clustering evidence needs no second
    round-trip. Returns a flattened plain-dict shape, not the raw
    Supabase row -- callers never need to know PostgREST's embedding
    shape.

    **Milestone 5.2 addition:** also extracts `would_change_mind_if` --
    additive only; `app.features.consensus.compute_consensus` (the
    original, unchanged caller) reads only the keys it needs and ignores
    the rest. Used by `app.features.explainability.select_would_change_mind_if`
    to verbatim-quote the highest-weighted supporting agent's own
    invalidation condition, never a synthesized one.

    **Pre-Phase-6 Operational Readiness Gate addition (Section 10,
    2026-08-27):** also extracts `prompt_name`/`prompt_version`
    (Milestone 4.8) and `model_name`/`provider`/`used_fallback`
    (Milestone 5.3) -- additive only, same discipline as
    `would_change_mind_if` above; existing callers (consensus,
    Adaptive Weighting) ignore keys they don't need. `None` on any row
    written before the corresponding column existed -- read back exactly
    as stored, never inferred."""
    response = await client.get(
        "/rest/v1/recommendation_agent_outputs",
        params={
            "recommendation_id": f"eq.{recommendation_id}",
            "candidate_key": "is.null",
            "select": (
                "raw_output,agent_confidence,weight_applied,prompt_name,prompt_version,"
                "model_name,provider,used_fallback,agents(name,category)"
            ),
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise ConsensusSnapshotsError(
            f"failed to read game-level agent outputs for recommendation_id={recommendation_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    flattened: list[dict] = []
    for row in rows:
        raw_output = row["raw_output"]
        agents_embed = row.get("agents") or {}
        flattened.append(
            {
                "agent_name": raw_output.get("agent_name") or agents_embed.get("name"),
                "category": agents_embed.get("category"),
                "finding": raw_output.get("finding"),
                "confidence": row["agent_confidence"],
                "directional_lean": raw_output.get("directional_lean"),
                "evidence_classification": raw_output.get("evidence_classification"),
                "weight_applied": row["weight_applied"],
                "would_change_mind_if": raw_output.get("would_change_mind_if"),
                "prompt_name": row.get("prompt_name"),
                "prompt_version": row.get("prompt_version"),
                "model_name": row.get("model_name"),
                "provider": row.get("provider"),
                "used_fallback": row.get("used_fallback"),
            }
        )
    return flattened


async def persist_consensus_snapshot(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_id: str,
    candidate_key: str,
    aggregate_confidence: float,
    final_aggregate_confidence: float,
    agreement_variance: float | None,
    below_confidence_floor: bool,
    participation_metadata: dict,
    model_routing_used: dict,
    second_pass_triggered: bool,
) -> str:
    """`aggregate_confidence` must already be a real number -- callers
    never invoke this when consensus could not be computed (see module
    docstring). Returns the persisted row's `id` (Milestone 5.1 addition
    -- Strategy Engine provenance, `app.persistence.recommendation_products`,
    needs the exact snapshot row a leg was selected from; requesting
    `return=representation` here doesn't change what's written, only
    what's read back)."""
    payload = {
        "recommendation_id": recommendation_id,
        "candidate_key": candidate_key,
        "aggregate_confidence": aggregate_confidence,
        "final_aggregate_confidence": final_aggregate_confidence,
        "agreement_variance": agreement_variance,
        "below_confidence_floor": below_confidence_floor,
        "participation_metadata": participation_metadata,
        "model_routing_used": model_routing_used,
        "second_pass_triggered": second_pass_triggered,
    }
    response = await client.post(
        "/rest/v1/consensus_snapshots",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise ConsensusSnapshotsError(
            f"failed to persist consensus snapshot for recommendation_id={recommendation_id!r} "
            f"candidate_key={candidate_key!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise ConsensusSnapshotsError(
            f"consensus snapshot insert for recommendation_id={recommendation_id!r} "
            f"candidate_key={candidate_key!r} returned no row"
        )
    return rows[0]["id"]
