"""Tests for `POST /v1/recommendations/ask` (Phase 8.5 Pass 1,
HQ-authorized). Follows the same respx-at-the-HTTP-boundary convention
as `test_recommendations.py` -- auth is exercised for real, not
dependency-overridden. Critically, no ai-orchestrator or provider host
is ever registered with respx in any test here: if the endpoint tried
to reach one, respx would fail the request (unmatched route), which is
this suite's own proof that no provider/worker/recomputation call
occurs (Requirement 8/9 of the HQ authorization)."""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SUPABASE_URL = "https://test-project.supabase.co"
AUTH_URL = f"{SUPABASE_URL}/auth/v1/user"
USER_ID = "22222222-2222-2222-2222-222222222222"


def _mock_authenticated_user(*, tier: str | None = None) -> None:
    respx.get(AUTH_URL).mock(return_value=httpx.Response(200, json={"id": USER_ID}))
    respx.get(f"{SUPABASE_URL}/rest/v1/user_profiles").mock(
        return_value=httpx.Response(200, json=[{"id": USER_ID, "jurisdiction_state": "NJ"}])
    )
    subscription_rows = [{"tier": tier}] if tier else []
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(
        return_value=httpx.Response(200, json=subscription_rows)
    )


def _mock_empty_reads() -> None:
    for table in (
        "recommendation_activation_snapshots",
        "recommendation_product_explanations",
        "recommendation_product_grade_events",
    ):
        respx.get(f"{SUPABASE_URL}/rest/v1/{table}").mock(return_value=httpx.Response(200, json=[]))


def _mock_games(*, today_ids: list[str], by_id: dict[str, dict] | None = None) -> None:
    by_id = by_id or {}

    def _respond(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if "scheduled_start" in params:
            return httpx.Response(200, json=[{"id": i} for i in today_ids])
        id_filter = params.get("id", "")
        if id_filter.startswith("in.(") and id_filter.endswith(")"):
            ids = id_filter[len("in.(") : -1].split(",")
            return httpx.Response(200, json=[by_id[i] for i in ids if i in by_id])
        if id_filter.startswith("eq."):
            game_id = id_filter[len("eq.") :]
            return httpx.Response(200, json=[by_id[game_id]] if game_id in by_id else [])
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_respond)


def _mock_no_runs() -> None:
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))


def _ask(question: str, *, token: str | None = "validtoken") -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/v1/recommendations/ask", json={"question": question}, headers=headers)


def _two_products_two_confidences() -> None:
    """Two active, game-scoped products today: a lower-confidence pick
    on the earlier game, a higher-confidence pick on the later game --
    proves `/ask` selects by confidence, not by the neutral
    chronological ordering `/today` itself uses."""
    _mock_games(
        today_ids=["game-early", "game-late"],
        by_id={
            "game-early": {
                "id": "game-early",
                "home_team": "C",
                "away_team": "D",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "status": "scheduled",
            },
            "game-late": {
                "id": "game-late",
                "home_team": "E",
                "away_team": "F",
                "scheduled_start": "2026-09-09T20:00:00Z",
                "status": "scheduled",
            },
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-low-confidence",
                    "display_id": "2026-00001",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-early",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
                {
                    "id": "prod-high-confidence",
                    "display_id": "2026-00002",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-late",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
            ],
        )
    )

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        if "prod-low-confidence" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-low-confidence",
                    "market_type": "moneyline",
                    "selection": "C",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.02,
                    "final_aggregate_confidence": 0.56,
                    "leg_order": 1,
                }
            )
        if "prod-high-confidence" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-high-confidence",
                    "market_type": "moneyline",
                    "selection": "E",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.20,
                    "final_aggregate_confidence": 0.91,
                    "leg_order": 1,
                }
            )
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)
    _mock_empty_reads()


@respx.mock
def test_ask_requires_authentication():
    response = client.post("/v1/recommendations/ask", json={"question": "highest confidence pick today"})
    assert response.status_code == 401


@respx.mock
def test_ask_rejects_malformed_request_body():
    _mock_authenticated_user()
    response = _ask("")
    assert response.status_code == 422


@respx.mock
def test_ask_returns_highest_confidence_pick():
    """The core Pass 1 success path -- proves selection by confidence,
    not by `/today`'s own neutral chronological order, and proves the
    existing card-serialization shape is reused verbatim."""
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_two_confidences()

    response = _ask("What's MANSA's highest-confidence pick today?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == {
        "requestType": "recommendation_lookup",
        "selectionMode": "highest_confidence",
        "marketType": None,
        "timeScope": "today",
        "count": 1,
    }
    assert body["insufficientEvidence"] is False
    assert body["reason"] is None
    assert body["result"]["label"] == "MANSA's highest-confidence pick today"
    assert body["result"]["selectionMetric"] == "finalAggregateConfidence"
    assert "not a guarantee" in body["result"]["disclosure"].lower()
    recommendation = body["result"]["recommendation"]
    assert recommendation["displayId"] == "2026-00002"
    assert recommendation["legs"][0]["finalAggregateConfidence"] == 0.91
    # Pass 4: default count=1 must leave `results` a single-item list
    # identical to `result` -- the existing single-pick behavior,
    # unchanged, just also exposed through the new plural field.
    assert body["results"] == [body["result"]]


@respx.mock
def test_ask_recognizes_equivalent_natural_language_phrasing():
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_two_confidences()

    for phrase in ("give me your most confident pick", "what's your strongest confidence play"):
        response = _ask(phrase)
        assert response.status_code == 200, phrase
        assert response.json()["result"]["recommendation"]["displayId"] == "2026-00002", phrase


@respx.mock
def test_ask_returns_insufficient_evidence_when_nothing_eligible_today():
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_games(today_ids=[])

    response = _ask("highest confidence pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["result"] is None
    assert "No eligible" in body["reason"]


@respx.mock
def test_ask_returns_honest_unsupported_response_and_never_conflates_safest_with_confidence():
    """Direct proof of the HQ terminology guardrail: 'safest' must
    never resolve to the highest-confidence selection."""
    _mock_authenticated_user()

    response = _ask("what's the safest bet today?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert body["intent"]["selectionMode"] is None
    assert body["insufficientEvidence"] is False
    assert body["result"] is None
    assert "highest-confidence" in body["reason"]


@respx.mock
def test_ask_returns_honest_ambiguous_response_for_unrecognized_text():
    _mock_authenticated_user()

    response = _ask("what should I have for lunch")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "ambiguous"
    assert body["result"] is None
    assert body["reason"]


@respx.mock
def test_ask_unsupported_and_ambiguous_paths_never_query_recommendation_tables():
    """Proves the execution-plan stage genuinely short-circuits before
    retrieval -- no recommendation_products/legs/games call is even
    attempted for a rejected request. respx would fail this test if
    the endpoint tried to reach any unmocked table."""
    _mock_authenticated_user()

    response = _ask("what's the safest bet")

    assert response.status_code == 200


@respx.mock
def test_ask_only_selects_from_active_products_not_withdrawn():
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_games(
        today_ids=["game-1"],
        by_id={
            "game-1": {
                "id": "game-1",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T18:00:00Z",
                "status": "scheduled",
            }
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-withdrawn",
                    "display_id": "2026-00003",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "withdrawn",
                    "min_required_tier": "free",
                    "withdrawn_at": "2026-09-09T10:00:00Z",
                    "withdrawal_reason": "line moved",
                    "created_at": "2026-09-09T06:00:00Z",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_product_id": "prod-withdrawn",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.15,
                    "final_aggregate_confidence": 0.99,
                    "leg_order": 1,
                }
            ],
        )
    )
    _mock_empty_reads()

    response = _ask("highest confidence pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["result"] is None


# ---------------------------------------------------------------------------
# Phase 8.5 Pass 2 -- "highest value" (ev_per_dollar)
# ---------------------------------------------------------------------------


def _two_products_diverging_confidence_and_value() -> None:
    """Product A: higher confidence, lower EV. Product B: lower
    confidence, higher EV. Proves the two selection modes genuinely
    diverge -- neither is a proxy for the other."""
    _mock_games(
        today_ids=["game-a", "game-b"],
        by_id={
            "game-a": {
                "id": "game-a",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "status": "scheduled",
            },
            "game-b": {
                "id": "game-b",
                "home_team": "C",
                "away_team": "D",
                "scheduled_start": "2026-09-09T20:00:00Z",
                "status": "scheduled",
            },
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-high-confidence-low-value",
                    "display_id": "2026-00010",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-a",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
                {
                    "id": "prod-low-confidence-high-value",
                    "display_id": "2026-00011",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-b",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
            ],
        )
    )

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        if "prod-high-confidence-low-value" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-high-confidence-low-value",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.03,
                    "final_aggregate_confidence": 0.95,
                    "leg_order": 1,
                }
            )
        if "prod-low-confidence-high-value" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-low-confidence-high-value",
                    "market_type": "moneyline",
                    "selection": "D",
                    "sportsbook": "book",
                    "american_odds": 150,
                    "point": None,
                    "decimal_odds": 2.50,
                    "ev_per_dollar": 0.35,
                    "final_aggregate_confidence": 0.58,
                    "leg_order": 1,
                }
            )
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)
    _mock_empty_reads()


@respx.mock
def test_ask_returns_highest_value_pick():
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_diverging_confidence_and_value()

    response = _ask("What's MANSA's highest-value pick today?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == {
        "requestType": "recommendation_lookup",
        "selectionMode": "highest_value",
        "marketType": None,
        "timeScope": "today",
        "count": 1,
    }
    assert body["result"]["label"] == "MANSA's highest-value pick today"
    assert body["result"]["selectionMetric"] == "evPerDollar"
    assert "not a guarantee" in body["result"]["disclosure"].lower()
    recommendation = body["result"]["recommendation"]
    assert recommendation["displayId"] == "2026-00011"
    assert recommendation["legs"][0]["evPerDollar"] == 0.35
    assert body["results"] == [body["result"]]


@respx.mock
def test_ask_recognizes_equivalent_value_phrasing():
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_diverging_confidence_and_value()

    for phrase in ("what's the highest value?", "show me the best value pick today"):
        response = _ask(phrase)
        assert response.status_code == 200, phrase
        assert response.json()["intent"]["selectionMode"] == "highest_value", phrase
        assert response.json()["result"]["recommendation"]["displayId"] == "2026-00011", phrase


@respx.mock
def test_highest_value_and_highest_confidence_return_different_picks():
    """Direct proof the two selection modes are not proxies for each
    other, using the exact same underlying data."""
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_diverging_confidence_and_value()

    value_response = _ask("highest value pick today")
    confidence_response = _ask("highest confidence pick today")

    assert value_response.json()["result"]["recommendation"]["displayId"] == "2026-00011"
    assert confidence_response.json()["result"]["recommendation"]["displayId"] == "2026-00010"


@respx.mock
def test_ask_never_ranks_null_ev_as_zero():
    """A leg with a null evPerDollar must never be selected as if its
    value were 0 -- it must simply be skipped."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_games(
        today_ids=["game-1"],
        by_id={
            "game-1": {
                "id": "game-1",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T18:00:00Z",
                "status": "scheduled",
            }
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-null-ev",
                    "display_id": "2026-00012",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_product_id": "prod-null-ev",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": None,
                    "point": None,
                    "decimal_odds": None,
                    "ev_per_dollar": None,
                    "final_aggregate_confidence": 0.70,
                    "leg_order": 1,
                }
            ],
        )
    )
    _mock_empty_reads()

    response = _ask("highest value pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["result"] is None


@respx.mock
def test_ask_never_selects_a_non_positive_ev_leg_as_highest_value():
    """Defensive proof: a real but non-positive evPerDollar (which
    should never occur on an active leg per Strategy Engine's own
    qualification gate, but is defended against anyway) is never
    presented as MANSA's 'highest value' pick."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_games(
        today_ids=["game-1"],
        by_id={
            "game-1": {
                "id": "game-1",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T18:00:00Z",
                "status": "scheduled",
            }
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-negative-ev",
                    "display_id": "2026-00013",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_product_id": "prod-negative-ev",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": -0.04,
                    "final_aggregate_confidence": 0.70,
                    "leg_order": 1,
                }
            ],
        )
    )
    _mock_empty_reads()

    response = _ask("highest value pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["result"] is None


@respx.mock
def test_ask_best_pick_remains_unsupported_and_is_never_treated_as_highest_value():
    """HQ's explicit instruction: 'best pick' must never be treated as
    a synonym for 'highest value' (or highest confidence)."""
    _mock_authenticated_user()

    response = _ask("what's the best pick today?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert body["intent"]["selectionMode"] is None
    assert body["result"] is None


@respx.mock
def test_ask_best_value_pick_does_not_collide_with_best_pick_substring():
    """Substring-matching audit (HQ-required): 'best value pick today'
    must resolve to highest_value, not the 'best pick' unsupported
    branch -- proves the two phrase lists don't collide."""
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_diverging_confidence_and_value()

    response = _ask("show me the best value pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "recommendation_lookup"
    assert body["intent"]["selectionMode"] == "highest_value"


@respx.mock
def test_ask_highest_value_and_highest_confidence_phrases_do_not_collide():
    """Further substring-audit proof: the two supported phrase sets
    never both match the same input in a way that would make ordering
    in the resolver matter for realistic phrasing."""
    _mock_authenticated_user()
    _mock_no_runs()
    _two_products_diverging_confidence_and_value()

    confidence_response = _ask("what's MANSA's highest confidence pick today")
    value_response = _ask("what's MANSA's highest value pick today")

    assert confidence_response.json()["intent"]["selectionMode"] == "highest_confidence"
    assert value_response.json()["intent"]["selectionMode"] == "highest_value"


# ---------------------------------------------------------------------------
# Phase 8.5 Pass 3 -- market-specific filtering (moneyline/spread/total)
# ---------------------------------------------------------------------------


def _three_products_three_markets() -> None:
    """One active product per market, deliberately engineered so the
    moneyline product is globally strongest on BOTH metrics -- proves
    a market-specific request can never be won by a stronger
    recommendation from a different market (HQ test G)."""
    _mock_games(
        today_ids=["game-ml", "game-spread", "game-total"],
        by_id={
            "game-ml": {
                "id": "game-ml",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "status": "scheduled",
            },
            "game-spread": {
                "id": "game-spread",
                "home_team": "C",
                "away_team": "D",
                "scheduled_start": "2026-09-09T16:00:00Z",
                "status": "scheduled",
            },
            "game-total": {
                "id": "game-total",
                "home_team": "E",
                "away_team": "F",
                "scheduled_start": "2026-09-09T20:00:00Z",
                "status": "scheduled",
            },
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-moneyline",
                    "display_id": "2026-00020",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-ml",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
                {
                    "id": "prod-spread",
                    "display_id": "2026-00021",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-spread",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
                {
                    "id": "prod-total",
                    "display_id": "2026-00022",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-total",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
            ],
        )
    )

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        if "prod-moneyline" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-moneyline",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.50,
                    "final_aggregate_confidence": 0.99,
                    "leg_order": 1,
                }
            )
        if "prod-spread" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-spread",
                    "market_type": "spread",
                    "selection": "C -3.5",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": -3.5,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.10,
                    "final_aggregate_confidence": 0.65,
                    "leg_order": 1,
                }
            )
        if "prod-total" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-total",
                    "market_type": "total",
                    "selection": "Over 47.5",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": 47.5,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.08,
                    "final_aggregate_confidence": 0.60,
                    "leg_order": 1,
                }
            )
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)
    _mock_empty_reads()


@respx.mock
def test_ask_unfiltered_highest_confidence_behavior_is_unchanged():
    """Test A -- proves Pass 3 doesn't alter the unfiltered case: the
    globally strongest (moneyline) leg still wins with no market
    named."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("highest confidence pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] is None
    assert body["result"]["recommendation"]["displayId"] == "2026-00020"
    assert body["result"]["label"] == "MANSA's highest-confidence pick today"


@respx.mock
def test_ask_unfiltered_highest_value_behavior_is_unchanged():
    """Test B -- same proof for highest-value."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("highest value pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] is None
    assert body["result"]["recommendation"]["displayId"] == "2026-00020"
    assert body["result"]["label"] == "MANSA's highest-value pick today"


@respx.mock
def test_ask_highest_confidence_spread_filters_before_ranking():
    """Test C + G -- the globally-strongest moneyline leg (0.99
    confidence) must NOT win a spread-scoped request; the spread leg
    (0.65) must, even though it's weaker globally."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("what is MANSA's highest-confidence spread?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "spread"
    assert body["result"]["recommendation"]["displayId"] == "2026-00021"
    assert body["result"]["recommendation"]["legs"][0]["marketType"] == "spread"
    assert body["result"]["label"] == "MANSA's highest-confidence spread pick today"


@respx.mock
def test_ask_highest_value_spread_filters_before_ranking():
    """Test D + G -- same proof for highest-value."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("what's the highest-value spread?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "spread"
    assert body["result"]["recommendation"]["displayId"] == "2026-00021"
    assert body["result"]["label"] == "MANSA's highest-value spread pick today"


@respx.mock
def test_ask_highest_confidence_total_filters_before_ranking():
    """Test E + G."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("what's MANSA's highest-confidence total?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "total"
    assert body["result"]["recommendation"]["displayId"] == "2026-00022"


@respx.mock
def test_ask_highest_value_total_filters_before_ranking():
    """Test F + G."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("give me the best value total")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "total"
    assert body["result"]["recommendation"]["displayId"] == "2026-00022"


@respx.mock
def test_ask_highest_confidence_moneyline_filters_before_ranking():
    """Moneyline gate: the Pass 3 audit found moneyline equally clean
    as spread/total -- included, not deferred. Here moneyline happens
    to also be the global winner, so this proves the filter path is
    genuinely exercised (matches, not merely coincides)."""
    _mock_authenticated_user()
    _mock_no_runs()
    _three_products_three_markets()

    response = _ask("what's MANSA's highest confidence moneyline?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "moneyline"
    assert body["result"]["recommendation"]["displayId"] == "2026-00020"
    assert body["result"]["recommendation"]["legs"][0]["marketType"] == "moneyline"


@respx.mock
def test_ask_market_specific_request_with_no_qualifying_recommendation_is_honest():
    """Test H + I -- only a moneyline and a spread product exist today;
    a total-scoped request must return an honest no-result, NEVER
    falling back to the moneyline or spread product no matter how
    strong either is."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_games(
        today_ids=["game-ml", "game-spread"],
        by_id={
            "game-ml": {
                "id": "game-ml",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "status": "scheduled",
            },
            "game-spread": {
                "id": "game-spread",
                "home_team": "C",
                "away_team": "D",
                "scheduled_start": "2026-09-09T16:00:00Z",
                "status": "scheduled",
            },
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-moneyline",
                    "display_id": "2026-00023",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-ml",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
                {
                    "id": "prod-spread",
                    "display_id": "2026-00024",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-spread",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-09-09T06:00:00Z",
                },
            ],
        )
    )

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        if "prod-moneyline" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-moneyline",
                    "market_type": "moneyline",
                    "selection": "A",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.50,
                    "final_aggregate_confidence": 0.99,
                    "leg_order": 1,
                }
            )
        if "prod-spread" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-spread",
                    "market_type": "spread",
                    "selection": "C -3.5",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": -3.5,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.30,
                    "final_aggregate_confidence": 0.90,
                    "leg_order": 1,
                }
            )
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)
    _mock_empty_reads()

    response = _ask("what's MANSA's highest-confidence total?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "total"
    assert body["insufficientEvidence"] is True
    assert body["result"] is None
    assert "total" in body["reason"]


@respx.mock
def test_ask_unsupported_market_wording_does_not_silently_resolve():
    """Test J -- 'player prop' is a market-shaped word but not a
    supported market; it must resolve to UNSUPPORTED, never silently
    fall through to an unfiltered (or wrongly-filtered) result."""
    _mock_authenticated_user()

    response = _ask("what's MANSA's highest-confidence player prop?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert body["intent"]["selectionMode"] is None
    assert body["intent"]["marketType"] is None
    assert body["result"] is None
    assert "player prop" in body["reason"]


@respx.mock
def test_ask_existing_unsupported_phrases_remain_unsupported():
    """Test K -- Pass 1/2's own unsupported vocabulary is unaffected
    by the Pass 3 reordering (unsupported-check-first)."""
    _mock_authenticated_user()

    for phrase in ("what's the safest bet", "build me a parlay", "what's the best pick"):
        response = _ask(phrase)
        assert response.status_code == 200, phrase
        assert response.json()["intent"]["requestType"] == "unsupported", phrase


@respx.mock
def test_ask_market_filtered_request_requires_authentication():
    """Test L -- authentication behavior is unchanged for market-scoped
    requests."""
    response = client.post(
        "/v1/recommendations/ask", json={"question": "highest confidence spread today"}
    )
    assert response.status_code == 401


@respx.mock
def test_ask_market_filtered_unsupported_request_never_queries_recommendation_tables():
    """Tests M/N -- proves no provider/worker/recommendation-table call
    occurs for a rejected (unsupported-market) request: zero mocks are
    registered for recommendation_products/legs/games, so respx would
    fail this test if the endpoint tried to reach any of them."""
    _mock_authenticated_user()

    response = _ask("what's MANSA's highest-confidence player prop?")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Phase 8.5 Pass 4 -- Top-N retrieval
# ---------------------------------------------------------------------------


def _mock_products_and_legs(specs: list[dict]) -> None:
    """Generic Pass 4 fixture builder: each spec is
    `{id, display_id, game_id, scheduled_start, market_type,
    confidence, ev, [status], [point], [selection], [leg_order]}`.
    Replaces one bespoke fixture function per scenario (the Pass 1-3
    pattern) with a single reusable builder, since Pass 4's tests need
    many small variations (5 products, ties, mixed null/negative EV,
    mixed markets) that would otherwise duplicate the same
    games/products/legs mocking boilerplate a dozen times over. IDs
    must not be substrings of one another (`_legs_respond` matches by
    substring against the raw PostgREST `in.(...)` param, exactly as
    every prior fixture in this file already does)."""
    games_by_id: dict[str, dict] = {}
    game_ids: list[str] = []
    for spec in specs:
        gid = spec["game_id"]
        if gid not in games_by_id:
            games_by_id[gid] = {
                "id": gid,
                "home_team": f"{gid}-home",
                "away_team": f"{gid}-away",
                "scheduled_start": spec["scheduled_start"],
                "status": "scheduled",
            }
            game_ids.append(gid)
    _mock_games(today_ids=game_ids, by_id=games_by_id)

    products = [
        {
            "id": spec["id"],
            "display_id": spec["display_id"],
            "recommendation_type": "single",
            "scope": "game",
            "game_id": spec["game_id"],
            "status": spec.get("status", "active"),
            "min_required_tier": "free",
            "withdrawn_at": None,
            "withdrawal_reason": None,
            "created_at": "2026-09-09T06:00:00Z",
        }
        for spec in specs
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=products)
    )

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        for spec in specs:
            if spec["id"] in product_ids:
                legs.append(
                    {
                        "recommendation_product_id": spec["id"],
                        "market_type": spec["market_type"],
                        "selection": spec.get("selection", "A"),
                        "sportsbook": "book",
                        "american_odds": -110,
                        "point": spec.get("point"),
                        "decimal_odds": 1.91,
                        "ev_per_dollar": spec.get("ev"),
                        "final_aggregate_confidence": spec.get("confidence"),
                        "leg_order": spec.get("leg_order", 1),
                    }
                )
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)
    _mock_empty_reads()


def _five_moneyline_confidences() -> None:
    """Five active moneyline products, distinct confidences,
    deliberately NOT in chronological/creation order -- proves Top-N
    ranks by confidence, not by any neutral ordering. Test B/Q."""
    _mock_products_and_legs(
        [
            {
                "id": "prod-a1",
                "display_id": "2026-00101",
                "game_id": "game-a1",
                "scheduled_start": "2026-09-09T20:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.90,
                "ev": 0.10,
            },
            {
                "id": "prod-a2",
                "display_id": "2026-00102",
                "game_id": "game-a2",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.85,
                "ev": 0.30,
            },
            {
                "id": "prod-a3",
                "display_id": "2026-00103",
                "game_id": "game-a3",
                "scheduled_start": "2026-09-09T16:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.80,
                "ev": 0.20,
            },
            {
                "id": "prod-a4",
                "display_id": "2026-00104",
                "game_id": "game-a4",
                "scheduled_start": "2026-09-09T18:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.75,
                "ev": 0.05,
            },
            {
                "id": "prod-a5",
                "display_id": "2026-00105",
                "game_id": "game-a5",
                "scheduled_start": "2026-09-09T22:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.70,
                "ev": 0.01,
            },
        ]
    )


@respx.mock
def test_ask_count_defaults_to_one_result_unchanged():
    """Test A -- default count=1 leaves `result`/`results` byte-
    identical to Pass 1-3 single-pick behavior (already asserted in
    `test_ask_returns_highest_confidence_pick`; this re-proves it on
    the Pass 4 five-product fixture as an independent check)."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("highest confidence pick today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["count"] == 1
    assert len(body["results"]) == 1
    assert body["result"] == body["results"][0]
    assert body["result"]["recommendation"]["displayId"] == "2026-00101"


@respx.mock
def test_ask_top_3_highest_confidence_ordered_correctly():
    """Test B -- top 3 of 5 by confidence descending: 0.90, 0.85, 0.80."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("give me your top 3 highest-confidence picks")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["count"] == 3
    assert body["insufficientEvidence"] is False
    display_ids = [r["recommendation"]["displayId"] for r in body["results"]]
    assert display_ids == ["2026-00101", "2026-00102", "2026-00103"]
    assert body["result"] == body["results"][0]


@respx.mock
def test_ask_top_3_highest_value_ordered_correctly():
    """Test C -- top 3 of 5 by evPerDollar descending: 0.30, 0.20, 0.10
    -- proves the value ranking is genuinely independent of the
    confidence ranking proven above, using the same underlying data."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("give me your top 3 highest-value picks")

    assert response.status_code == 200
    body = response.json()
    display_ids = [r["recommendation"]["displayId"] for r in body["results"]]
    assert display_ids == ["2026-00102", "2026-00103", "2026-00101"]


@respx.mock
def test_ask_top_n_word_and_digit_forms_are_equivalent():
    """Test Q -- 'top three' and 'top 3' must produce identical
    results."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()
    digit_response = _ask("give me your top 3 highest-confidence picks")

    _mock_no_runs()
    _five_moneyline_confidences()
    word_response = _ask("give me your top three highest-confidence picks")

    digit_ids = [r["recommendation"]["displayId"] for r in digit_response.json()["results"]]
    word_ids = [r["recommendation"]["displayId"] for r in word_response.json()["results"]]
    assert digit_ids == word_ids == ["2026-00101", "2026-00102", "2026-00103"]


@respx.mock
def test_ask_market_scoped_top_3_filters_before_ranking_never_admits_stronger_other_market_leg():
    """Test D/E -- extends the Pass 3 fixture design: a globally-
    dominant moneyline leg (confidence 0.99) plus three spread legs and
    one total leg. A 'top 3 highest-confidence spread' request must
    return exactly the three spread legs, ranked among themselves --
    the far stronger moneyline leg must never enter the result no
    matter how strong, and the request must not fall back to filling
    the third slot from the total market either."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_products_and_legs(
        [
            {
                "id": "prod-b1",
                "display_id": "2026-00110",
                "game_id": "game-b1",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.99,
                "ev": 0.60,
            },
            {
                "id": "prod-b2",
                "display_id": "2026-00111",
                "game_id": "game-b2",
                "scheduled_start": "2026-09-09T14:00:00Z",
                "market_type": "spread",
                "confidence": 0.80,
                "ev": 0.10,
                "point": -3.5,
            },
            {
                "id": "prod-b3",
                "display_id": "2026-00112",
                "game_id": "game-b3",
                "scheduled_start": "2026-09-09T15:00:00Z",
                "market_type": "spread",
                "confidence": 0.75,
                "ev": 0.08,
                "point": -2.5,
            },
            {
                "id": "prod-b4",
                "display_id": "2026-00113",
                "game_id": "game-b4",
                "scheduled_start": "2026-09-09T16:00:00Z",
                "market_type": "spread",
                "confidence": 0.70,
                "ev": 0.06,
                "point": 1.5,
            },
            {
                "id": "prod-b5",
                "display_id": "2026-00114",
                "game_id": "game-b5",
                "scheduled_start": "2026-09-09T17:00:00Z",
                "market_type": "total",
                "confidence": 0.95,
                "ev": 0.50,
            },
        ]
    )

    response = _ask("what is MANSA's top 3 highest-confidence spread?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "spread"
    assert body["intent"]["count"] == 3
    display_ids = [r["recommendation"]["displayId"] for r in body["results"]]
    assert display_ids == ["2026-00111", "2026-00112", "2026-00113"]
    for r in body["results"]:
        assert r["recommendation"]["legs"][0]["marketType"] == "spread"


@respx.mock
def test_ask_fewer_than_n_returns_only_what_qualifies_never_fabricates_or_falls_back():
    """Test F/G -- only 2 legs are eligible (one null EV, one negative
    EV are correctly excluded by the existing defensive checks), but
    'top 5' is requested. Must return exactly those 2 -- never padded
    to 5, never falling back to a different market/metric to fill the
    gap. `insufficientEvidence` stays False because something real was
    found (smallest-consistent-behavior decision, Pass 4 ops doc)."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_products_and_legs(
        [
            {
                "id": "prod-c1",
                "display_id": "2026-00120",
                "game_id": "game-c1",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.80,
                "ev": 0.15,
            },
            {
                "id": "prod-c2",
                "display_id": "2026-00121",
                "game_id": "game-c2",
                "scheduled_start": "2026-09-09T14:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.75,
                "ev": 0.05,
            },
            {
                "id": "prod-c3",
                "display_id": "2026-00122",
                "game_id": "game-c3",
                "scheduled_start": "2026-09-09T15:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.70,
                "ev": None,
            },
            {
                "id": "prod-c4",
                "display_id": "2026-00123",
                "game_id": "game-c4",
                "scheduled_start": "2026-09-09T16:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.65,
                "ev": -0.02,
            },
        ]
    )

    response = _ask("give me your top 5 highest-value picks")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficientEvidence"] is False
    display_ids = [r["recommendation"]["displayId"] for r in body["results"]]
    assert display_ids == ["2026-00120", "2026-00121"]
    assert len(body["results"]) == 2


@respx.mock
def test_ask_market_scoped_top_n_with_zero_qualifying_is_honest_insufficient_evidence():
    """Test H/I (Pass 4 variant) -- 'top 3 highest-confidence total'
    with only moneyline/spread products today must return an honest
    empty result, never a fallback."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_products_and_legs(
        [
            {
                "id": "prod-d1",
                "display_id": "2026-00130",
                "game_id": "game-d1",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.90,
                "ev": 0.20,
            },
            {
                "id": "prod-d2",
                "display_id": "2026-00131",
                "game_id": "game-d2",
                "scheduled_start": "2026-09-09T14:00:00Z",
                "market_type": "spread",
                "confidence": 0.85,
                "ev": 0.15,
                "point": -1.5,
            },
        ]
    )

    response = _ask("give me the top 3 highest-confidence totals")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "total"
    assert body["insufficientEvidence"] is True
    assert body["result"] is None
    assert body["results"] == []


@respx.mock
def test_ask_over_max_count_is_rejected_honestly_never_silently_truncated():
    """Test J (over-max) -- 'top 6' exceeds the ceiling of 5. Must be
    rejected as UNSUPPORTED with an honest reason, and -- proven by
    zero recommendation_products/legs/games mocks being registered --
    must never attempt retrieval at all (a silently truncated top-5
    response would be dishonest about what was asked for)."""
    _mock_authenticated_user()

    response = _ask("give me your top 6 highest-confidence picks")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert body["result"] is None
    assert body["results"] is None
    assert "5" in body["reason"]


@respx.mock
def test_ask_over_max_word_count_is_rejected_honestly():
    _mock_authenticated_user()

    response = _ask("give me the top ten highest-value picks")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert "5" in body["reason"]


@respx.mock
def test_ask_bare_number_never_auto_resolves_a_count():
    """Test K -- 'give me 5' must NOT be treated as a count request;
    only an explicit 'top N' phrase does. This must still return
    exactly ONE result (Pass 1-3 default), not five."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("give me 5 highest confidence picks today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["count"] == 1
    assert len(body["results"]) == 1


@respx.mock
def test_ask_top_n_never_shadows_best_pick_unsupported_wording():
    """Test L -- 'best pick' stays UNSUPPORTED even alongside a 'top N'
    phrase; count changes must never weaken this terminology guardrail."""
    _mock_authenticated_user()

    response = _ask("give me the top 3 best picks today")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["requestType"] == "unsupported"
    assert body["result"] is None
    assert body["results"] is None


@respx.mock
def test_ask_top_n_existing_market_aliases_still_work():
    """Test M -- moneyline/spread/total aliases (Pass 3) still resolve
    correctly when combined with a Top-N count (Pass 4)."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("what's MANSA's top 2 highest confidence money line picks?")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["marketType"] == "moneyline"
    assert body["intent"]["count"] == 2
    assert len(body["results"]) == 2


@respx.mock
def test_ask_top_n_tied_values_produce_deterministic_ordering():
    """Test N (tiebreak, Pass 4 Step 6) -- two legs share the exact
    same confidence (0.85). Ordering must be deterministic via the
    displayId-ascending tiebreak (candidate_key is not available on
    this serialized data -- see the Pass 4 ops doc / `_rank_and_limit`
    docstring), regardless of the order the underlying rows arrive in.
    Products are constructed with the HIGHER displayId listed FIRST in
    the fixture, to prove the tiebreak isn't just preserving input
    order by accident."""
    _mock_authenticated_user()
    _mock_no_runs()
    _mock_products_and_legs(
        [
            {
                "id": "prod-e2",
                "display_id": "2026-00202",
                "game_id": "game-e2",
                "scheduled_start": "2026-09-09T14:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.85,
                "ev": 0.10,
            },
            {
                "id": "prod-e1",
                "display_id": "2026-00201",
                "game_id": "game-e1",
                "scheduled_start": "2026-09-09T13:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.85,
                "ev": 0.20,
            },
            {
                "id": "prod-e3",
                "display_id": "2026-00203",
                "game_id": "game-e3",
                "scheduled_start": "2026-09-09T15:00:00Z",
                "market_type": "moneyline",
                "confidence": 0.60,
                "ev": 0.05,
            },
        ]
    )

    response = _ask("give me your top 2 highest-confidence picks")

    assert response.status_code == 200
    display_ids = [r["recommendation"]["displayId"] for r in response.json()["results"]]
    assert display_ids == ["2026-00201", "2026-00202"]


@respx.mock
def test_ask_top_n_requires_authentication():
    """Test O -- auth behavior is unchanged for a Top-N request."""
    response = client.post(
        "/v1/recommendations/ask", json={"question": "top 3 highest confidence picks"}
    )
    assert response.status_code == 401


@respx.mock
def test_ask_top_n_never_queries_any_unmocked_host():
    """Test P -- proves no provider/worker/recomputation call occurs
    for a real, successful Top-N request: only the mocks this test
    itself registers (auth, games, products, legs, and the three
    empty-read tables) are ever contacted -- respx fails on any
    unmatched request, so this test's mere success is the proof."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("top 3 highest confidence picks")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 3


@respx.mock
def test_ask_top_n_result_always_equals_first_results_entry():
    """Test S -- for every count, `result` stays exactly `results[0]`
    (the backward-compatible singular field), never diverging."""
    _mock_authenticated_user()
    _mock_no_runs()
    _five_moneyline_confidences()

    response = _ask("give me your top 4 highest-confidence picks")

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 4
    assert body["result"] == body["results"][0]
