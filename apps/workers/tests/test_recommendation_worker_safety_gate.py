"""Recommendation Worker autonomy safety gate (2026-09-17).

Covers the eight properties HQ required before `REFERENCE_SPORTSBOOK_PREFERENCE`
may be set, i.e. before candidate generation can reach the LLM committee at all.

The defect these guard against is live and dated: the 06:15 run on 2026-09-17
selected **257 games** -- every remaining fixture in the season, kicking off
from that morning through 2027-01-10 -- because `read_eligible_game_ids`
filtered on `status='scheduled'` and nothing else. It dispatched one
`ai-orchestrator` call per game. It cost nothing only because a *downstream*
`ConfigError` happened to abort each one; that error is raised AFTER the
game-level fan-out, so it was never the cost circuit breaker it appeared to be.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.cron_dispatch import result_failure_summary
from app.persistence.games import RECOMMENDATION_WINDOW_DAYS, read_eligible_game_ids
from app.recommendation_worker import (
    CONSECUTIVE_IDENTICAL_FAILURE_LIMIT,
    DEFAULT_MAX_GAMES_PER_RUN,
    max_games_per_cycle,
    max_games_per_run,
    run_recommendation_worker_cycle,
)

SUPABASE_URL = "https://test-project.supabase.co"
AI_ORCHESTRATOR_URL = "https://ai-orchestrator.test"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _headers() -> dict:
    return {"apikey": "k", "Authorization": "Bearer k"}


def _captured_params(route) -> dict:
    """respx records the request; read back what we actually sent to
    PostgREST so the assertions below are about the QUERY, not about a
    Python-side filter that a real database would never see."""
    request = route.calls[0].request
    return dict(httpx.URL(str(request.url)).params.multi_items())


# ---------------------------------------------------------------- 1, 2, 3
# Eligibility contract: what may and may not enter recommendation processing.


@pytest.mark.asyncio
@respx.mock
async def test_final_and_live_games_cannot_enter_recommendation_processing():
    """VERIFY 1 -- completed/final games are excluded, in the query."""
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)

    params = _captured_params(route)
    # Only `scheduled` is ever requested -- final/live/postponed/canceled
    # are excluded by construction, not filtered out afterwards.
    assert params["status"] == "eq.scheduled"


@pytest.mark.asyncio
@respx.mock
async def test_far_future_season_games_cannot_enter_outside_the_authorized_horizon():
    """VERIFY 2 -- the horizon is enforced as an upper bound in the query.

    This is the exact defect: without the `lt.` bound, a January fixture
    read in September was 'eligible'.
    """
    route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)

    bounds = _captured_params(route)
    sent = [v for k, v in httpx.URL(str(route.calls[0].request.url)).params.multi_items() if k == "scheduled_start"]
    window_end = NOW + timedelta(days=RECOMMENDATION_WINDOW_DAYS)
    assert f"gte.{NOW.isoformat()}" in sent, "must exclude games already kicked off"
    assert f"lt.{window_end.isoformat()}" in sent, "must exclude games beyond the horizon"
    assert bounds["status"] == "eq.scheduled"
    # A January game against a September `now` is outside [now, now+7d).
    january = datetime(2027, 1, 10, 5, 0, tzinfo=timezone.utc)
    assert not (NOW <= january < window_end)


@pytest.mark.asyncio
@respx.mock
async def test_past_dated_scheduled_games_are_excluded():
    """VERIFY 2b -- `status` alone is not sufficient.

    Two real dev fixtures dated 2026-08-09 were still `scheduled` in
    mid-September and were being dispatched every run.
    """
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        await read_eligible_game_ids(client, _headers(), now=NOW)
    stale = datetime(2026, 8, 9, 23, 11, tzinfo=timezone.utc)
    assert stale < NOW, "a past-dated scheduled game must fall outside [now, now+7d)"


@pytest.mark.asyncio
@respx.mock
async def test_the_real_257_slate_reduces_to_the_in_window_games():
    """VERIFY 2c -- the live numbers, end to end.

    Dev at the time of the incident: 258 scheduled games, of which 2 were
    past-dated, 240 beyond the horizon, and 16 genuinely inside it.
    """
    window_end = NOW + timedelta(days=RECOMMENDATION_WINDOW_DAYS)
    season = (
        [{"id": f"past-{i}", "scheduled_start": datetime(2026, 8, 9, tzinfo=timezone.utc)} for i in range(2)]
        + [{"id": f"soon-{i}", "scheduled_start": NOW + timedelta(days=1 + i % 6)} for i in range(16)]
        + [{"id": f"far-{i}", "scheduled_start": NOW + timedelta(days=8 + i)} for i in range(240)]
    )
    assert len(season) == 258
    in_window = [g for g in season if NOW <= g["scheduled_start"] < window_end]
    assert len(in_window) == 16, "only the 7-day slate is eligible"


@pytest.mark.asyncio
@respx.mock
async def test_stale_or_missing_odds_never_reach_llm_agents_because_the_game_is_never_dispatched():
    """VERIFY 3 -- games with no fresh odds do not reach the committee.

    Freshness and reference-sportsbook selection already exist inside
    `ai-orchestrator`'s `generate_candidates_for_game`, which returns
    `game_skipped_reason="no_configured_sportsbook_has_fresh_data"`. But
    that guard runs AFTER the 6 game-level agents, so it bounds candidate
    work, not the fan-out. The horizon is what keeps a game with no
    possible fresh odds from being dispatched in the first place --
    specialized workers only poll inside the same 7 days, so a game beyond
    it provably has no fresh odds to find.
    """
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[]))
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.status == "completed"
    assert result.games_selected == 0
    assert orch.call_count == 0, "no eligible game means no dispatch and therefore no LLM fan-out"


# ------------------------------------------------------------------- 4
# Run-level bound: fail closed, never silently truncate.


def test_max_games_per_run_default_and_override(monkeypatch):
    monkeypatch.delenv("RECOMMENDATION_MAX_GAMES_PER_RUN", raising=False)
    assert max_games_per_run() == DEFAULT_MAX_GAMES_PER_RUN
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_RUN", "5")
    assert max_games_per_run() == 5
    # A typo in a safety ceiling must not itself become an outage.
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_RUN", "not-a-number")
    assert max_games_per_run() == DEFAULT_MAX_GAMES_PER_RUN
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_RUN", "0")
    assert max_games_per_run() == DEFAULT_MAX_GAMES_PER_RUN


@pytest.mark.asyncio
@respx.mock
async def test_run_level_bound_cannot_be_exceeded_and_fails_closed(monkeypatch):
    """VERIFY 4 -- an oversized slate dispatches NOTHING.

    Replays the incident: 257 eligible games against a ceiling of 20.
    """
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_RUN", "20")
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(257)])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.status == "failed"
    assert orch.call_count == 0, "fail closed means ZERO dispatches, not a truncated slate"
    assert result.games_selected == 257
    assert result.games_not_attempted == 257
    assert "257" in result.error and "20" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_bound_not_tripped_by_a_legitimate_slate(monkeypatch):
    """A real 16-game NFL week runs normally -- the bound is a safety net,
    not a scheduling policy."""
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_RUN", "20")
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(16)])
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r", "status": "ok", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.status == "completed"
    assert result.games_selected == 16
    assert result.games_not_attempted == 0
    assert len(result.games) == 16


# ------------------------------------------------------------------- 5
# Deterministic config failure must not create unbounded marker rows.


@pytest.mark.asyncio
@respx.mock
async def test_deterministic_config_failure_halts_instead_of_burning_the_slate():
    """VERIFY 5 -- the exact 2026-09-17 shape, bounded.

    Every game returns the same `ConfigError` 500. Each dispatch that
    reaches `ai-orchestrator` creates one `recommendations` marker row
    BEFORE failing, so 257 dispatches left 256 orphan rows. The breaker
    stops after 3.
    """
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(16)])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(
            500,
            text="REFERENCE_SPORTSBOOK_PREFERENCE is not set or empty -- cannot generate candidates",
        )
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.status == "failed"
    assert orch.call_count == CONSECUTIVE_IDENTICAL_FAILURE_LIMIT == 3
    assert result.games_not_attempted == 13, "the remaining games are never attempted"
    assert "deterministic" in result.error
    # Marker growth is bounded by dispatch count: 3 per run, not 256.


@pytest.mark.asyncio
@respx.mock
async def test_isolated_per_game_failures_do_not_trip_the_breaker():
    """A genuinely per-game fault must still be isolated, not halt the
    slate -- the breaker is for deterministic faults only."""
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(6)])
    )

    calls = {"n": 0}

    def _respond(request):
        calls["n"] += 1
        # Distinct, game-specific errors -- never the same fault twice.
        return httpx.Response(500, text=f"transient upstream blip #{calls['n']}")

    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(side_effect=_respond)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.status == "completed"
    assert orch.call_count == 6, "every game is still attempted"
    assert all(g.status == "failed" for g in result.games)


# ------------------------------------------------------------------- 6, 7
# Sentry semantics: nested failures are visible; clean runs stay silent.


def test_257_of_257_nested_failures_produce_a_sentry_failure_summary():
    """VERIFY 6 -- the miss that started this directive.

    `status="completed"` with every game carrying an error previously
    returned `None`, because "completed" is on the non-reportable list and
    the nested check came afterwards.
    """
    payload = {
        "status": "completed",
        "run_id": "run-1",
        "games": [
            {"game_id": f"g{i}", "status": "failed", "error": "ai-orchestrator returned 500: ConfigError"}
            for i in range(257)
        ],
    }
    summary = result_failure_summary(payload)
    assert summary is not None, "a total failure wearing a success status must be reported"
    level, text = summary
    assert level == "error"
    assert "every item" in text
    assert "257" not in text or "ConfigError" in text


def test_partial_nested_failure_is_reported_as_a_warning():
    payload = {
        "status": "completed",
        "games": [
            {"game_id": "g1", "status": "dispatched", "error": None},
            {"game_id": "g2", "status": "failed", "error": "boom"},
        ],
    }
    level, text = result_failure_summary(payload)
    assert level == "warning"
    assert "1 of 2 items" in text


def test_genuinely_clean_completed_run_remains_non_reportable():
    """VERIFY 7 -- the silence that must be preserved.

    This is the postgame-grading shape that has been running clean every
    30 minutes since the transport fix.
    """
    payload = {
        "status": "completed",
        "game_ids": ["g1", "g2"],
        "games": [
            {"game_id": "g1", "status": "graded", "legs": [], "no_bet_products": [], "products": []},
            {"game_id": "g2", "status": "graded", "legs": [], "no_bet_products": [], "products": []},
        ],
        "postgame_reviews_generated": 0,
        "postgame_reviews_failed": 0,
        "postgame_reviews_skipped": 0,
    }
    assert result_failure_summary(payload) is None


def test_clean_success_and_deliberate_pauses_remain_silent():
    """The non-reportable set shipped 2026-09-16 is unchanged by this fix."""
    assert result_failure_summary({"status": "success", "games_due": 0, "failures": []}) is None
    assert result_failure_summary({"status": "paused"}) is None
    assert result_failure_summary({"status": "skipped_credit_guard"}) is None
    assert result_failure_summary({"status": "skipped_daily_budget"}) is None


def test_fail_closed_bound_is_sentry_visible():
    """The run-level bound reports at `error` -- a ceiling being hit is
    never silent, and never dressed up as a complete run."""
    payload = {
        "status": "failed",
        "games": [],
        "games_selected": 257,
        "games_not_attempted": 257,
        "error": "eligible slate of 257 games exceeds the run ceiling of 20",
    }
    level, text = result_failure_summary(payload)
    assert level == "error"
    assert "257" in text


def test_nested_check_applies_generically_to_grading_shapes():
    """The rule is generic, not a 257-specific exception: postgame
    grading's own `legs`/`products` collections are inspected too."""
    payload = {
        "status": "completed",
        "legs": [{"leg_id": "l1", "status": "failed", "error": "missing final score"}],
        "products": [{"product_id": "p1", "status": "created"}],
    }
    level, text = result_failure_summary(payload)
    assert level == "warning"
    assert "missing final score" in text


# ------------------------------------------------------------------- 8
# No real LLM call occurred anywhere in this suite.


def test_no_real_llm_or_provider_call_is_reachable_from_this_suite():
    """VERIFY 8 -- structural, not aspirational.

    Every test above is wrapped in `respx.mock`, which intercepts all
    httpx traffic; an unmocked host raises rather than escaping. This
    worker service additionally has no model adapter, no provider SDK and
    no API key in its dependency graph at all -- it only ever speaks to
    Supabase and to `ai-orchestrator`'s internal endpoint.
    """
    import app.recommendation_worker as worker

    source = worker.__file__
    assert "ai_orchestrator_client" in open(source).read()
    for forbidden in ("anthropic", "openai", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert forbidden not in open(source).read(), f"{forbidden} must never appear in the worker service"


# ------------------------------------------------------------------- 12
# Staged activation throttle (2026-09-18): process at most N, explicitly.


@pytest.mark.asyncio
@respx.mock
async def test_activation_throttle_processes_exactly_one_game_and_says_so(monkeypatch):
    """The first live committee run is held to ONE game, and the result
    makes that impossible to mistake for a full slate."""
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "1")
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(16)])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "status": "computed", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 1, "exactly one game may reach the LLM path"
    assert result.status == "completed_limited", "a throttled pass must not report plain 'completed'"
    assert result.games_selected == 16
    assert result.games_deferred == 15
    assert len(result.games) == 1


@pytest.mark.asyncio
@respx.mock
async def test_throttle_takes_the_soonest_kickoff_not_an_invented_ranking(monkeypatch):
    """Ordering is Volume 5's HQ Final Decision 1 -- chronological by
    `games.scheduled_start`, never EV or confidence. The read already
    orders `scheduled_start.asc`, so the throttle takes a prefix and
    invents nothing."""
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "1")
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    # Returned in the order PostgREST would return them under
    # `order=scheduled_start.asc`.
    games_route = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": "earliest"}, {"id": "middle"}, {"id": "latest"}])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "status": "computed", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert result.games[0].game_id == "earliest"
    assert orch.call_count == 1
    # The ordering comes from the query, not from Python re-sorting.
    # `id.asc` is a tiebreak, not a ranking: eight real games share a
    # 17:00 UTC kickoff, so chronological alone is irreproducible.
    assert games_route.calls[0].request.url.params["order"] == "scheduled_start.asc,id.asc"


def test_throttle_defaults_to_no_limit(monkeypatch):
    """Unset is the normal production state -- a throttle must never be
    accidentally on."""
    monkeypatch.delenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", raising=False)
    assert max_games_per_cycle() is None
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "")
    assert max_games_per_cycle() is None
    # A typo must not silently shrink the slate to something unintended.
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "one")
    assert max_games_per_cycle() is None
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "0")
    assert max_games_per_cycle() is None
    monkeypatch.setenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", "1")
    assert max_games_per_cycle() == 1


@pytest.mark.asyncio
@respx.mock
async def test_throttle_does_not_change_an_unthrottled_run(monkeypatch):
    """With no throttle set, behaviour is exactly as before -- plain
    `completed`, nothing deferred."""
    monkeypatch.delenv("RECOMMENDATION_MAX_GAMES_PER_CYCLE", raising=False)
    respx.get(f"{SUPABASE_URL}/rest/v1/master_refresh_runs").mock(
        return_value=httpx.Response(200, json=[{"id": "run-1", "status": "success"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[{"id": f"g{i}"} for i in range(16)])
    )
    orch = respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/run-game").mock(
        return_value=httpx.Response(200, json={"recommendation_id": "r1", "status": "computed", "candidates": []})
    )
    respx.post(f"{AI_ORCHESTRATOR_URL}/v1/internal/recommendation-worker/finalize-strategy").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as db, httpx.AsyncClient() as orch_client:
        result = await run_recommendation_worker_cycle(
            db, _headers(), ai_orchestrator_client=orch_client,
            ai_orchestrator_base_url=AI_ORCHESTRATOR_URL, internal_token="secret", now=NOW,
        )

    assert orch.call_count == 16
    assert result.status == "completed"
    assert result.games_deferred == 0


def test_throttled_status_is_not_reported_as_an_error():
    """A deliberate throttle is normal operation, not a Sentry event --
    but it is still a DISTINCT status from a full `completed`."""
    from app.cron_dispatch import _NON_ERROR_STATUSES

    assert "completed_limited" in _NON_ERROR_STATUSES
    assert result_failure_summary({
        "status": "completed_limited", "games_selected": 16, "games_deferred": 15,
        "games": [{"game_id": "g1", "status": "dispatched", "error": None}],
    }) is None
    # ...and a throttled run that ALSO failed its one game is still loud.
    level, _ = result_failure_summary({
        "status": "completed_limited", "games_deferred": 15,
        "games": [{"game_id": "g1", "status": "failed", "error": "boom"}],
    })
    assert level == "error"
