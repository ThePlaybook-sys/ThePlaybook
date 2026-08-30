"""Phase 6 Milestone 2 -- Track Record read model (Volume 5 v5.0 §5/§6).

Scoped to exactly the Category A/B metrics HQ approved: sample size,
product-level Win/Loss/Push/Void record, and a recommendation-type
breakdown of that same record. Explicitly NOT built here, per HQ's
repeated instruction: units, ROI, EV realization, CLV, calibration,
projected-user performance, verified-user performance -- none of those
have a live writer anywhere in this codebase (confirmed during Phase 6
planning), and inventing one here would be exactly the "new analytics
engine" HQ ruled out for this milestone.

**Unit of observation is the recommendation PRODUCT, never the leg**
(HQ Final Decision 2). `MIXED_SETTLED` (the real, wired outcome
`app.features.grading.rollup_product_outcome` persists for a
`multiple_singles` product once every leg is terminally graded) is
reported as its own bucket -- never folded into `win` or `loss`, since
it is neither. `NOT_APPLICABLE` (`no_bet`/`bankroll_preservation`,
confirmed the only value those two types ever receive) and
`PENDING_MISSING_DATA` are excluded from the sample entirely: neither
is a settled bet outcome, so counting them would misstate what the
sample actually measures.

**Sample-status threshold (a disclosed, low-stakes policy choice, not
handed down by HQ):** `zero` at n=0, `low` for 0<n<30, `mature` at
n>=30 -- a conventional statistical minimum, not derived from any
Blueprint value. Flagged in the Milestone 2 close-out report as a
threshold future product direction may want to revisit, not asserted as
authoritative.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, get_current_user
from app.entitlement import read_active_subscription_tier, tier_permits
from app.supabase_client import new_client, postgrest_headers

router = APIRouter(prefix="/v1/track-record", tags=["track-record"])

_SETTLED_SINGLE_OUTCOMES = {"WIN": "win", "LOSS": "loss", "PUSH": "push", "VOID_NO_ACTION": "voidNoAction"}
_LOW_SAMPLE_THRESHOLD = 30


def _empty_record() -> dict:
    return {"win": 0, "loss": 0, "push": 0, "voidNoAction": 0, "mixedSettled": 0}


def _tally(record: dict, outcome: str) -> None:
    if outcome in _SETTLED_SINGLE_OUTCOMES:
        record[_SETTLED_SINGLE_OUTCOMES[outcome]] += 1
    elif outcome == "MIXED_SETTLED":
        record["mixedSettled"] += 1
    # NOT_APPLICABLE / PENDING_MISSING_DATA: not tallied at all -- see
    # module docstring.


def _sample_size(record: dict) -> int:
    return sum(record.values())


def _sample_status(sample_size: int) -> str:
    if sample_size == 0:
        return "zero"
    if sample_size < _LOW_SAMPLE_THRESHOLD:
        return "low"
    return "mature"


@router.get("")
async def get_track_record(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with new_client() as client:
        user_tier = await read_active_subscription_tier(client, user_id=current_user.id)

        response = await client.get(
            "/rest/v1/recommendation_product_grade_events",
            params={
                "select": "recommendation_product_id,outcome,computed_at,"
                "recommendation_products(recommendation_type,min_required_tier,deleted_at)",
                "order": "computed_at.desc",
            },
            headers=postgrest_headers(),
        )
        response.raise_for_status()
        rows = response.json()

    latest_by_product: dict[str, dict] = {}
    for row in rows:
        product = row.get("recommendation_products")
        if product is None or product.get("deleted_at") is not None:
            continue
        if not tier_permits(product["min_required_tier"], user_tier):
            continue
        # `order=computed_at.desc` means the first row seen per product
        # is its current, most-recent outcome (a correction supersedes
        # the row it corrects chronologically, per Volume 3 §5D).
        latest_by_product.setdefault(row["recommendation_product_id"], row)

    overall = _empty_record()
    by_type: dict[str, dict] = {}
    for row in latest_by_product.values():
        product = row["recommendation_products"]
        _tally(overall, row["outcome"])
        by_type.setdefault(product["recommendation_type"], _empty_record())
        _tally(by_type[product["recommendation_type"]], row["outcome"])

    sample_size = _sample_size(overall)
    return {
        "sampleSize": sample_size,
        "sampleStatus": _sample_status(sample_size),
        "record": overall,
        "byRecommendationType": {
            rtype: {**record, "sampleSize": _sample_size(record)} for rtype, record in by_type.items()
        },
    }
