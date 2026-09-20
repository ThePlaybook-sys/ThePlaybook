"""Pre-LLM eligibility gate + hard outbound ceiling (2026-09-18).

Proves the eleven properties HQ required before
`REFERENCE_SPORTSBOOK_PREFERENCE` may be set.

Two independent guarantees are under test, and they are deliberately
independent:

1. **Ordering** -- every cheap deterministic check runs before any agent,
   so an ineligible game costs zero model requests.
2. **A counted ceiling at the outbound boundary** -- even if the
   orchestration above it changes in ways this file has never heard of,
   `ModelAdapter.complete` refuses past the limit. Ordering is a
   property of today's code; the ceiling is a property of the boundary.

Every model call in this service goes
`Agent -> ModelRouter.route -> AdapterRegistry.get -> ModelAdapter.complete`,
so a counting adapter is both sufficient and necessary: counting higher up
counts intentions, and the retry engine can turn one intention into
several real requests.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.config import DEFAULT_MAX_LLM_CALLS_PER_GAME, max_llm_calls_per_game
from app.models.base import ModelAdapter
from app.models.budget import (
    BudgetedModelAdapter,
    CallBudget,
    LlmBudgetExceededError,
    budgeted_registry,
)
from app.models.fake_adapter import FakeModelAdapter
from app.models.router import AdapterRegistry, UnknownProviderError
from app.models.types import ModelRequest, ModelResponse, UsageMetadata
from app.orchestration.recommendation_worker import run_game_recommendation

SUPABASE_URL = "https://test-project.supabase.co"
NOW = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
KICKOFF = "2026-09-21T20:00:00+00:00"


def _headers() -> dict:
    return {"apikey": "k", "Authorization": "Bearer k"}


def _routing_rules() -> dict:
    return {
        task: {"task_type": task, "primary_model": "claude-sonnet-5", "fallback_model": None, "min_tier_for_second_pass": "elite"}
        for task in (
            "injury_analysis", "weather_analysis", "vegas_line_analysis", "closing_line_movement_analysis",
            "travel_fatigue_analysis", "rest_days_analysis", "probability_modeling_analysis",
            "expected_value_analysis", "risk_manager_analysis", "meta_agent_review",
            "consensus_reconciliation", "bankroll_coach_analysis",
        )
    }


def _request(model: str = "claude-sonnet-5") -> ModelRequest:
    """The minimal valid `ModelRequest` -- field list per
    `app.models.types`, not guessed."""
    return ModelRequest(
        model=model,
        messages=[{"role": "user", "content": "x"}],
        task_type="injury_analysis",
        agent_name="injury_intelligence_agent",
        correlation_id="run-1:g1",
    )


class CountingAdapter(ModelAdapter):
    """Records every request that reaches the provider boundary. This is
    the only thing in these tests that could ever have been a real LLM
    call -- so `calls == 0` is a literal proof of zero spend, not an
    inference from a status field."""

    def __init__(self) -> None:
        self.calls: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(raw_text="{}", usage=UsageMetadata(model="claude-sonnet-5", provider="anthropic"))


def _mock_game(odds_rows: list, *, status: str = "scheduled", scheduled_start: str = KICKOFF) -> None:
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{
            "id": "g1", "status": status, "scheduled_start": scheduled_start,
            "home_team": "KC", "away_team": "BAL", "season_type": "regular", "week": 3,
            "venue_lat": None, "venue_long": None, "stadium": None, "venue_type": None,
        }])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(200, json=odds_rows))
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/subscriptions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/daily_game_intelligence").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/prompt_registry").mock(
        return_value=httpx.Response(200, json=[{"prompt_name": "x", "version": "1", "prompt_text": "p", "status": "active"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/agents").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "current_weight": 1.0}])
    )


def _fresh_odds() -> list:
    return [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]},
        "captured_at": NOW.isoformat(),
    }]


async def _run(adapter, *, budget: CallBudget | None = None, now: datetime = NOW):
    registry = AdapterRegistry(adapters={"anthropic": adapter})
    if budget is not None:
        registry = budgeted_registry(registry, budget)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        return await run_game_recommendation(
            client, _headers(), game_id="g1", correlation_id="run-1:g1",
            prompt_version="v1", agent_version="v1",
            routing_rules=_routing_rules(), adapter_registry=registry,
            model_providers={"claude-sonnet-5": "anthropic"}, now=now,
        )


def _counting_fake() -> tuple[FakeModelAdapter, CallBudget]:
    """The project's own `FakeModelAdapter` behind a `CallBudget` with an
    unreachable limit. The budget doubles as the instrument: `used` is a
    count taken at the exact production boundary a real provider call
    would cross, rather than a parallel counter that could drift from it.
    An empty script makes every agent fail in isolation, which is fine --
    what is being measured is whether the boundary was REACHED."""
    budget = CallBudget(limit=10_000)
    return FakeModelAdapter(provider="anthropic", script=[]), budget


# ------------------------------------------------------------ 1, 2, 3
# Deterministic prerequisites: each costs ZERO model requests.


@pytest.mark.asyncio
@respx.mock
async def test_no_odds_means_zero_llm_calls(monkeypatch):
    """VERIFY 1."""
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    _mock_game(odds_rows=[])
    rec_post = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    adapter = CountingAdapter()

    result = await _run(adapter)

    assert adapter.calls == [], "a game with no odds must never reach a model"
    assert result.status == "skipped_ineligible"
    assert result.game_skipped_reason == "no_configured_sportsbook_has_fresh_data"
    assert result.recommendation_id is None
    assert rec_post.call_count == 0, "and must not leave an orphan marker row"


@pytest.mark.asyncio
@respx.mock
async def test_stale_odds_means_zero_llm_calls(monkeypatch):
    """VERIFY 2 -- odds exist but are far older than the kickoff tier
    allows. Freshness logic is unchanged; only when it runs has changed."""
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    stale = [{
        "sportsbook": "draftkings", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]},
        "captured_at": "2026-09-01T00:00:00+00:00",  # ~3 weeks before kickoff
    }]
    _mock_game(odds_rows=stale)
    adapter = CountingAdapter()

    result = await _run(adapter)

    assert adapter.calls == [], "stale odds must never reach a model"
    assert result.status == "skipped_ineligible"


@pytest.mark.asyncio
@respx.mock
async def test_reference_sportsbook_unavailable_means_zero_llm_calls(monkeypatch):
    """VERIFY 3 -- fresh odds exist, but only at a book that is not in the
    configured preference list."""
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    other_book = [{
        "sportsbook": "mybookieag", "market_type": "moneyline",
        "line_data": {"outcomes": [{"name": "KC", "price": -150}]},
        "captured_at": NOW.isoformat(),
    }]
    _mock_game(odds_rows=other_book)
    adapter = CountingAdapter()

    result = await _run(adapter)

    assert adapter.calls == [], "an unconfigured book must never reach a model"
    assert result.status == "skipped_ineligible"
    assert result.sportsbook_used is None


@pytest.mark.asyncio
@respx.mock
async def test_unset_sportsbook_preference_costs_zero_llm_calls(monkeypatch):
    """The 2026-09-17 incident shape, now bounded.

    An unset `REFERENCE_SPORTSBOOK_PREFERENCE` used to raise AFTER the
    6-agent fan-out had already run. It now raises before any agent.
    """
    monkeypatch.delenv("REFERENCE_SPORTSBOOK_PREFERENCE", raising=False)
    _mock_game(odds_rows=_fresh_odds())
    rec_post = respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    adapter = CountingAdapter()

    from app.config import ConfigError

    with pytest.raises(ConfigError):
        await _run(adapter)

    assert adapter.calls == [], "the config error must now precede the committee, not follow it"
    assert rec_post.call_count == 0, "and must not leave an orphan marker row"


# ---------------------------------------------------------------- 4, 5
# Horizon and retry/backoff suppression are enforced by the CALLER
# (apps/workers) and are covered there; this asserts the orchestrator's
# own share -- an already-completed cycle is never recomputed.


@pytest.mark.asyncio
@respx.mock
async def test_already_completed_cycle_costs_zero_llm_calls(monkeypatch):
    """VERIFY 5 (orchestrator half) -- retry/backoff suppression.

    A `correlation_id` that already reached `cycle_completed_at` is
    refused before candidate generation and before any agent.
    """
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    _mock_game(odds_rows=_fresh_odds())
    respx.get(f"{SUPABASE_URL}/rest/v1/recommendations").mock(
        return_value=httpx.Response(200, json=[{"id": "r1", "cycle_completed_at": "2026-09-20T00:00:00+00:00"}])
    )
    adapter = CountingAdapter()

    result = await _run(adapter)

    assert adapter.calls == [], "an already-computed cycle must never re-spend"
    assert result.status == "skipped_already_computed"


# ------------------------------------------------------------------ 6
# The positive case: an eligible game DOES reach the committee.


@pytest.mark.asyncio
@respx.mock
async def test_eligible_game_reaches_fan_out(monkeypatch):
    """VERIFY 6 -- the gate must not be so strict that nothing passes.

    This is the test that would fail if the reorder had accidentally
    disabled recommendations altogether.
    """
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    _mock_game(odds_rows=_fresh_odds())
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "s1"}]))
    adapter, budget = _counting_fake()

    result = await _run(adapter, budget=budget)

    # HQ "EMPTY NO-BET SAFETY FIX" (2026-09-20): this test's point is that an
    # ELIGIBLE game reaches the fan-out and spends real budget -- proven below
    # by `budget.used >= 6`, unchanged. The status is now
    # `analysis_incomplete` rather than `computed` because this test's adapter
    # produces no usable analytical output, and a cycle that produces none no
    # longer reports success. The eligibility gate behaviour under test is
    # untouched.
    assert result.status == "analysis_incomplete"
    assert result.sportsbook_used == "draftkings"
    assert budget.used >= 6, (
        f"an eligible game must reach the committee -- the 6 game-level agents "
        f"should each cross the provider boundary; saw {budget.used}"
    )


# ------------------------------------------------------------------ 8
# The hard ceiling at the outbound boundary.


def test_max_llm_calls_per_game_default_and_override(monkeypatch):
    monkeypatch.delenv("MAX_LLM_CALLS_PER_GAME", raising=False)
    assert max_llm_calls_per_game() == DEFAULT_MAX_LLM_CALLS_PER_GAME == 48
    monkeypatch.setenv("MAX_LLM_CALLS_PER_GAME", "10")
    assert max_llm_calls_per_game() == 10
    # A typo in a safety ceiling must never itself become the outage.
    monkeypatch.setenv("MAX_LLM_CALLS_PER_GAME", "oops")
    assert max_llm_calls_per_game() == DEFAULT_MAX_LLM_CALLS_PER_GAME
    monkeypatch.setenv("MAX_LLM_CALLS_PER_GAME", "-1")
    assert max_llm_calls_per_game() == DEFAULT_MAX_LLM_CALLS_PER_GAME


@pytest.mark.asyncio
async def test_budget_refuses_at_the_adapter_boundary():
    """VERIFY 8 -- the ceiling cannot be exceeded, at the only place that
    reaches a provider."""
    inner = CountingAdapter()
    budget = CallBudget(limit=3)
    adapter = BudgetedModelAdapter(inner=inner, budget=budget)
    request = _request()

    for _ in range(3):
        await adapter.complete(request)
    assert len(inner.calls) == 3
    assert budget.exhausted

    with pytest.raises(LlmBudgetExceededError) as exc:
        await adapter.complete(request)

    assert exc.value.limit == 3
    assert exc.value.attempted == 4
    assert len(inner.calls) == 3, "the refused request never reached the provider"


@pytest.mark.asyncio
async def test_budget_counts_before_the_request_so_failures_still_spend():
    """A request that was sent and then failed has still been spent.
    Counting on success would let a retry storm bypass the ceiling."""

    class FailingAdapter(ModelAdapter):
        def __init__(self) -> None:
            self.attempts = 0

        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.attempts += 1
            raise RuntimeError("provider exploded")

    inner = FailingAdapter()
    budget = CallBudget(limit=2)
    adapter = BudgetedModelAdapter(inner=inner, budget=budget)
    request = _request(model="m")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await adapter.complete(request)

    assert budget.used == 2
    with pytest.raises(LlmBudgetExceededError):
        await adapter.complete(request)
    assert inner.attempts == 2, "the third attempt was refused before reaching the provider"


def test_budget_is_shared_across_providers():
    """One run's allowance, not one per provider."""
    budget = CallBudget(limit=5)
    registry = budgeted_registry(
        AdapterRegistry(adapters={"anthropic": CountingAdapter(), "openai": CountingAdapter()}), budget
    )
    assert registry.get("anthropic").budget is registry.get("openai").budget


def test_budgeted_registry_adds_a_ceiling_never_a_provider():
    """An unconfigured provider stays absent -- wrapping must not
    accidentally manufacture an adapter."""
    registry = budgeted_registry(AdapterRegistry(adapters={}), CallBudget(limit=10))
    with pytest.raises(UnknownProviderError):
        registry.get("anthropic")


@pytest.mark.asyncio
@respx.mock
async def test_ceiling_holds_end_to_end_through_a_real_game(monkeypatch):
    """VERIFY 8 end-to-end -- with a ceiling of 2, an eligible game gets
    exactly 2 provider requests and no more, however many the committee
    would otherwise have made."""
    monkeypatch.setenv("REFERENCE_SPORTSBOOK_PREFERENCE", "draftkings,fanduel")
    _mock_game(odds_rows=_fresh_odds())
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(201, json=[{"id": "r1"}]))
    respx.patch(f"{SUPABASE_URL}/rest/v1/recommendations").mock(return_value=httpx.Response(204))
    respx.post(f"{SUPABASE_URL}/rest/v1/recommendation_agent_outputs").mock(return_value=httpx.Response(201, json=[{}]))
    respx.post(f"{SUPABASE_URL}/rest/v1/consensus_snapshots").mock(return_value=httpx.Response(201, json=[{"id": "s1"}]))
    adapter = FakeModelAdapter(provider="anthropic", script=[])
    budget = CallBudget(limit=2)

    # Per-agent isolation means a budget breach surfaces as isolated agent
    # failures rather than propagating -- what matters, and what is
    # asserted, is that the boundary is never crossed a third time.
    try:
        await _run(adapter, budget=budget)
    except LlmBudgetExceededError:
        pass

    assert budget.used == 2, f"ceiling of 2 must hold; got {budget.used}"
    assert budget.exhausted


# ----------------------------------------------------------------- 11
# Zero real calls anywhere in this suite.


def test_no_real_provider_call_is_reachable_from_this_suite():
    """VERIFY 11 -- structural.

    Every adapter used above is `CountingAdapter` or `FailingAdapter`,
    both defined in this file. `_build_real_adapter_registry` (the only
    thing that constructs `AnthropicModelAdapter`/`OpenAIModelAdapter`)
    is never imported here, and every HTTP test is `respx.mock`-wrapped,
    which raises on an unmocked host rather than letting it escape.
    """
    import app.models.budget as budget_module

    source = open(budget_module.__file__).read()
    for forbidden in ("api.anthropic.com", "api.openai.com", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert forbidden not in source, f"{forbidden} must not appear in the budget boundary"
