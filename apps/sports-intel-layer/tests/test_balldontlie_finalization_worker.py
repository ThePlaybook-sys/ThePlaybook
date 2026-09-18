"""BALLDONTLIE canonical finalization worker (2026-09-18, HQ-authorized).

Every cost-policy clause in the directive gets its own test, and the two
safety cases that would actually corrupt data -- freezing an in-progress
score, and overwriting an already-finalized game -- get theirs first.

The adapter is injected, so no provider host appears in this file at all.
respx is strict, so that is enforced rather than asserted.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.errors import ProviderRateLimitError
from app.adapters.models import AdapterResponse, FinalScoreLine
from app.workers import balldontlie_finalization_worker as worker
from app.workers.balldontlie_finalization_worker import (
    MAX_ATTEMPTS,
    FinalizationResult,
    run_balldontlie_finalization,
)

SUPABASE_URL = "https://test-project.supabase.co"
GAMES = f"{SUPABASE_URL}/rest/v1/games"
STATE = f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state"
EVENTS = f"{SUPABASE_URL}/rest/v1/game_events"

GAME_ID = "11111111-1111-4111-8111-111111111111"
KICKOFF = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)
NOW = KICKOFF + timedelta(hours=4)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BALLDONTLIE_FINALIZATION_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)


class _Adapter:
    """Injected stand-in. Counts requests the way the real boundary does --
    before the outcome is known."""

    def __init__(self, lines: list[FinalScoreLine] | None = None, raises: Exception | None = None):
        self._lines = lines or []
        self._raises = raises
        self.calls: list[tuple[int, int]] = []

    async def fetch_week_final_scores(self, *, season: int, week: int, per_page: int = 100):
        self.calls.append((season, week))
        if self._raises is not None:
            raise self._raises
        return AdapterResponse(value=list(self._lines), source="balldontlie")


def _line(**overrides) -> FinalScoreLine:
    data = {
        "provider_game_id": "1392300",
        "home_team": "TB",
        "away_team": "CLE",
        "scheduled_start": KICKOFF,
        "home_score": 24,
        "away_score": 17,
        "provider_status": "Final",
        "is_final": True,
    }
    data.update(overrides)
    return FinalScoreLine(**data)


def _candidate(**overrides) -> dict:
    row = {
        "id": GAME_ID,
        "scheduled_start": KICKOFF.isoformat(),
        "home_team": "TB",
        "away_team": "CLE",
        "week": 2,
        "season_id": None,
        "status": "final",
    }
    row.update(overrides)
    return row


def _mock_supabase(*, candidates: list[dict], claim_row: dict | None, finalize_rows=None):
    respx.get(GAMES).mock(return_value=httpx.Response(200, json=candidates))
    respx.get(STATE).mock(return_value=httpx.Response(200, json=[]))
    respx.post(STATE).mock(
        return_value=httpx.Response(201, json=[{"id": "s1", "state": "scheduled", "attempt_count": 0}])
    )
    respx.patch(STATE).mock(
        return_value=httpx.Response(200, json=[claim_row] if claim_row else [])
    )
    respx.post(EVENTS).mock(return_value=httpx.Response(201, json=[{"id": "ev1"}]))
    return respx.patch(GAMES).mock(
        return_value=httpx.Response(
            200, json=finalize_rows if finalize_rows is not None else [{"id": GAME_ID}]
        )
    )


async def _run(adapter) -> FinalizationResult:
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        return await run_balldontlie_finalization(
            supabase_client=client, adapter=adapter, now=NOW, season=2026
        )


# ---------------------------------------------------------------- safety
@pytest.mark.asyncio
@respx.mock
async def test_in_progress_game_is_never_finalized():
    """The live-captured SF @ LAR case: a REAL 3-0 score with
    `status_state='in_progress'`. A rule keyed on "score is not null" writes a
    first-quarter score as the result of the game."""
    finalize = _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    adapter = _Adapter([_line(home_score=0, away_score=3, provider_status="1:31 - 1st", is_final=False)])

    result = await _run(adapter)

    assert result.finalized == []
    assert result.not_final_yet == [GAME_ID]
    assert finalize.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_final_but_scoreless_row_is_not_finalized():
    """`is_final` alone is not enough -- a null score must not become a 0."""
    finalize = _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    result = await _run(_Adapter([_line(home_score=None, away_score=None)]))

    assert result.finalized == []
    assert finalize.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_already_finalized_game_is_not_overwritten():
    """`finalize_game` carries `finalized_at=is.null` server-side, so a repeat
    returns zero rows. That is a normal outcome, not a failure."""
    _mock_supabase(
        candidates=[_candidate()],
        claim_row={"attempt_count": 0, "state": "capture_in_progress"},
        finalize_rows=[],
    )
    result = await _run(_Adapter([_line()]))

    assert result.finalized == []
    assert result.already_finalized == [GAME_ID]
    assert result.status == "success"


@pytest.mark.asyncio
@respx.mock
async def test_score_is_copied_verbatim_never_derived():
    finalize = _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    await _run(_Adapter([_line(home_score=24, away_score=17)]))

    body = json.loads(finalize.calls[0].request.content)
    assert body["final_score"] == {"home": 24, "away": 17}
    assert body["status"] == "final"
    assert body["finalized_at"] == NOW.isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_raw_evidence_is_written_before_the_canonical_score():
    """No final score may exist without the payload that justifies it."""
    _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    await _run(_Adapter([_line()]))

    order = [c.request.url.path for c in respx.calls]
    assert order.index("/rest/v1/game_events") < len(order) - 1
    evidence = json.loads(
        [c for c in respx.calls if c.request.url.path == "/rest/v1/game_events"][0].request.content
    )
    payload = evidence[0]["raw_payload"] if isinstance(evidence, list) else evidence["raw_payload"]
    assert payload["matched_provider_game_id"] == "1392300"
    assert payload["endpoint"] == "https://api.balldontlie.io/nfl/v1/games"


# ------------------------------------------------------------ identity
@pytest.mark.asyncio
@respx.mock
async def test_no_exact_match_is_reported_never_guessed():
    """A provider row for a different kickoff must not be matched to this game
    just because it is the only row in the response."""
    finalize = _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    result = await _run(_Adapter([_line(scheduled_start=KICKOFF + timedelta(minutes=5))]))

    assert result.unresolved == [GAME_ID]
    assert finalize.call_count == 0
    assert result.status == "partial"


@pytest.mark.asyncio
@respx.mock
async def test_wsh_alias_resolves_to_the_canonical_was():
    """The one documented abbreviation divergence, handled by an explicit
    alias rather than by fuzzy matching."""
    finalize = _mock_supabase(
        candidates=[_candidate(home_team="WAS")],
        claim_row={"attempt_count": 0, "state": "capture_in_progress"},
    )
    result = await _run(_Adapter([_line(home_team="WSH")]))

    assert result.finalized == [GAME_ID]
    assert finalize.call_count == 1


# ---------------------------------------------------------------- cost
@pytest.mark.asyncio
@respx.mock
async def test_no_eligible_game_means_zero_provider_requests():
    _mock_supabase(candidates=[], claim_row=None)
    adapter = _Adapter([_line()])
    result = await _run(adapter)

    assert result.games_considered == 0
    assert adapter.calls == []
    assert result.provider_requests == 0


@pytest.mark.asyncio
@respx.mock
async def test_unclaimable_slate_means_zero_provider_requests():
    """Backed-off or concurrently-claimed games contribute no week, so they
    cannot pull a request. Claim first, fetch second, on purpose."""
    _mock_supabase(candidates=[_candidate()], claim_row=None)
    adapter = _Adapter([_line()])
    result = await _run(adapter)

    assert adapter.calls == []
    assert result.provider_requests == 0


@pytest.mark.asyncio
@respx.mock
async def test_pre_kickoff_and_finalized_games_are_excluded_in_the_query():
    """The three bounds are enforced by PostgREST, not in Python, so an
    oversized candidate set can never reach the fetch loop."""
    _mock_supabase(candidates=[], claim_row=None)
    await _run(_Adapter())

    params = respx.get(GAMES).calls[0].request.url.params
    assert params["finalized_at"] == "is.null"
    assert params.get_list("scheduled_start") == [
        f"gte.{(NOW - timedelta(days=worker.LOOKBACK_DAYS)).isoformat()}",
        f"lte.{(NOW - timedelta(hours=worker.FIRST_CHECK_AFTER_KICKOFF_HOURS)).isoformat()}",
    ]


@pytest.mark.asyncio
@respx.mock
async def test_sixteen_games_in_one_week_cost_exactly_one_request():
    """The bulk advantage, which the directive forbids converting into
    per-game calls."""
    candidates = [
        _candidate(id=f"1111111{i}-1111-4111-8111-111111111111", home_team=f"T{i:02d}")
        for i in range(16)
    ]
    _mock_supabase(candidates=candidates, claim_row={"attempt_count": 0, "state": "capture_in_progress"})
    adapter = _Adapter([_line(home_team=f"T{i:02d}") for i in range(16)])

    result = await _run(adapter)

    assert result.games_considered == 16
    assert adapter.calls == [(2026, 2)]
    assert result.provider_requests == 1
    assert len(result.finalized) == 16


@pytest.mark.asyncio
@respx.mock
async def test_two_weeks_cost_exactly_two_requests():
    candidates = [
        _candidate(week=2),
        _candidate(id="22222222-2222-4222-8222-222222222222", week=3, home_team="KC"),
    ]
    _mock_supabase(candidates=candidates, claim_row={"attempt_count": 0, "state": "capture_in_progress"})
    adapter = _Adapter([_line(), _line(home_team="KC")])

    result = await _run(adapter)

    assert sorted(adapter.calls) == [(2026, 2), (2026, 3)]
    assert result.provider_requests == 2


# ------------------------------------------------------------- retries
@pytest.mark.asyncio
@respx.mock
async def test_transient_failure_backs_off_durably_and_is_counted():
    """A request that was sent and then failed has still been spent."""
    _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 1, "state": "capture_in_progress"}
    )
    result = await _run(_Adapter(raises=ProviderRateLimitError("rate limited", provider="balldontlie")))

    assert result.provider_requests == 1
    assert result.status == "partial"

    release = json.loads(respx.patch(STATE).calls[-1].request.content)
    assert release["state"] == "capture_failed_transient"
    assert release["error_classification"] == "transient"
    assert release["attempt_count"] == 2
    assert release["next_eligible_attempt_at"] == (
        NOW + timedelta(minutes=worker.RETRY_BACKOFF_MINUTES)
    ).isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_attempt_budget_exhaustion_stops_permanently_and_costs_nothing():
    """At the budget the game is quarantined BEFORE the fetch, so a
    permanently broken game stops costing provider calls entirely."""
    _mock_supabase(
        candidates=[_candidate()],
        claim_row={"attempt_count": MAX_ATTEMPTS, "state": "capture_in_progress"},
    )
    adapter = _Adapter([_line()])
    result = await _run(adapter)

    assert adapter.calls == []
    assert result.provider_requests == 0
    release = json.loads(respx.patch(STATE).calls[-1].request.content)
    assert release["state"] == "capture_failed_permanent"
    assert release["error_classification"] == "permanent"


@pytest.mark.asyncio
@respx.mock
async def test_restart_cannot_reset_the_attempt_budget():
    """The budget is read from the DURABLE row, not from process memory. A
    fresh worker sees attempt 5 and increments to 6, it does not start at 1."""
    _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 5, "state": "capture_in_progress"}
    )
    await _run(_Adapter(raises=ProviderRateLimitError("rate limited", provider="balldontlie")))

    assert json.loads(respx.patch(STATE).calls[-1].request.content)["attempt_count"] == 6


# ---------------------------------------------------------------- gate
@pytest.mark.asyncio
@respx.mock
async def test_disabled_gate_makes_no_call_of_any_kind(monkeypatch):
    """Not one provider request and not one Supabase query. Proven with respx
    strict and NO routes registered at all, so any request would raise."""
    monkeypatch.setenv("BALLDONTLIE_FINALIZATION_ENABLED", "false")
    adapter = _Adapter([_line()])

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_balldontlie_finalization(
            supabase_client=client, adapter=adapter, now=NOW
        )

    assert result.status == "paused"
    assert result.error is None
    assert adapter.calls == []
    assert len(respx.calls) == 0


@pytest.mark.asyncio
@respx.mock
async def test_unset_gate_is_paused_not_enabled(monkeypatch):
    """Explicit-opt-in: a removed flag must never start spending money."""
    monkeypatch.delenv("BALLDONTLIE_FINALIZATION_ENABLED", raising=False)
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_balldontlie_finalization(
            supabase_client=client, adapter=_Adapter(), now=NOW
        )
    assert result.status == "paused"


@pytest.mark.asyncio
@respx.mock
async def test_no_provider_host_is_contacted_from_this_module():
    _mock_supabase(
        candidates=[_candidate()], claim_row={"attempt_count": 0, "state": "capture_in_progress"}
    )
    await _run(_Adapter([_line()]))
    assert {c.request.url.host for c in respx.calls} == {"test-project.supabase.co"}
