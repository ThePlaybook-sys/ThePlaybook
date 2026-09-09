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
        "timeScope": "today",
    }
    assert body["insufficientEvidence"] is False
    assert body["reason"] is None
    assert body["result"]["label"] == "MANSA's highest-confidence pick today"
    assert body["result"]["confidenceMetric"] == "finalAggregateConfidence"
    assert "not a guarantee" in body["result"]["disclosure"].lower()
    recommendation = body["result"]["recommendation"]
    assert recommendation["displayId"] == "2026-00002"
    assert recommendation["legs"][0]["finalAggregateConfidence"] == 0.91


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
