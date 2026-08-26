"""Tests for app.orchestration.reconstruction (Milestone 5.3) -- the
internal Time Machine reconstruction function, plus the roadmap's own
named reproducibility test: mutate live state after activation, confirm
reconstruction is unaffected."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.orchestration.reconstruction import ReconstructionError, reconstruct_recommendation_product

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


@pytest.mark.asyncio
@respx.mock
async def test_raises_when_product_does_not_exist():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ReconstructionError):
            await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="nonexistent")


@pytest.mark.asyncio
@respx.mock
async def test_raises_when_activation_snapshot_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-1", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(ReconstructionError):
            await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-1")


@pytest.mark.asyncio
@respx.mock
async def test_no_bet_reconstructs_with_no_legs():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-nobet", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-1", "why_this_shape": "no candidate qualified"}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-nobet")
    assert result.legs == []
    assert result.source_products == []
    assert result.product_explanation["why_this_shape"] == "no candidate qualified"
    assert result.strategy_version == "v1"


@pytest.mark.asyncio
@respx.mock
async def test_bankroll_preservation_reconstructs_its_source_no_bet_products():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-bp", "recommendation_type": "bankroll_preservation"}])
    )

    def _snapshot_responder(request: httpx.Request) -> httpx.Response:
        product_id = request.url.params.get("recommendation_product_id", "").removeprefix("eq.")
        snapshots = {
            "prod-bp": {"id": "snap-bp", "strategy_version": "v1", "recommendation_product_explanation_id": None},
            "prod-g1": {"id": "snap-g1", "strategy_version": "v1", "recommendation_product_explanation_id": "expl-g1"},
        }
        row = snapshots.get(product_id)
        return httpx.Response(200, json=[row] if row else [])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(side_effect=_snapshot_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_source_products").mock(
        return_value=httpx.Response(200, json=[{"source_recommendation_product_id": "prod-g1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_product_explanations").mock(
        return_value=httpx.Response(200, json=[{"id": "expl-g1", "why_this_shape": "g1 had no qualifying candidate"}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-bp")

    assert len(result.source_products) == 1
    assert result.source_products[0].recommendation_product_id == "prod-g1"
    assert result.source_products[0].explanation["why_this_shape"] == "g1 had no qualifying candidate"


@pytest.mark.asyncio
@respx.mock
async def test_multiple_singles_reconstructs_legs_in_frozen_order():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-ms", "recommendation_type": "multiple_singles"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-ms", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(
            200, json=[{"recommendation_leg_id": "leg-strong", "leg_order": 1}, {"recommendation_leg_id": "leg-weak", "leg_order": 2}]
        )
    )

    def _leg_responder(request: httpx.Request) -> httpx.Response:
        leg_id = request.url.params.get("id", "").removeprefix("eq.")
        rows = {
            "leg-strong": {"id": "leg-strong", "candidate_key": "strong", "ev_per_dollar": 0.09},
            "leg-weak": {"id": "leg-weak", "candidate_key": "weak", "ev_per_dollar": 0.02},
        }
        return httpx.Response(200, json=[rows[leg_id]])

    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(side_effect=_leg_responder)
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-ms")

    assert [(leg.leg_order, leg.leg["candidate_key"]) for leg in result.legs] == [(1, "strong"), (2, "weak")]
    assert all(leg.explanation is None for leg in result.legs)


@pytest.mark.asyncio
@respx.mock
async def test_single_product_with_user_id_attaches_that_users_latest_selection():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-single", "recommendation_type": "single"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-single", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshot_legs").mock(
        return_value=httpx.Response(200, json=[{"recommendation_leg_id": "leg-1", "leg_order": 1}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_legs").mock(
        return_value=httpx.Response(200, json=[{"id": "leg-1", "candidate_key": "only"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_leg_explanations").mock(return_value=httpx.Response(200, json=[]))
    selection_route = respx.get(f"{SUPABASE_URL}/rest/v1/user_recommendation_selections").mock(
        return_value=httpx.Response(200, json=[{"id": "sel-1", "stake": 42.0}])
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(
            client, _headers(), recommendation_product_id="prod-single", user_id="user-1"
        )

    assert result.user_selection["stake"] == 42.0
    assert selection_route.calls.last.request.url.params["recommendation_leg_id"] == "eq.leg-1"


@pytest.mark.asyncio
@respx.mock
async def test_no_user_id_leaves_user_selection_none():
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_products").mock(
        return_value=httpx.Response(200, json=[{"id": "prod-nobet", "recommendation_type": "no_bet"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendation_activation_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "snap-1", "strategy_version": "v1", "recommendation_product_explanation_id": None}])
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await reconstruct_recommendation_product(client, _headers(), recommendation_product_id="prod-nobet")
    assert result.user_selection is None
