"""Tests for /v1/recommendations/* (Phase 6 Milestone 2). Follows this
repo's established respx-at-the-HTTP-boundary convention (see
test_onboarding.py) -- auth is exercised for real, not dependency-
overridden."""
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
        "recommendation_legs",
        "recommendation_product_explanations",
        "master_refresh_runs",
    ):
        respx.get(f"{SUPABASE_URL}/rest/v1/{table}").mock(return_value=httpx.Response(200, json=[]))


def _mock_games(*, today_ids: list[str], by_id: dict[str, dict] | None = None) -> None:
    """`games` is queried two different ways in one request -- a
    date-range filter for "today's game ids", then an id-list filter
    for full game details. A static respx `.mock()` can't distinguish
    them (it answers every call to the URL identically), so this uses a
    `side_effect` that reads the actual query params, matching real
    PostgREST usage rather than a single scripted response."""
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


@respx.mock
def test_today_requires_authentication():
    response = client.get("/v1/recommendations/today")
    assert response.status_code == 401


@respx.mock
def test_today_returns_empty_list_when_no_games_or_runs_scheduled_today():
    _mock_authenticated_user()
    _mock_games(today_ids=[])
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json() == []


@respx.mock
def test_no_bet_product_survives_serialization():
    _mock_authenticated_user()
    _mock_games(
        today_ids=["game-1"],
        by_id={
            "game-1": {
                "id": "game-1",
                "home_team": "Chiefs",
                "away_team": "Bills",
                "scheduled_start": "2026-08-28T18:00:00Z",
                "status": "scheduled",
            }
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-nobet",
                    "display_id": "2026-00001",
                    "recommendation_type": "no_bet",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:00:00Z",
                }
            ],
        )
    )
    _mock_empty_reads()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(
            200, json=[{"recommendation_product_id": "prod-nobet", "why_this_shape": "no candidate qualified"}]
        )
    )

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == 1
    assert cards[0]["recommendationType"] == "no_bet"
    assert cards[0]["legs"] == []
    assert cards[0]["oneLineSummary"] == "no candidate qualified"
    assert cards[0]["game"]["homeTeam"] == "Chiefs"


@respx.mock
def test_bankroll_preservation_product_survives_serialization():
    _mock_authenticated_user()
    _mock_games(today_ids=[])
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-bp",
                    "display_id": "2026-00002",
                    "recommendation_type": "bankroll_preservation",
                    "scope": "slate",
                    "game_id": None,
                    "master_refresh_run_id": "run-1",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:05:00Z",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(
            200, json=[{"recommendation_product_id": "prod-bp", "activated_at": "2026-08-28T06:05:30Z"}]
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recommendation_product_id": "prod-bp",
                    "why_this_shape": "today's slate doesn't offer a favorable risk/reward setup",
                }
            ],
        )
    )

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == 1
    assert cards[0]["recommendationType"] == "bankroll_preservation"
    assert cards[0]["scope"] == "slate"
    assert cards[0]["game"] is None
    # Neutral ordering fallback: no game_id, so decidedAt (activation
    # time) is what orders it -- and is exposed, distinctly from any
    # source-freshness concept (no "updatedAt"/"lastRefreshed" key
    # exists anywhere in this contract).
    assert cards[0]["decidedAt"] == "2026-08-28T06:05:30Z"
    assert "updatedAt" not in cards[0]
    assert "lastRefreshed" not in cards[0]


@respx.mock
def test_withdrawn_product_serializes_withdrawal_fields():
    _mock_authenticated_user()
    _mock_games(today_ids=["game-1"])
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
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
                    "withdrawn_at": "2026-08-28T10:00:00Z",
                    "withdrawal_reason": "line moved past invalidation threshold",
                    "created_at": "2026-08-28T06:00:00Z",
                }
            ],
        )
    )
    _mock_empty_reads()

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    card = response.json()[0]
    assert card["status"] == "withdrawn"
    assert card["withdrawnAt"] == "2026-08-28T10:00:00Z"
    assert card["withdrawalReason"] == "line moved past invalidation threshold"


@respx.mock
def test_tier_gated_product_hidden_from_free_user():
    _mock_authenticated_user(tier=None)
    _mock_games(today_ids=["game-1"])
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-elite",
                    "display_id": "2026-00004",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "active",
                    "min_required_tier": "elite",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:00:00Z",
                }
            ],
        )
    )

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert response.json() == []


@respx.mock
def test_tier_gated_product_visible_to_elite_subscriber():
    _mock_authenticated_user(tier="elite")
    _mock_games(
        today_ids=["game-1"],
        by_id={
            "game-1": {
                "id": "game-1",
                "home_team": "A",
                "away_team": "B",
                "scheduled_start": "2026-08-28T18:00:00Z",
                "status": "scheduled",
            }
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-elite",
                    "display_id": "2026-00004",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-1",
                    "status": "active",
                    "min_required_tier": "elite",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:00:00Z",
                }
            ],
        )
    )
    _mock_empty_reads()

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    assert len(response.json()) == 1


@respx.mock
def test_neutral_ordering_uses_game_start_time_not_confidence_or_ev():
    """The lower-EV, lower-confidence game (kicking off first) must
    come first -- proves ordering is chronological, never a business
    ranking."""
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(return_value=httpx.Response(200, json=[]))
    _mock_games(
        today_ids=["game-early", "game-late"],
        by_id={
            "game-early": {
                "id": "game-early",
                "home_team": "C",
                "away_team": "D",
                "scheduled_start": "2026-08-28T13:00:00Z",
                "status": "scheduled",
            },
            "game-late": {
                "id": "game-late",
                "home_team": "E",
                "away_team": "F",
                "scheduled_start": "2026-08-28T20:00:00Z",
                "status": "scheduled",
            },
        },
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "prod-high-ev",
                    "display_id": "2026-00005",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-late",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:00:00Z",
                },
                {
                    "id": "prod-low-ev",
                    "display_id": "2026-00006",
                    "recommendation_type": "single",
                    "scope": "game",
                    "game_id": "game-early",
                    "status": "active",
                    "min_required_tier": "free",
                    "withdrawn_at": None,
                    "withdrawal_reason": None,
                    "created_at": "2026-08-28T06:00:00Z",
                },
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(return_value=httpx.Response(200, json=[]))

    def _legs_respond(request: httpx.Request) -> httpx.Response:
        product_ids = request.url.params.get("recommendation_product_id", "")
        legs = []
        if "prod-high-ev" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-high-ev",
                    "market_type": "moneyline",
                    "selection": "E",
                    "sportsbook": "book",
                    "american_odds": -110,
                    "point": None,
                    "decimal_odds": 1.91,
                    "ev_per_dollar": 0.20,
                    "final_aggregate_confidence": 0.90,
                    "leg_order": 1,
                }
            )
        if "prod-low-ev" in product_ids:
            legs.append(
                {
                    "recommendation_product_id": "prod-low-ev",
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
        return httpx.Response(200, json=legs)

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_legs_respond)

    response = client.get("/v1/recommendations/today", headers={"Authorization": "Bearer validtoken"})

    assert response.status_code == 200
    cards = response.json()
    assert [c["displayId"] for c in cards] == ["2026-00006", "2026-00005"]


@respx.mock
def test_reconstruction_returns_404_for_unknown_display_id():
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))

    response = client.get(
        "/v1/recommendations/nonexistent/reconstruction", headers={"Authorization": "Bearer validtoken"}
    )

    assert response.status_code == 404


@respx.mock
def test_reconstruction_hides_tier_gated_product_as_404_not_403():
    """HQ Final Decision 9 -- never a distinguishable "this exists but
    you can't see it" signal."""
    _mock_authenticated_user(tier=None)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200, json=[{"id": "prod-1", "display_id": "2026-00007", "min_required_tier": "elite"}]
        )
    )

    response = client.get(
        "/v1/recommendations/2026-00007/reconstruction", headers={"Authorization": "Bearer validtoken"}
    )

    assert response.status_code == 404


@respx.mock
def test_reconstruction_proxies_ai_orchestrator_reconstruction_verbatim(monkeypatch):
    """Confirms the one route that reuses Milestone 5.3's reconstruction
    (rather than rebuilding history) actually calls it and returns its
    shape unmodified -- not just the two short-circuit 404 cases above."""
    monkeypatch.setenv("AI_ORCHESTRATOR_URL", "http://ai-orchestrator.railway.internal:8080")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "internal-token")
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200, json=[{"id": "prod-1", "display_id": "2026-00008", "min_required_tier": "free"}]
        )
    )
    reconstruction_route = respx.get("http://ai-orchestrator.railway.internal:8080/v1/internal/reconstruction/prod-1").mock(
        return_value=httpx.Response(200, json={"strategy_version": "v1", "legs": []})
    )

    response = client.get(
        "/v1/recommendations/2026-00008/reconstruction", headers={"Authorization": "Bearer validtoken"}
    )

    assert response.status_code == 200
    assert response.json() == {"strategy_version": "v1", "legs": []}
    assert reconstruction_route.calls.last.request.headers["X-Internal-Token"] == "internal-token"


@respx.mock
def test_reconstruction_returns_502_when_ai_orchestrator_unreachable(monkeypatch):
    monkeypatch.setenv("AI_ORCHESTRATOR_URL", "http://ai-orchestrator.railway.internal:8080")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "internal-token")
    _mock_authenticated_user()
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(
            200, json=[{"id": "prod-1", "display_id": "2026-00009", "min_required_tier": "free"}]
        )
    )
    respx.get("http://ai-orchestrator.railway.internal:8080/v1/internal/reconstruction/prod-1").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    response = client.get(
        "/v1/recommendations/2026-00009/reconstruction", headers={"Authorization": "Bearer validtoken"}
    )

    assert response.status_code == 502
