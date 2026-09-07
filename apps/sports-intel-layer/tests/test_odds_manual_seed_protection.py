"""Phase 7 Controlled Real Odds Activation safety fix (2026-09-07): a
`games.manual_seed=true` row that never links to a real event must not
trigger a paid call on every cron tick indefinitely -- MANUAL_SEED_MAX_ATTEMPTS
caps it. A normal (manual_seed=false) game is completely unaffected.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.adapters.cache import InMemoryCacheBackend
from app.workers.odds_worker import MANUAL_SEED_MAX_ATTEMPTS, run_odds_worker
from tests.test_odds_worker import _headers_env, _mock_credit_ledger, _mock_game_provider_ids

SUPABASE_URL = "https://test-project.supabase.co"
ODDS_API_URL = "https://api.the-odds-api.com"
ODDS_URL = f"{ODDS_API_URL}/v4/sports/americanfootball_nfl/odds"

_NOW = datetime(2026, 9, 14, 16, 55, tzinfo=timezone.utc)  # 5 min before kickoff -> due


def _manual_seed_game(*, unresolved_poll_attempts: int) -> dict:
    return {
        "id": "game-manual-1",
        "external_provider_id": None,
        "home_team": "KC",
        "away_team": "BUF",
        "scheduled_start": "2026-09-14T17:00:00Z",
        "stadium": None,
        "status": "scheduled",
        "season_type": "regular",
        "week": 1,
        "manual_seed": True,
        "unresolved_poll_attempts": unresolved_poll_attempts,
    }


def _normal_game() -> dict:
    return {
        "id": "game-normal-1",
        "external_provider_id": None,
        "home_team": "SEA",
        "away_team": "NE",
        "scheduled_start": "2026-09-14T17:00:00Z",
        "stadium": None,
        "status": "scheduled",
        "season_type": "regular",
        "week": 1,
        "manual_seed": False,
        "unresolved_poll_attempts": 0,
    }


async def _run(*, games: list[dict], monkeypatch):
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=games))
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(return_value=httpx.Response(201))
    _mock_credit_ledger()
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(204))
    odds_route = respx.get(ODDS_URL).mock(return_value=httpx.Response(200, json=[]))  # no real events -- nothing links
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(base_url=ODDS_API_URL) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client,
            the_odds_api_client=odds_client,
            the_odds_api_key="test-key",
            cache_backend=InMemoryCacheBackend(),
            now=_NOW,
        )
    return result, odds_route, patch_route


@pytest.mark.asyncio
@respx.mock
async def test_manual_seed_game_below_cap_is_still_due_and_attempts_increment(monkeypatch):
    result, odds_route, patch_route = await _run(games=[_manual_seed_game(unresolved_poll_attempts=0)], monkeypatch=monkeypatch)
    assert result.games_due == 1
    assert odds_route.call_count == 1  # still tries -- below the cap
    # unresolved_poll_attempts incremented from 0 -> 1 (nothing linked/captured)
    assert patch_route.call_count == 1
    import json
    body = json.loads(patch_route.calls[0].request.content)
    assert body == {"unresolved_poll_attempts": 1}


@pytest.mark.asyncio
@respx.mock
async def test_manual_seed_game_at_cap_is_excluded_no_paid_call(monkeypatch):
    result, odds_route, patch_route = await _run(
        games=[_manual_seed_game(unresolved_poll_attempts=MANUAL_SEED_MAX_ATTEMPTS)], monkeypatch=monkeypatch
    )
    assert result.games_due == 0
    assert result.games_skipped_not_due == 1
    assert odds_route.call_count == 0  # never even attempted -- no paid call
    assert patch_route.call_count == 0  # nothing to update, it was never due


@pytest.mark.asyncio
@respx.mock
async def test_normal_game_unaffected_by_manual_seed_protection(monkeypatch):
    """A normal Schedule-sourced game (manual_seed=false) keeps retrying
    indefinitely, unaffected -- the correct behavior for a real,
    temporarily-unresolved game (never capped)."""
    result, odds_route, patch_route = await _run(games=[_normal_game()], monkeypatch=monkeypatch)
    assert result.games_due == 1
    assert odds_route.call_count == 1
    assert patch_route.call_count == 0  # unresolved_poll_attempts is never touched for a non-manual-seed game


@pytest.mark.asyncio
@respx.mock
async def test_manual_seed_game_that_links_resets_attempts_to_zero(monkeypatch):
    game = _manual_seed_game(unresolved_poll_attempts=2)
    _headers_env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(200, json=[game]))
    def _team_provider_respond(request: httpx.Request) -> httpx.Response:
        provider_name = request.url.params["provider_name"]
        rows = {
            "eq.the_odds_api": [
                {"team_id": "t-kc", "provider_team_id": "Kansas City Chiefs"},
                {"team_id": "t-buf", "provider_team_id": "Buffalo Bills"},
            ],
            "eq.sportsdataio": [
                {"team_id": "t-kc", "provider_team_id": "KC"},
                {"team_id": "t-buf", "provider_team_id": "BUF"},
            ],
        }
        return httpx.Response(200, json=rows.get(provider_name, []))

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(side_effect=_team_provider_respond)
    _mock_game_provider_ids()
    _mock_credit_ledger()
    respx.post(f"{SUPABASE_URL}/rest/v1/odds_snapshots").mock(return_value=httpx.Response(201))
    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(return_value=httpx.Response(204))
    respx.get(ODDS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "real-event-1",
                    "sport_key": "americanfootball_nfl",
                    "commence_time": "2026-09-14T17:00:00Z",
                    "home_team": "Kansas City Chiefs",
                    "away_team": "Buffalo Bills",
                    "bookmakers": [
                        {
                            "key": "draftkings",
                            "markets": [{"key": "h2h", "last_update": "2026-09-14T16:00:00Z", "outcomes": [{"name": "Kansas City Chiefs", "price": -150}, {"name": "Buffalo Bills", "price": 130}]}],
                        }
                    ],
                }
            ],
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as supabase_client, httpx.AsyncClient(base_url=ODDS_API_URL) as odds_client:
        result = await run_odds_worker(
            supabase_client=supabase_client, the_odds_api_client=odds_client, the_odds_api_key="test-key",
            cache_backend=InMemoryCacheBackend(), now=_NOW,
        )
    assert result.newly_linked == 1
    assert result.lines_persisted == 1
    import json
    body = json.loads(patch_route.calls[0].request.content)
    assert body == {"unresolved_poll_attempts": 0}
