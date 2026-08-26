"""Milestone 5.4 persistence for the three new grading/review tables --
`recommendation_leg_grade_events`, `recommendation_product_grade_events`,
`recommendation_product_postgame_reviews` (see the schema migration's own
docstring for why these three, not four, and not one polymorphic table).

**Idempotent-retry vs. legitimate-regrade (Decision BQ) is driven by a
DB read immediately before the write, never by anything remembered in
application memory across calls.** Each `persist_*_grade` function reads
the latest existing row for `(parent_id, grading_version)` (if any),
compares its frozen facts to what was just computed, and only then
decides: no existing row -> plain insert; existing row with identical
facts -> no-op (a crashed-and-retried worker lands here); existing row
with DIFFERENT facts -> a correction insert referencing the row it
supersedes. The partial unique index on `(parent_id, grading_version)
WHERE is_correction = false` is the actual enforcement backstop against
a race between two concurrent "no existing row" reads -- a losing
insert's 409 is caught and re-read as the winning row, never treated as
a hard failure."""
from __future__ import annotations

import httpx


class PostgameGradingError(Exception):
    """Raised when a grading/review read or write fails on Supabase's
    side for a reason other than the expected unique-constraint race
    (which is handled, not raised, by `persist_leg_grade`/
    `persist_product_grade`)."""


async def read_recommendation_legs_by_game(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> list[dict]:
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={
            "game_id": f"eq.{game_id}",
            "select": "id,recommendation_product_id,market_type,selection,point,game_id,recommendation_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(f"failed to read recommendation_legs for game_id={game_id!r}: {response.status_code} {response.text}")
    return response.json()


async def read_recommendation_legs_by_product(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str
) -> list[dict]:
    response = await client.get(
        "/rest/v1/recommendation_legs",
        params={
            "recommendation_product_id": f"eq.{recommendation_product_id}",
            "select": "id,recommendation_product_id,market_type,selection,point,game_id,recommendation_id",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(
            f"failed to read recommendation_legs for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def read_no_bet_products_by_game(client: httpx.AsyncClient, headers: dict, *, game_id: str) -> list[dict]:
    """`no_bet` products are per-game (Milestone 5.1) -- always
    NOT_APPLICABLE for grading purposes (Decision BL), regardless of the
    game's own final result."""
    response = await client.get(
        "/rest/v1/recommendation_products",
        params={
            "game_id": f"eq.{game_id}",
            "recommendation_type": "eq.no_bet",
            "select": "id,recommendation_type",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(f"failed to read no_bet products for game_id={game_id!r}: {response.status_code} {response.text}")
    return response.json()


async def read_ungraded_bankroll_preservation_product_ids(client: httpx.AsyncClient, headers: dict) -> list[str]:
    """`bankroll_preservation` products are slate-level (no single
    `game_id`) and always NOT_APPLICABLE (Decision BM) -- this reads
    EVERY such product, already-graded or not; `persist_product_grade`'s
    own idempotent read-before-write makes re-grading an already-graded
    one a cheap no-op, so no separate filtering happens here. Bounded by
    nothing today (no
    `created_at` window) -- an accepted MVP scope limitation, flagged in
    the Milestone 5.4 completion report, matching this codebase's
    existing convention of flagging unbounded-scan scope decisions
    rather than silently building one."""
    response = await client.get(
        "/rest/v1/recommendation_products",
        params={"recommendation_type": "eq.bankroll_preservation", "select": "id"},
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(f"failed to read bankroll_preservation products: {response.status_code} {response.text}")
    return [row["id"] for row in response.json()]


async def read_recommendation_product(client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_products",
        params={"id": f"eq.{recommendation_product_id}", "select": "id,recommendation_type"},
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(
            f"failed to read recommendation_product id={recommendation_product_id!r}: {response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_latest_leg_grade_event(
    client: httpx.AsyncClient, headers: dict, *, recommendation_leg_id: str, grading_version: str
) -> dict | None:
    """Latest row (original or correction) for this `(leg, version)` --
    the reference point for both the idempotent-retry comparison and, if
    a correction is needed, `corrects_grade_event_id`."""
    response = await client.get(
        "/rest/v1/recommendation_leg_grade_events",
        params={
            "recommendation_leg_id": f"eq.{recommendation_leg_id}",
            "grading_version": f"eq.{grading_version}",
            "select": "id,outcome,authoritative_result,is_correction",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(
            f"failed to read latest leg grade event for recommendation_leg_id={recommendation_leg_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def read_latest_product_grade_event(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str, grading_version: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_product_grade_events",
        params={
            "recommendation_product_id": f"eq.{recommendation_product_id}",
            "grading_version": f"eq.{grading_version}",
            "select": "id,outcome,leg_outcome_counts,is_correction",
            "order": "created_at.desc",
            "limit": "1",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(
            f"failed to read latest product grade event for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def persist_leg_grade(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_leg_id: str,
    game_id: str,
    grading_version: str,
    outcome: str,
    authoritative_result: dict,
) -> tuple[str, str]:
    """Create-or-correct-or-noop for one leg's grade (Decision BQ). Reads
    the latest existing row first (see module docstring); returns
    `(status, leg_grade_event_id)` where `status` is `"created"`,
    `"unchanged"`, or `"corrected"`."""
    existing = await read_latest_leg_grade_event(
        client, headers, recommendation_leg_id=recommendation_leg_id, grading_version=grading_version
    )
    if existing is not None and existing["outcome"] == outcome and existing["authoritative_result"] == authoritative_result:
        return "unchanged", existing["id"]

    is_correction = existing is not None
    payload = {
        "recommendation_leg_id": recommendation_leg_id,
        "game_id": game_id,
        "grading_version": grading_version,
        "outcome": outcome,
        "authoritative_result": authoritative_result,
        "is_correction": is_correction,
        "corrects_grade_event_id": existing["id"] if is_correction else None,
        "correction_source": "stat_correction" if is_correction else None,
    }
    response = await client.post(
        "/rest/v1/recommendation_leg_grade_events",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code == 409 and not is_correction:
        # Lost a race against a concurrent original insert for this
        # (leg, version) -- the partial unique index is the real
        # enforcement; re-read and treat the winner's row as ours.
        winner = await read_latest_leg_grade_event(
            client, headers, recommendation_leg_id=recommendation_leg_id, grading_version=grading_version
        )
        if winner is not None:
            return "unchanged", winner["id"]
    if response.status_code not in (200, 201):
        raise PostgameGradingError(
            f"failed to persist leg grade for recommendation_leg_id={recommendation_leg_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise PostgameGradingError(f"leg grade insert for recommendation_leg_id={recommendation_leg_id!r} returned no row")
    return ("corrected" if is_correction else "created"), rows[0]["id"]


async def persist_product_grade(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    grading_version: str,
    outcome: str,
    leg_outcome_counts: dict[str, int] | None,
    correction_source: str | None = "stat_correction",
) -> tuple[str, str]:
    """Create-or-correct-or-noop for one product's rollup grade --
    mirrors `persist_leg_grade` exactly (see that function's docstring
    for the full reasoning). `correction_source` defaults to
    `"stat_correction"` (the leg-rollup case) but a caller grading a
    no_bet/bankroll_preservation product directly (no underlying leg
    correction is possible for those) never reaches the correction path
    at all -- their outcome is always identical on every call."""
    existing = await read_latest_product_grade_event(
        client, headers, recommendation_product_id=recommendation_product_id, grading_version=grading_version
    )
    if existing is not None and existing["outcome"] == outcome and existing["leg_outcome_counts"] == leg_outcome_counts:
        return "unchanged", existing["id"]

    is_correction = existing is not None
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "grading_version": grading_version,
        "outcome": outcome,
        "leg_outcome_counts": leg_outcome_counts,
        "is_correction": is_correction,
        "corrects_grade_event_id": existing["id"] if is_correction else None,
        "correction_source": correction_source if is_correction else None,
    }
    response = await client.post(
        "/rest/v1/recommendation_product_grade_events",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code == 409 and not is_correction:
        winner = await read_latest_product_grade_event(
            client, headers, recommendation_product_id=recommendation_product_id, grading_version=grading_version
        )
        if winner is not None:
            return "unchanged", winner["id"]
    if response.status_code not in (200, 201):
        raise PostgameGradingError(
            f"failed to persist product grade for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise PostgameGradingError(f"product grade insert for recommendation_product_id={recommendation_product_id!r} returned no row")
    return ("corrected" if is_correction else "created"), rows[0]["id"]


async def persist_postgame_review(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    recommendation_product_id: str,
    product_grade_event_id: str,
    grading_version: str,
    postgame_review_version: str,
    outcome_summary: str | None,
    why_it_won_or_lost: str | None,
    factual_deltas: dict | None,
    correct_agents: list[str] | None,
    underperforming_agents: list[str] | None,
    learning_notes: str | None,
) -> str:
    """Inserts one narrative Postgame Review row. Additive-only for a
    given `(recommendation_product_id, postgame_review_version)` -- the
    unique index rejects a second row for the same version outright
    (narrative regeneration under an unchanged version is not a defined
    use case yet; a genuinely new narrative bumps
    `postgame_review_version`, exactly like a grading-rule change bumps
    `grading_version`)."""
    payload = {
        "recommendation_product_id": recommendation_product_id,
        "product_grade_event_id": product_grade_event_id,
        "grading_version": grading_version,
        "postgame_review_version": postgame_review_version,
        "outcome_summary": outcome_summary,
        "why_it_won_or_lost": why_it_won_or_lost,
        "factual_deltas": factual_deltas,
        "correct_agents": correct_agents,
        "underperforming_agents": underperforming_agents,
        "learning_notes": learning_notes,
    }
    response = await client.post(
        "/rest/v1/recommendation_product_postgame_reviews",
        json=payload,
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    if response.status_code not in (200, 201):
        raise PostgameGradingError(
            f"failed to persist postgame review for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    if not rows:
        raise PostgameGradingError(f"postgame review insert for recommendation_product_id={recommendation_product_id!r} returned no row")
    return rows[0]["id"]


async def read_postgame_review(
    client: httpx.AsyncClient, headers: dict, *, recommendation_product_id: str, postgame_review_version: str
) -> dict | None:
    response = await client.get(
        "/rest/v1/recommendation_product_postgame_reviews",
        params={
            "recommendation_product_id": f"eq.{recommendation_product_id}",
            "postgame_review_version": f"eq.{postgame_review_version}",
            "select": "*",
        },
        headers=headers,
    )
    if response.status_code != 200:
        raise PostgameGradingError(
            f"failed to read postgame review for recommendation_product_id={recommendation_product_id!r}: "
            f"{response.status_code} {response.text}"
        )
    rows = response.json()
    return rows[0] if rows else None
