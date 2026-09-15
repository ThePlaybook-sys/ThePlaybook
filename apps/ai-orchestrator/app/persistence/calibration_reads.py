"""The calibration ledger's read side (Phase 8, "PHASE 8 PROBABILITY CALIBRATION
LEDGER", 2026-09-15). Read-only: nothing in this module writes, and nothing in it
recomputes a historical prediction.

**No new prediction table was created, deliberately.** Every field the calibration
ledger needs already exists, frozen at decision time, in three tables that each
carry a DB-level append-only trigger (verified live before this module was
written: `trg_block_rao_update`, `trg_block_recommendation_leg_update`,
`trg_block_leg_grade_event_update`):

    recommendation_legs            -- the frozen bet: candidate_key, game_id,
                                      market_type, selection, sportsbook,
                                      american_odds, point, created_at
    recommendation_agent_outputs   -- the frozen prediction: raw_output
                                      (modeled_probability, confidence_in_
                                      probability), prompt_name/prompt_version,
                                      model_name/provider/used_fallback,
                                      candidate_key, created_at
    recommendation_leg_grade_events -- the authoritative outcome: outcome,
                                      graded_at, grading_version, is_correction,
                                      corrects_grade_event_id

A new table would have added a second, mutable-by-default copy of data that is
already immutable -- strictly worse for the one property that matters most here
("do not let later prompt/model/context changes mutate historical prediction
records"). What was missing was never storage; it was the JOIN. This module is
that join.

**Linkage.** A leg and its prediction meet at `(recommendation_id,
candidate_key)`: `recommendation_legs` carries both, and
`recommendation_agent_outputs` is tagged with both for every candidate-scoped
row (Milestone 4.6, Decision G). The prediction row is further narrowed to the
`probability_modeling_agent` output specifically -- that is the only agent whose
`raw_output` contains a `modeled_probability` at all.

**Outcome authority.** The grade is read from the existing grading lifecycle, never
recomputed here: the latest row per `(leg, grading_version)` ordered by
`created_at desc`, exactly mirroring `app.persistence.postgame_grading.
read_latest_leg_grade_event`'s own definition of "current". Because a correction is
a NEW row pointing at the one it supersedes (never an UPDATE), that latest row IS
the authoritative present grade, and `grade_is_correction`/`corrects_grade_event_id`
travel forward with it so a corrected history stays visible rather than flattened.

**Unsupported grading cases stay unsupported.** This module filters nothing in or
out by market type. A leg whose market this codebase cannot grade simply has no
terminal grade event, so it never becomes a settled prediction -- no player-prop
grading support is invented here.
"""
from __future__ import annotations

import httpx

from app.features.calibration import SettledPrediction
from app.features.grading import GRADING_VERSION
from app.features.probability import InvalidOddsError, implied_probability

#: Only this agent's output carries a modeled_probability.
PROBABILITY_AGENT_NAME = "probability_modeling_agent"

#: Outcomes that represent a settled, realized event. `PENDING_MISSING_DATA` is
#: excluded here (the bet has not resolved yet), while PUSH/VOID are included as
#: settled-but-unscoreable -- `app.features.calibration` reports them separately
#: rather than coercing them into a win or loss.
SETTLED_OUTCOMES = ("WIN", "LOSS", "PUSH", "VOID_NO_ACTION")


class CalibrationReadError(Exception):
    """Raised when a calibration-ledger read fails on Supabase's side -- never
    silently returns a partial ledger, which would understate or overstate
    measured calibration without the caller knowing."""


async def _get(client: httpx.AsyncClient, headers: dict, path: str, params: dict, *, what: str) -> list[dict]:
    response = await client.get(path, params=params, headers=headers)
    if response.status_code != 200:
        raise CalibrationReadError(f"failed to read {what}: {response.status_code} {response.text}")
    return response.json()


async def _read_scheduled_starts(client: httpx.AsyncClient, headers: dict, *, game_ids: list[str]) -> dict[str, str | None]:
    """Kickoff times for the events behind these legs, batched into one read.
    Required by the forward-looking timing contract: a prediction is only a
    forecast if it existed strictly before `scheduled_start`. A game row that
    somehow lacks one yields `None`, which the eligibility rule reports as an
    exclusion rather than silently treating as "in time"."""
    if not game_ids:
        return {}
    rows = await _get(
        client,
        headers,
        "/rest/v1/games",
        {"id": f"in.({','.join(sorted(set(game_ids)))})", "select": "id,scheduled_start"},
        what="games scheduled_start",
    )
    return {row["id"]: row.get("scheduled_start") for row in rows}


async def _read_agent_id(client: httpx.AsyncClient, headers: dict, *, agent_name: str) -> str | None:
    rows = await _get(
        client,
        headers,
        "/rest/v1/agents",
        {"name": f"eq.{agent_name}", "select": "id", "limit": "1"},
        what=f"agents row for {agent_name!r}",
    )
    return rows[0]["id"] if rows else None


def _extract_probability_output(raw_output: dict) -> dict | None:
    """`cycle.py` persists the probability agent's row as
    `{"probability_output": {...}}` (plus, from 2026-09-15, a sibling
    `"context_provenance"`). A row that does not carry that key is not a
    probability prediction and is skipped rather than guessed at."""
    output = raw_output.get("probability_output")
    return output if isinstance(output, dict) else None


async def read_settled_predictions(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    grading_version: str = GRADING_VERSION,
    limit: int = 1000,
) -> list[SettledPrediction]:
    """Every prediction that has both a frozen `modeled_probability` and a
    terminal grade, joined into `SettledPrediction`. A leg with no prediction
    row, a prediction with no terminal grade, or a grade still
    `PENDING_MISSING_DATA` simply does not appear -- the ledger reports what has
    actually settled, never a partially-resolved placeholder.

    **Post-event predictions are returned, not filtered.** A prediction made at
    or after its event's `scheduled_start` is still a real persisted row and is
    still returned here, carrying the kickoff time that disqualifies it;
    `SettledPrediction.calibration_exclusion_reason` then holds it out of every
    metric. Filtering it away at read time would hide a process problem instead
    of surfacing it."""
    legs = await _get(
        client,
        headers,
        "/rest/v1/recommendation_legs",
        {
            "select": "id,recommendation_id,candidate_key,game_id,market_type,selection,sportsbook,american_odds,point,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        what="recommendation_legs",
    )
    if not legs:
        return []

    scheduled_starts = await _read_scheduled_starts(client, headers, game_ids=[leg["game_id"] for leg in legs])
    agent_id = await _read_agent_id(client, headers, agent_name=PROBABILITY_AGENT_NAME)
    if agent_id is None:
        raise CalibrationReadError(
            f"no agents row named {PROBABILITY_AGENT_NAME!r} -- cannot identify which persisted "
            f"outputs are probability predictions"
        )

    predictions: list[SettledPrediction] = []
    for leg in legs:
        outputs = await _get(
            client,
            headers,
            "/rest/v1/recommendation_agent_outputs",
            {
                "recommendation_id": f"eq.{leg['recommendation_id']}",
                "candidate_key": f"eq.{leg['candidate_key']}",
                "agent_id": f"eq.{agent_id}",
                "select": "id,raw_output,prompt_name,prompt_version,model_name,provider,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            what=f"probability output for leg {leg['id']!r}",
        )
        if not outputs:
            continue
        probability_output = _extract_probability_output(outputs[0]["raw_output"] or {})
        if probability_output is None or "modeled_probability" not in probability_output:
            continue

        grades = await _get(
            client,
            headers,
            "/rest/v1/recommendation_leg_grade_events",
            {
                "recommendation_leg_id": f"eq.{leg['id']}",
                "grading_version": f"eq.{grading_version}",
                "select": "id,outcome,graded_at,grading_version,is_correction,corrects_grade_event_id",
                "order": "created_at.desc",
                "limit": "1",
            },
            what=f"grade events for leg {leg['id']!r}",
        )
        if not grades or grades[0]["outcome"] not in SETTLED_OUTCOMES:
            continue
        grade = grades[0]

        try:
            book_implied = implied_probability(leg["american_odds"])
        except InvalidOddsError:
            # A structurally invalid stored price is a real data problem, not a
            # prediction to silently score against a guessed break-even.
            continue

        predictions.append(
            SettledPrediction(
                candidate_key=leg["candidate_key"],
                recommendation_id=leg["recommendation_id"],
                recommendation_leg_id=leg["id"],
                game_id=leg["game_id"],
                market_type=leg["market_type"],
                selection=leg["selection"],
                sportsbook=leg["sportsbook"],
                american_odds=leg["american_odds"],
                point=float(leg["point"]) if leg.get("point") is not None else None,
                sportsbook_implied_probability=book_implied,
                modeled_probability=float(probability_output["modeled_probability"]),
                confidence_in_probability=(
                    float(probability_output["confidence_in_probability"])
                    if probability_output.get("confidence_in_probability") is not None
                    else None
                ),
                model_name=outputs[0].get("model_name"),
                provider=outputs[0].get("provider"),
                prompt_name=outputs[0].get("prompt_name"),
                prompt_version=outputs[0].get("prompt_version"),
                predicted_at=outputs[0].get("created_at"),
                context_provenance=(outputs[0]["raw_output"] or {}).get("context_provenance"),
                scheduled_start=scheduled_starts.get(leg["game_id"]),
                outcome=grade["outcome"],
                graded_at=grade.get("graded_at"),
                grading_version=grade.get("grading_version"),
                grade_event_id=grade.get("id"),
                grade_is_correction=bool(grade.get("is_correction")),
                corrects_grade_event_id=grade.get("corrects_grade_event_id"),
            )
        )

    return predictions
