"""Zero-cost Gate B 69-player REAL replay against the PERMANENT
orchestration path (Permanent Box Score Worker Build, 2026-09-11,
HQ-authorized). Exercises `run_msf_postgame_capture` end to end --
claim, MSF game-id resolution, season resolution, raw preservation,
validation, playedStatus inspection, per-player automatic identity
activation, idempotent stat persistence, and final ingestion-state
advancement -- with ONLY the network fetch substituted by the
already-preserved real NE@SEA fixture
(`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`).

**NO MySportsFeeds call is made anywhere in this file.** The injected
`fetch_boxscore` fake returns the real, already-captured fixture body
directly -- `_default_fetch_boxscore` (the only function in
`app.workers.msf_postgame_worker` that could make a real call) is never
imported or invoked here.

`_LIVE_DEV_RESOLVED_PLAYER_IDS` is the same real, live-confirmed
(provider_player_id -> players.id) mapping the prior "Automatic Player
Identity + Quarantine Build" pass's own Gate B replay used (confirmed
against dev, project `nhwjtsdebgiwskshzqiq`, 2026-09-11) -- all 69 real
players in this fixture already carry a mysportsfeeds mapping.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.workers.msf_postgame_worker import BoxscoreFetchResult, run_msf_postgame_capture

SUPABASE_URL = "https://test-project.supabase.co"
CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
MSF_GAME_ID = "163541"

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "ops"
    / "fixtures"
    / "gate-b-msf-game-boxscore-163541-2026-09-10.json"
)

#: Same real, live-confirmed mapping used by
#: tests/test_player_identity_activation_gate_b_replay.py -- see that
#: file's own docstring for full provenance.
_LIVE_DEV_RESOLVED_PLAYER_IDS: dict[str, str] = {
    "10027": "fde15cd4-e003-4b4f-80aa-5b03ed90edaa", "10040": "ddb2883e-cf1e-42d0-9af5-67058fd60efa",
    "108896": "38501d2e-31d8-4e4f-89af-e1eaa01ff435", "112112": "fdf01652-d62c-4138-8391-e82b6e99e4bd",
    "112158": "a92f6723-0701-409c-ac7e-67c2d055d893", "112190": "4c5fb5a4-9ca4-455f-af83-507a666f005a",
    "112203": "3168919b-4eed-4dae-92c8-85bbc8957df2", "112349": "a6ed9ee6-cea6-4044-abce-46d780f536d2",
    "112359": "5bd23f39-6f17-46d1-9476-fd46e1dcbe6d", "12738": "64568902-1ddd-4a36-b9d1-c54450b5fc74",
    "13280": "f07364ba-7242-45b3-9af6-a0d42557ff53", "133837": "00323ce5-d456-4c5a-a570-9bf97ac1c70d",
    "133850": "eb2217e4-bfc4-4c7a-8121-2af842e780a4", "133956": "dd17580e-ff37-4336-9248-6ee6b4ccde0c",
    "133972": "351ea8e3-89b5-473c-8ea8-2d04940448b6", "13412": "40258346-dd7e-4ff6-a159-a3e37aa4b5bb",
    "134254": "65ed5b33-7794-4876-9ee9-f1b5e1c558de", "134564": "80a69a07-94d0-4e84-9e1b-d6e45e997d51",
    "134586": "4d757809-13fa-49f5-88bc-7d636f5fd0ed", "14494": "94e9a1a1-bf78-4780-873e-c024527bb39e",
    "14732": "2c83b05f-8e14-4f38-ab0a-423c08f921f3", "14990": "36dc5f3e-1d7d-4fef-81a2-fa86bb789dfa",
    "15031": "4d4d0514-beb5-4900-8442-96d5c96bc394", "16129": "90e967b8-1356-4488-9627-e9cbe6688d37",
    "16516": "89447ac9-5090-4f19-94f0-745f30b7be7f", "16653": "a99d092e-43be-4ffa-82d6-0348cdba1aeb",
    "166661": "1c2e80f8-4f68-41b6-9bcb-3c816c963578", "166678": "296dedd2-86ac-44e2-98eb-31e07eb7520a",
    "166739": "52cd9323-d138-4b43-beaa-eef83d75eae9", "166763": "27516ef2-c1bb-4c83-9981-7786035247a5",
    "166773": "32cab57e-2a94-4474-bb2f-328587f32d0b", "166844": "5b3c7e3d-03af-404f-888e-a93cac7980ea",
    "166894": "b3a2321a-cf77-479d-ba1f-632d0dc18eaf", "166956": "d72f1a24-b20e-4d9f-9ba1-a1b9e76dc301",
    "16698": "940576c3-751d-48d5-98c1-c6d5eeaf0a87", "167667": "b574df7a-61d4-41b8-8cd1-2fa42cba50b3",
    "16786": "c9acc58a-0ff9-48fc-a9e8-8b6e7cc5170c", "168066": "1941b092-aa15-4863-9489-0c8b12212d8e",
    "168073": "cf2fa2be-983c-4053-a0a9-da77dbfcca6b", "16817": "00e21a2f-a03d-487e-97f4-1c0734a8f802",
    "207936": "366a5ed7-f725-4c1f-8b3b-c59ef613b24c", "207959": "be05232f-6149-4461-9970-d50a039a9e2e",
    "207999": "7ab0bc29-5b95-46b1-986d-ef0218993520", "208124": "59e98077-2676-4271-8875-b664c16e4667",
    "30251": "9580cbbb-ca59-4782-8355-f598dd919a0b", "30398": "36bf6b7e-68d9-4a55-987d-235bb046fa8a",
    "30442": "5f92bf4a-a6ac-4c19-8e27-112e31a96f38", "30602": "d2cc6d68-7748-4e22-8ca2-2d2e6b231aed",
    "30820": "8f6551bc-095e-4136-b892-895c76ebab6e", "30942": "d76ee386-c5ec-4aa9-bf72-ef30a8518d14",
    "30974": "b647cc0a-9773-4311-955f-e4adba1463c3", "31103": "d7cb37dd-547f-435a-8b3d-6e3cd42dce2c",
    "39267": "89b94fb5-a999-4b6e-8153-de0280e5e3cc", "39287": "5b38f7bc-df80-4fa9-8664-2361f146e840",
    "39293": "3d915ba3-3138-4f48-86c6-a92bedee21bc", "47382": "2240479a-561e-4318-ac46-ae09ad674977",
    "48151": "757ef996-57eb-4370-8acd-45db1c3b9110", "48291": "c86d87a9-4a97-4878-a99a-e7e4321484be",
    "55455": "db0abc28-7309-4dd2-ab4e-25d6cac15a19", "6696": "49b95de1-1331-447d-8bac-d5f23d861452",
    "7266": "b772844c-1cd5-4687-ad29-7c515ef35ee3", "7876": "ad24d682-1b40-4a80-adc3-c5c88490cb0e",
    "79743": "90d749de-abc0-4aa3-b46f-2342e606acdf", "79755": "12be989d-29b0-4a9a-97e0-98c2b05949a5",
    "79758": "c9b7de10-b380-45e4-90a3-f98444dce258", "79775": "30e77e0a-ee6c-42f2-9802-a667961ddf9f",
    "79846": "0683e33b-82b4-4d2c-89ee-675c35848309", "8771": "f25dc468-107f-4596-8fed-58f064b1ac9d",
    "9999": "334c285e-449f-43a9-8b4f-12cacfa8a26a",
}


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _player_provider_ids_side_effect(request: httpx.Request) -> httpx.Response:
    raw = request.url.params["provider_player_id"]
    requested_ids = raw.removeprefix("in.(").removesuffix(")").split(",")
    rows = [
        {"player_id": _LIVE_DEV_RESOLVED_PLAYER_IDS[pid], "provider_player_id": pid}
        for pid in requested_ids
        if pid in _LIVE_DEV_RESOLVED_PLAYER_IDS
    ]
    return httpx.Response(200, json=rows)


@pytest.mark.asyncio
@respx.mock
async def test_full_permanent_path_replays_gate_b_69_players_zero_provider_calls(monkeypatch):
    _env(monkeypatch)
    fixture = _load_fixture()

    # Ingestion-state row already eligible and due (as if a prior process
    # had already promoted/seeded it) -- this test's own focus is the
    # capture-through-persistence path, not the scheduling seed, which
    # tests/test_msf_postgame_worker.py already covers directly.
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"state": "eligible_for_postgame_check", "attempt_count": 0}])
    )
    claim_route = respx.patch(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"id": "row-1", "attempt_count": 0}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(200, json=[{"provider_game_id": MSF_GAME_ID}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[{"id": "league-1"}]))
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(200, json=[{"year": 2026, "start_date": "2026-09-01", "end_date": "2027-02-01"}])
    )
    raw_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_events").mock(
        return_value=httpx.Response(201, json=[{"id": "raw-evt-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(side_effect=_player_provider_ids_side_effect)
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    stats_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))
    # Deliberately NOT registering /rest/v1/players (POST) or
    # /rest/v1/player_identity_quarantine at all -- zero new players and
    # zero quarantines must hold structurally: any attempt would raise a
    # "no route matched" error and fail this test.

    fetch_calls: list = []

    async def _fake_fetch(*, season: str, msf_game_id: str) -> BoxscoreFetchResult:
        fetch_calls.append((season, msf_game_id))
        assert msf_game_id == MSF_GAME_ID
        return BoxscoreFetchResult(status="success", http_status=200, body=fixture)

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(
            supabase_client=client, game_id=CANONICAL_GAME_ID, fetch_boxscore=_fake_fetch
        )

    assert fetch_calls == [("2026-2027-regular", MSF_GAME_ID)]  # exactly one, real MSF season format
    assert result.outcome == "confirmed_complete"
    assert result.resolved_players == 69
    assert result.quarantined_players == 0
    assert result.persisted_rows == 69
    assert result.unchanged_rows == 0

    # Raw evidence preserved exactly once, carrying the real fixture body
    # byte-for-byte, before any player mutation.
    assert raw_insert_route.call_count == 1
    raw_body = json.loads(raw_insert_route.calls.last.request.content)
    assert raw_body["raw_payload"]["body"] == fixture
    assert raw_body["raw_payload"]["canonical_game_id"] == CANONICAL_GAME_ID

    # Every one of the 69 real players persisted, zero duplicates.
    assert stats_insert_route.call_count == 69
    persisted_player_ids = {
        json.loads(call.request.content)["player_id"] for call in stats_insert_route.calls
    }
    assert persisted_player_ids == set(_LIVE_DEV_RESOLVED_PLAYER_IDS.values())

    # Ingestion state advanced validated -> confirmed_complete.
    written_states = [
        json.loads(c.request.content).get("state")
        for c in claim_route.calls
        if json.loads(c.request.content).get("state")
    ]
    assert "validated" in written_states
    assert written_states[-1] == "confirmed_complete"


@pytest.mark.asyncio
@respx.mock
async def test_rerun_against_confirmed_complete_is_a_structural_no_op(monkeypatch):
    """Deterministic/idempotent rerun: once a game is confirmed_complete,
    a second invocation makes ZERO further calls of any kind -- no fetch,
    no raw write, no player activation, no stat persistence."""
    _env(monkeypatch)
    respx.get(f"{SUPABASE_URL}/rest/v1/game_postgame_ingestion_state").mock(
        return_value=httpx.Response(200, json=[{"state": "confirmed_complete", "attempt_count": 1}])
    )
    # Nothing else registered at all -- any further call of any kind
    # would raise a "no route matched" error.

    async def _fake_fetch(*, season: str, msf_game_id: str) -> BoxscoreFetchResult:
        raise AssertionError("fetch_boxscore must never be called for an already-finalized game")

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await run_msf_postgame_capture(
            supabase_client=client, game_id=CANONICAL_GAME_ID, fetch_boxscore=_fake_fetch
        )

    assert result.outcome == "already_finalized"
    assert result.state == "confirmed_complete"
