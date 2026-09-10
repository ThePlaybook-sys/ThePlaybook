"""End-to-end tests: real Gate B fixture -> mysportsfeeds_game_boxscore
adapter -> app.persistence.player_stats.persist_player_stats (MANSA
Phase 8 Player-Game Persistence Design + Implementation Pass, 2026-09-10).

Proves the full pipeline HQ asked this pass to prove, against the real,
committed Gate B payload (`docs/ops/fixtures/gate-b-msf-game-boxscore-
163541-2026-09-10.json`) -- NOT synthetic data:

- real player stat extraction survives all the way to the persisted row
- game_id assignment resolves via the existing game_provider_ids mapping
  (already real, already persisted for MSF game 163541 -- Gate B
  preflight)
- provider ID resolution: some of the 69 real players resolve to
  canonical players, others correctly do not
- unresolved identity is reported explicitly, never guessed/auto-created
- these rows are game-scoped, never season-scoped (no season_id anywhere)
- the confirmed-unreliable snapCounts/gamesStarted fields are persisted
  verbatim but flagged, never silently trusted as real participation
- repeat processing of the identical real payload creates zero duplicate
  rows (idempotency) -- and a genuine correction inserts exactly one new
  row per changed player, never mutates the prior one

No live MySportsFeeds call is made anywhere in this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.adapters.providers.mysportsfeeds_game_boxscore import parse_game_boxscore
from app.persistence.player_stats import persist_player_stats

SUPABASE_URL = "https://test-project.supabase.co"
CANONICAL_GAME_ID = "280e7b05-1215-42c7-9bba-8a3631b86f26"
MSF_GAME_ID = "163541"

# A deliberately PARTIAL resolution map -- mirrors the real dev DB, where
# 22 of these 69 real MSF player ids already resolve to canonical players
# (Gate B's own reported identity-coverage finding) and the rest do not.
# Drake Maye (133837) and Rhamondre Stevenson (31103) are real players in
# this fixture -- used here as the "resolved" sample; every other real id
# in the fixture is deliberately left unmapped to prove partial coverage
# is handled correctly, not silently papered over.
_RESOLVED_PLAYER_IDS = {
    "133837": "player-drake-maye",
    "31103": "player-rhamondre-stevenson",
}

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "ops"
    / "fixtures"
    / "gate-b-msf-game-boxscore-163541-2026-09-10.json"
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _headers_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _mock_game_identity():
    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(
            200, json=[{"game_id": CANONICAL_GAME_ID, "provider_game_id": MSF_GAME_ID}]
        )
    )


def _mock_player_identity():
    respx.get(f"{SUPABASE_URL}/rest/v1/player_provider_ids").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"player_id": pid, "provider_player_id": provider_id}
                for provider_id, pid in _RESOLVED_PLAYER_IDS.items()
            ],
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_real_stats_persist_with_correct_game_id_and_resolved_identity(monkeypatch):
    _headers_env(monkeypatch)
    _mock_game_identity()
    _mock_player_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    adapter_response = parse_game_boxscore(_load_fixture())
    result = await persist_player_stats(adapter_response, provider_name="mysportsfeeds")

    # Exactly the 2 resolved players inserted -- the other 67 real, genuine
    # players in this payload are correctly unresolved, not silently
    # dropped or guessed.
    assert result.inserted == 2
    assert insert_route.call_count == 2

    bodies = [json.loads(call.request.content) for call in insert_route.calls]
    game_ids = {b["game_id"] for b in bodies}
    assert game_ids == {CANONICAL_GAME_ID}  # game-scoped, never season-scoped
    player_ids = {b["player_id"] for b in bodies}
    assert player_ids == set(_RESOLVED_PLAYER_IDS.values())

    maye_row = next(b for b in bodies if b["player_id"] == "player-drake-maye")
    assert maye_row["stats"]["passing"]["passYards"] == 178
    assert maye_row["stats"]["rushing"]["rushYards"] == 47
    assert "season_id" not in maye_row  # never confused with a season-aggregate row


@pytest.mark.asyncio
@respx.mock
async def test_unresolved_players_are_reported_explicitly_not_guessed(monkeypatch):
    """67 of the 69 real players in this fixture have no player_provider_ids
    mapping in this test's identity map -- every one must be reported by
    provider id, never matched by name, never auto-created."""
    _headers_env(monkeypatch)
    _mock_game_identity()
    _mock_player_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))
    players_insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/players").mock(return_value=httpx.Response(201))

    adapter_response = parse_game_boxscore(_load_fixture())
    result = await persist_player_stats(adapter_response, provider_name="mysportsfeeds")

    assert len(result.unresolved_players) == 67
    assert set(result.unresolved_players).isdisjoint(_RESOLVED_PLAYER_IDS.keys())
    assert players_insert_route.call_count == 0  # never auto-created


@pytest.mark.asyncio
@respx.mock
async def test_zero_snap_counts_are_persisted_but_never_treated_as_reliable(monkeypatch):
    """The persisted row must carry the real (zero) snapCounts value --
    provenance-preserving -- AND the structural unreliable-fields marker,
    so nothing downstream can mistake this zero for confirmed zero
    participation."""
    _headers_env(monkeypatch)
    _mock_game_identity()
    _mock_player_identity()
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=[]))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    adapter_response = parse_game_boxscore(_load_fixture())
    await persist_player_stats(adapter_response, provider_name="mysportsfeeds")

    bodies = [json.loads(call.request.content) for call in insert_route.calls]
    maye_row = next(b for b in bodies if b["player_id"] == "player-drake-maye")
    assert maye_row["stats"]["snapCounts"] == {"offenseSnaps": 0, "defenseSnaps": 0, "specialTeamSnaps": 0}
    assert maye_row["stats"]["_unreliable_fields"] == ["snapCounts", "miscellaneous.gamesStarted"]


@pytest.mark.asyncio
@respx.mock
async def test_repeat_processing_of_the_identical_real_payload_creates_no_duplicates(monkeypatch):
    """Idempotency, proven with the REAL payload: processing the exact
    same Gate B fixture a second time (e.g. a redeploy re-running the
    diagnostic hook, or a future reconciliation pass re-reading the same
    game_events evidence row) must insert nothing new for players whose
    stats have not changed."""
    _headers_env(monkeypatch)
    _mock_game_identity()
    _mock_player_identity()
    # Simulate that both resolved players were already persisted from a
    # prior run, with the exact stats this fixture will produce.
    fixture = _load_fixture()
    first_pass_response = parse_game_boxscore(fixture)
    maye_line = next(line for line in first_pass_response.value if line.player_external_id == "133837")
    stevenson_line = next(line for line in first_pass_response.value if line.player_external_id == "31103")
    existing_rows = [
        {"id": "row-maye", "game_id": CANONICAL_GAME_ID, "player_id": "player-drake-maye",
         "stats": maye_line.stats, "created_at": "2026-09-10T13:00:13Z"},
        {"id": "row-stevenson", "game_id": CANONICAL_GAME_ID, "player_id": "player-rhamondre-stevenson",
         "stats": stevenson_line.stats, "created_at": "2026-09-10T13:00:13Z"},
    ]

    async def _latest_row(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        player_id = params.get("player_id", "").removeprefix("eq.")
        matches = [r for r in existing_rows if r["player_id"] == player_id]
        return httpx.Response(200, json=matches[:1])

    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(side_effect=_latest_row)
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    result = await persist_player_stats(first_pass_response, provider_name="mysportsfeeds")

    assert result.inserted == 0
    assert result.unchanged == 2
    assert insert_route.call_count == 0  # no corrupt duplicates, no PATCH/PUT either


@pytest.mark.asyncio
@respx.mock
async def test_a_genuine_correction_inserts_exactly_one_new_row_never_mutates_the_old_one(monkeypatch):
    """Correction-safety, proven with the real payload: if MySportsFeeds
    later revises this completed game's boxscore, re-processing produces
    exactly one new row per changed player -- the prior observation is
    never touched (no PATCH/PUT route is registered, so respx would raise
    if this module ever attempted one)."""
    _headers_env(monkeypatch)
    _mock_game_identity()
    _mock_player_identity()
    existing = [
        {
            "id": "row-maye-old",
            "game_id": CANONICAL_GAME_ID,
            "player_id": "player-drake-maye",
            "stats": {"passing": {"passYards": 150}},  # a different, earlier observation
            "created_at": "2026-09-10T12:00:00Z",
        }
    ]
    respx.get(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(200, json=existing))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/player_stats").mock(return_value=httpx.Response(201))

    adapter_response = parse_game_boxscore(_load_fixture())
    result = await persist_player_stats(adapter_response, provider_name="mysportsfeeds")

    # Both resolved players insert: Maye because the real fixture stats
    # differ from the stale "existing" row, Stevenson because no prior
    # row exists for him at all in this mock.
    assert result.inserted == 2
    bodies = [json.loads(call.request.content) for call in insert_route.calls]
    maye_row = next(b for b in bodies if b["player_id"] == "player-drake-maye")
    assert maye_row["stats"]["passing"]["passYards"] == 178  # the real, current value
    assert all(call.request.method == "POST" for call in insert_route.calls)  # never PATCH/PUT
