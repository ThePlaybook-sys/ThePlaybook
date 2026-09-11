"""Gate B 69-player REAL replay test (2026-09-11, HQ-authorized
"AUTOMATIC PLAYER IDENTITY + QUARANTINE BUILD", Section 3).

Uses ONLY the already-preserved, real MySportsFeeds NE@SEA boxscore
fixture (`docs/ops/fixtures/gate-b-msf-game-boxscore-163541-2026-09-10.json`,
game 163541, COMPLETED) -- no new MySportsFeeds call is made anywhere in
this file, matching the directive's explicit "zero-cost" requirement.

`_LIVE_DEV_RESOLVED_PLAYER_IDS` below is not synthetic -- it is the
exact, real (provider_player_id -> players.id) mapping this pass
confirmed live against the dev database immediately before writing this
test (`select provider_player_id, player_id from player_provider_ids
where provider_name = 'mysportsfeeds' and provider_player_id in (...)`,
run against all 69 real ids this fixture contains): **69/69 of this
fixture's real players already have a mysportsfeeds mapping, 69 of them
distinct**. That live fact is exactly what this test exercises: running
every one of the 69 real players from the real payload through the new
`activate_msf_player` wrapper must resolve every single one via the
REUSE path (Rule B) -- zero new players created, zero duplicate
mappings, zero false quarantines.

No route is registered for `/rest/v1/team_provider_ids`,
`/rest/v1/players` (POST), or `/rest/v1/player_identity_quarantine` --
Rule B's reuse path must never reach team resolution, player creation,
or quarantine at all. If the wrapper's implementation ever touched one
of those endpoints for an already-mapped provider_player_id, respx would
raise a "no route matched" error and this test would fail structurally,
not just by a wrong assertion.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.adapters.providers.mysportsfeeds_game_boxscore import parse_game_boxscore
from app.persistence.player_identity_activation import activate_msf_player

SUPABASE_URL = "https://test-project.supabase.co"
CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "ops"
    / "fixtures"
    / "gate-b-msf-game-boxscore-163541-2026-09-10.json"
)

#: Confirmed live against dev (project nhwjtsdebgiwskshzqiq), 2026-09-11,
#: immediately before this test was written -- see module docstring.
#: Every one of these 69 real provider_player_id values is drawn
#: directly from the Gate B fixture itself (no id here was invented).
_LIVE_DEV_RESOLVED_PLAYER_IDS: dict[str, str] = {
    "10027": "fde15cd4-e003-4b4f-80aa-5b03ed90edaa",
    "10040": "ddb2883e-cf1e-42d0-9af5-67058fd60efa",
    "108896": "38501d2e-31d8-4e4f-89af-e1eaa01ff435",
    "112112": "fdf01652-d62c-4138-8391-e82b6e99e4bd",
    "112158": "a92f6723-0701-409c-ac7e-67c2d055d893",
    "112190": "4c5fb5a4-9ca4-455f-af83-507a666f005a",
    "112203": "3168919b-4eed-4dae-92c8-85bbc8957df2",
    "112349": "a6ed9ee6-cea6-4044-abce-46d780f536d2",
    "112359": "5bd23f39-6f17-46d1-9476-fd46e1dcbe6d",
    "12738": "64568902-1ddd-4a36-b9d1-c54450b5fc74",
    "13280": "f07364ba-7242-45b3-9af6-a0d42557ff53",
    "133837": "00323ce5-d456-4c5a-a570-9bf97ac1c70d",
    "133850": "eb2217e4-bfc4-4c7a-8121-2af842e780a4",
    "133956": "dd17580e-ff37-4336-9248-6ee6b4ccde0c",
    "133972": "351ea8e3-89b5-473c-8ea8-2d04940448b6",
    "13412": "40258346-dd7e-4ff6-a159-a3e37aa4b5bb",
    "134254": "65ed5b33-7794-4876-9ee9-f1b5e1c558de",
    "134564": "80a69a07-94d0-4e84-9e1b-d6e45e997d51",
    "134586": "4d757809-13fa-49f5-88bc-7d636f5fd0ed",
    "14494": "94e9a1a1-bf78-4780-873e-c024527bb39e",
    "14732": "2c83b05f-8e14-4f38-ab0a-423c08f921f3",
    "14990": "36dc5f3e-1d7d-4fef-81a2-fa86bb789dfa",
    "15031": "4d4d0514-beb5-4900-8442-96d5c96bc394",
    "16129": "90e967b8-1356-4488-9627-e9cbe6688d37",
    "16516": "89447ac9-5090-4f19-94f0-745f30b7be7f",
    "16653": "a99d092e-43be-4ffa-82d6-0348cdba1aeb",
    "166661": "1c2e80f8-4f68-41b6-9bcb-3c816c963578",
    "166678": "296dedd2-86ac-44e2-98eb-31e07eb7520a",
    "166739": "52cd9323-d138-4b43-beaa-eef83d75eae9",
    "166763": "27516ef2-c1bb-4c83-9981-7786035247a5",
    "166773": "32cab57e-2a94-4474-bb2f-328587f32d0b",
    "166844": "5b3c7e3d-03af-404f-888e-a93cac7980ea",
    "166894": "b3a2321a-cf77-479d-ba1f-632d0dc18eaf",
    "166956": "d72f1a24-b20e-4d9f-9ba1-a1b9e76dc301",
    "16698": "940576c3-751d-48d5-98c1-c6d5eeaf0a87",
    "167667": "b574df7a-61d4-41b8-8cd1-2fa42cba50b3",
    "16786": "c9acc58a-0ff9-48fc-a9e8-8b6e7cc5170c",
    "168066": "1941b092-aa15-4863-9489-0c8b12212d8e",
    "168073": "cf2fa2be-983c-4053-a0a9-da77dbfcca6b",
    "16817": "00e21a2f-a03d-487e-97f4-1c0734a8f802",
    "207936": "366a5ed7-f725-4c1f-8b3b-c59ef613b24c",
    "207959": "be05232f-6149-4461-9970-d50a039a9e2e",
    "207999": "7ab0bc29-5b95-46b1-986d-ef0218993520",
    "208124": "59e98077-2676-4271-8875-b664c16e4667",
    "30251": "9580cbbb-ca59-4782-8355-f598dd919a0b",
    "30398": "36bf6b7e-68d9-4a55-987d-235bb046fa8a",
    "30442": "5f92bf4a-a6ac-4c19-8e27-112e31a96f38",
    "30602": "d2cc6d68-7748-4e22-8ca2-2d2e6b231aed",
    "30820": "8f6551bc-095e-4136-b892-895c76ebab6e",
    "30942": "d76ee386-c5ec-4aa9-bf72-ef30a8518d14",
    "30974": "b647cc0a-9773-4311-955f-e4adba1463c3",
    "31103": "d7cb37dd-547f-435a-8b3d-6e3cd42dce2c",
    "39267": "89b94fb5-a999-4b6e-8153-de0280e5e3cc",
    "39287": "5b38f7bc-df80-4fa9-8664-2361f146e840",
    "39293": "3d915ba3-3138-4f48-86c6-a92bedee21bc",
    "47382": "2240479a-561e-4318-ac46-ae09ad674977",
    "48151": "757ef996-57eb-4370-8acd-45db1c3b9110",
    "48291": "c86d87a9-4a97-4878-a99a-e7e4321484be",
    "55455": "db0abc28-7309-4dd2-ab4e-25d6cac15a19",
    "6696": "49b95de1-1331-447d-8bac-d5f23d861452",
    "7266": "b772844c-1cd5-4687-ad29-7c515ef35ee3",
    "7876": "ad24d682-1b40-4a80-adc3-c5c88490cb0e",
    "79743": "90d749de-abc0-4aa3-b46f-2342e606acdf",
    "79755": "12be989d-29b0-4a9a-97e0-98c2b05949a5",
    "79758": "c9b7de10-b380-45e4-90a3-f98444dce258",
    "79775": "30e77e0a-ee6c-42f2-9802-a667961ddf9f",
    "79846": "0683e33b-82b4-4d2c-89ee-675c35848309",
    "8771": "f25dc468-107f-4596-8fed-58f064b1ac9d",
    "9999": "334c285e-449f-43a9-8b4f-12cacfa8a26a",
}


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _player_provider_ids_side_effect(request: httpx.Request) -> httpx.Response:
    """Mirrors the real `player_provider_ids` table's own PostgREST
    `in.(...)` query shape -- returns exactly the rows the live dev
    database actually holds for whichever single provider_player_id this
    call asked about."""
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
async def test_all_69_real_gate_b_players_resolve_via_reuse_zero_provider_calls():
    fixture = _load_fixture()
    adapter_response = parse_game_boxscore(fixture)
    assert len(adapter_response.value) == 69  # Gate B's own confirmed real count

    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        side_effect=_player_provider_ids_side_effect
    )
    # Deliberately NOT registering team_provider_ids / players (POST) /
    # player_identity_quarantine routes at all -- see module docstring.

    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        results = []
        for line in adapter_response.value:
            result = await activate_msf_player(
                client,
                _headers(),
                game_id=CANONICAL_GAME_ID,
                provider_player_id=line.player_external_id,
                provider_team_id=line.team,
                raw_player_name=line.player_name,
                # The adapter's PlayerStatLine does not carry position --
                # see this pass's own STOP AND REPORT for why that's a
                # named blocker for the future permanent boxscore worker,
                # not something this replay can supply from the fixture.
                raw_position=None,
            )
            results.append((line.player_external_id, result))

    assert len(results) == 69
    for provider_player_id, result in results:
        assert result.outcome == "resolved", (
            f"expected REUSE for real provider_player_id {provider_player_id}, "
            f"got {result.outcome} ({result.conflict_type})"
        )
        assert result.player_id == _LIVE_DEV_RESOLVED_PLAYER_IDS[provider_player_id]

    resolved_player_ids = {result.player_id for _, result in results}
    assert len(resolved_player_ids) == 69  # 69 distinct canonical players, zero collapsed/duplicated
