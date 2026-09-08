"""Test for app.diagnostics.msf_roster_activation (Phase 8.2 controlled
DEV activation, temporary module). Proves the real 34-player dataset is
well-formed and correctly split by team before it's ever run against
real Supabase -- every Supabase boundary respx-mocked, matching this
project's own established convention."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.diagnostics.msf_roster_activation import _REAL_ACTIVATED_PLAYERS, run_msf_roster_activation

SUPABASE_URL = "https://test-project.supabase.co"


def test_real_dataset_has_34_players_split_17_and_17():
    assert len(_REAL_ACTIVATED_PLAYERS) == 34
    teams = [t for *_rest, t in _REAL_ACTIVATED_PLAYERS]
    assert teams.count("NE") == 17
    assert teams.count("SEA") == 17


def test_real_dataset_ids_are_unique():
    ids = [pid for pid, *_rest in _REAL_ACTIVATED_PLAYERS]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
@respx.mock
async def test_run_activation_persists_both_teams(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json=[
                {
                    "team_id": "team-ne" if "NE" in request.url.params.get("provider_team_id", "") else "team-sea",
                    "provider_team_id": "NE" if "NE" in request.url.params.get("provider_team_id", "") else "SEA",
                }
            ],
        )
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(return_value=httpx.Response(201))
    created_ids = iter([f"player-{i}" for i in range(34)])
    respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created_ids)}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/roster_memberships").mock(return_value=httpx.Response(201))
    respx.patch(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(204))
    depth_route = respx.post(f"{SUPABASE_URL}/rest/v1/depth_chart_snapshots")

    results = await run_msf_roster_activation()

    assert set(results.keys()) == {"NE", "SEA"}
    assert results["NE"].players_created == 17
    assert results["SEA"].players_created == 17
    assert results["NE"].depth_chart_written is False
    assert results["SEA"].depth_chart_written is False
    assert not depth_route.called  # write_depth_chart_snapshot=False honored end-to-end
