"""End-to-end dry run of canonical reconciliation against dev's REAL shape
(2026-09-15, HQ-authorized "SPORTSDATAIO CANONICAL GAME RECONCILIATION").

This is the proof that the authorized full-season Schedule refresh is safe to
run. It drives the real `persist_schedule_entries` and asserts what it does to a
canonical table shaped exactly like dev's, verified live before this was
written:

  - 23 canonical games, of which 16 are Week 1 games finalized on 2026-09-15
    with real scores, plus 3 future manual-seed games and 4 legacy fixtures
    that store full team names;
  - **zero** `sportsdataio` GAME mappings -- every game is mapped only under
    `balldontlie` / `mysportsfeeds` / `the_odds_api`;
  - **32/32** `sportsdataio` TEAM mappings, so team identity resolves.

Before reconciliation, that combination meant every entry resolved as not-found
and would have been inserted, duplicating all 19 resolvable games.

**No SportsDataIO production game ids are fabricated for live rows.** GameKeys
here are obviously synthetic (`TEST-GK-*`); the canonical game ids are likewise
placeholders, not the real dev UUIDs. What is reproduced is the SHAPE -- team
text, kickoff times, finalized state, and the absence of SportsDataIO mappings
-- not invented provider identity.

Zero provider calls: the SportsDataIO adapter is never constructed here; entries
are built directly and every Supabase read/write is respx-mocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.adapters.models import AdapterResponse, ScheduleEntry
from app.persistence.schedule import persist_schedule_entries

SUPABASE_URL = "https://test-project.supabase.co"

WK1_KICKOFF = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
WK2_KICKOFF = datetime(2026, 9, 18, 0, 15, tzinfo=timezone.utc)
WK5_KICKOFF = datetime(2026, 10, 11, 20, 25, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _entry(external_id, home, away, start, week=1) -> ScheduleEntry:
    return ScheduleEntry(
        game_external_id=external_id,
        home_team=home,
        away_team=away,
        scheduled_start=start,
        stadium="Test Stadium",
        status="scheduled",  # what SportsDataIO still says about a played game
        season_type="regular",
        week=week,
        venue_lat=None,
        venue_long=None,
        venue_type=None,
    )


def _canonical(game_id, home, away, start, *, finalized=False):
    return {
        "id": game_id,
        "home_team": home,
        "away_team": away,
        "scheduled_start": start.isoformat(),
        "finalized_at": "2026-09-15T20:16:13.594649+00:00" if finalized else None,
    }


#: Dev's real canonical shape, abbreviated to the cases that matter.
DEV_CANONICAL = [
    # Week 1, finalized 2026-09-15 with real scores.
    _canonical("wk1-ne-sea", "SEA", "NE", WK1_KICKOFF, finalized=True),
    _canonical("wk1-sf-lar", "LAR", "SF", WK1_KICKOFF + timedelta(days=1), finalized=True),
    # Future manual-seed game, not finalized.
    _canonical("wk5-chi-gb", "GB", "CHI", WK5_KICKOFF),
    # Legacy fixture storing full team names -- must never match.
    _canonical("legacy-1", "Seattle Seahawks", "New England Patriots", WK1_KICKOFF),
]

#: 32/32 team mappings exist in dev; these are the ones this fixture needs.
DEV_TEAM_ROWS = [
    {"team_id": f"team-{t}", "provider_team_id": t}
    for t in ("SEA", "NE", "LAR", "SF", "GB", "CHI", "KC", "BUF")
]


def _mock_dev(*, canonical=None, team_rows=None, mapped_game_ids=()):
    """Mocks dev's state: no SportsDataIO game mappings, real team mappings."""
    canonical = DEV_CANONICAL if canonical is None else canonical
    team_rows = DEV_TEAM_ROWS if team_rows is None else team_rows

    def _gpi_get(request: httpx.Request) -> httpx.Response:
        # resolve_game_ids asks with provider_game_id; the reconciliation
        # candidate load and the conflict check do not.
        if "provider_game_id" in request.url.params:
            return httpx.Response(200, json=[])
        if "game_id" in request.url.params:
            return httpx.Response(200, json=[])  # no existing sdio mapping
        return httpx.Response(200, json=[{"game_id": g} for g in mapped_game_ids])

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_gpi_get)
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=team_rows)
    )

    def _games_get(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("sport") == "eq.nfl":
            return httpx.Response(200, json=canonical)
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_games_get)

    def _patch(request: httpx.Request) -> httpx.Response:
        game_id = request.url.params["id"].removeprefix("eq.")
        finalized = any(c["id"] == game_id and c["finalized_at"] for c in canonical)
        if request.url.params.get("finalized_at") == "is.null" and finalized:
            return httpx.Response(200, json=[])  # terminal guard, as Postgres would
        return httpx.Response(200, json=[{"id": game_id}])

    patch_route = respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(side_effect=_patch)
    created = iter(f"new-{i}" for i in range(1, 400))
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        side_effect=lambda request: httpx.Response(201, json=[{"id": next(created)}])
    )
    return insert_route, patch_route, link_route


# --------------------------------------------------------------------------
# 1. Existing Week 1 games -- link, never duplicate.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_existing_finalized_week1_games_link_instead_of_duplicating():
    """The headline proof. Before this change these two entries inserted two new
    canonical rows; now they attach the GameKey to the finalized rows."""
    insert_route, _, link_route = _mock_dev()
    entries = [
        _entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF),
        _entry("TEST-GK-WK1-B", "LAR", "SF", WK1_KICKOFF + timedelta(days=1)),
    ]
    result = await persist_schedule_entries(
        AdapterResponse(value=entries, source="sportsdataio")
    )

    assert result.reconciled == 2
    assert result.reconciled_exact == 2
    assert result.created == 0
    assert not insert_route.called  # NOT ONE duplicate row
    linked = [json.loads(c.request.content) for c in link_route.calls]
    assert {b["game_id"] for b in linked} == {"wk1-ne-sea", "wk1-sf-lar"}


@pytest.mark.asyncio
@respx.mock
async def test_a_reconciled_finalized_game_keeps_its_terminal_state():
    """It links AND stays final: the status-carrying PATCH is guarded, and the
    follow-up patch omits `status` entirely, so the score and terminal status
    written by canonical finalization survive."""
    _, patch_route, _ = _mock_dev()
    await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF)], source="sportsdataio"
        )
    )

    bodies = [json.loads(c.request.content) for c in patch_route.calls]
    guarded = [
        b for b, c in zip(bodies, patch_route.calls)
        if c.request.url.params.get("finalized_at") == "is.null"
    ]
    retained = [
        b for b, c in zip(bodies, patch_route.calls)
        if c.request.url.params.get("finalized_at") is None
    ]
    assert guarded and all("status" in b for b in guarded)  # attempted...
    assert retained and all("status" not in b for b in retained)  # ...never landed
    # final_score / finalized_at are not writable from this path at all.
    assert all("final_score" not in b and "finalized_at" not in b for b in bodies)


# --------------------------------------------------------------------------
# 2. Existing future/manual-seed game.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_an_existing_future_manual_seed_game_links_instead_of_duplicating():
    insert_route, _, link_route = _mock_dev()
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK5", "GB", "CHI", WK5_KICKOFF, week=5)],
            source="sportsdataio",
        )
    )

    assert result.reconciled == 1 and result.created == 0
    assert not insert_route.called
    assert json.loads(link_route.calls.last.request.content)["game_id"] == "wk5-chi-gb"


# --------------------------------------------------------------------------
# 3. Genuinely missing game -- Week 2, the whole point of the refresh.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_genuinely_missing_week2_game_is_still_inserted():
    insert_route, _, _ = _mock_dev()
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK2", "KC", "BUF", WK2_KICKOFF, week=2)],
            source="sportsdataio",
        )
    )

    assert result.created == 1 and result.reconciled == 0
    assert insert_route.called
    assert json.loads(insert_route.calls.last.request.content)["week"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_a_mixed_season_reconciles_and_inserts_in_the_same_run():
    """What the authorized refresh actually looks like: some entries already
    exist, some do not, and each takes the right path."""
    insert_route, _, _ = _mock_dev()
    entries = [
        _entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF),
        _entry("TEST-GK-WK1-B", "LAR", "SF", WK1_KICKOFF + timedelta(days=1)),
        _entry("TEST-GK-WK5", "GB", "CHI", WK5_KICKOFF, week=5),
        _entry("TEST-GK-WK2", "KC", "BUF", WK2_KICKOFF, week=2),
    ]
    result = await persist_schedule_entries(
        AdapterResponse(value=entries, source="sportsdataio")
    )

    assert result.reconciled == 3  # the three that already existed
    assert result.created == 1  # only the genuinely missing Week 2 game
    assert insert_route.call_count == 1


# --------------------------------------------------------------------------
# 4. Ambiguity.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_an_ambiguous_match_is_skipped_and_reported_never_duplicated():
    """Two existing canonical rows for the same matchup and kickoff (exactly the
    duplicate state this change prevents). The entry is refused: nothing linked,
    nothing inserted, and the conflict is reported."""
    duplicated = [
        _canonical("dupe-a", "SEA", "NE", WK1_KICKOFF),
        _canonical("dupe-b", "SEA", "NE", WK1_KICKOFF),
    ]
    insert_route, _, link_route = _mock_dev(canonical=duplicated)
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF)], source="sportsdataio"
        )
    )

    assert result.reconciled == 0
    assert result.created == 0
    assert not insert_route.called and not link_route.called
    assert len(result.ambiguous) == 1
    assert "dupe-a" in result.ambiguous[0] and "dupe-b" in result.ambiguous[0]


# --------------------------------------------------------------------------
# 5. Timestamp tolerance boundary, end to end.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_kickoff_inside_tolerance_reconciles():
    insert_route, _, _ = _mock_dev()
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF + timedelta(minutes=10))],
            source="sportsdataio",
        )
    )
    assert result.reconciled_within_tolerance == 1
    assert not insert_route.called


@pytest.mark.asyncio
@respx.mock
async def test_a_five_hour_skew_is_not_absorbed_and_surfaces_as_a_new_row():
    """An Eastern-local vs UTC mix-up must never be silently treated as the same
    game. It fails to match, which is the loud outcome."""
    insert_route, _, _ = _mock_dev()
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF - timedelta(hours=5))],
            source="sportsdataio",
        )
    )
    assert result.reconciled == 0
    assert result.created == 1 and insert_route.called


# --------------------------------------------------------------------------
# 6. Idempotency and uniqueness.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_second_run_updates_instead_of_reconciling_or_inserting():
    """Once mapped, identity is by GameKey forever -- the second run never
    reaches the reconciliation path at all."""

    def _gpi_get(request: httpx.Request) -> httpx.Response:
        if "provider_game_id" in request.url.params:
            return httpx.Response(
                200, json=[{"game_id": "wk1-ne-sea", "provider_game_id": "TEST-GK-WK1-A"}]
            )
        return httpx.Response(200, json=[])

    respx.get(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(side_effect=_gpi_get)
    link_route = respx.post(f"{SUPABASE_URL}/rest/v1/game_provider_ids").mock(
        return_value=httpx.Response(201)
    )
    team_route = respx.get(f"{SUPABASE_URL}/rest/v1/team_provider_ids").mock(
        return_value=httpx.Response(200, json=DEV_TEAM_ROWS)
    )
    games_get = respx.get(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=DEV_CANONICAL)
    )
    respx.patch(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(200, json=[])  # finalized: terminal guard holds
    )
    insert_route = respx.post(f"{SUPABASE_URL}/rest/v1/games").mock(
        return_value=httpx.Response(201, json=[{"id": "should-not-happen"}])
    )

    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF)], source="sportsdataio"
        )
    )

    assert result.created == 0 and result.reconciled == 0
    assert not insert_route.called
    assert not link_route.called
    # Everything already mapped means the reconciliation reads are skipped too.
    assert not team_route.called and not games_get.called


@pytest.mark.asyncio
@respx.mock
async def test_two_entries_cannot_both_claim_the_same_canonical_game():
    """Proves `UNIQUE (game_id, provider_name)` can't even be reached: once an
    entry reconciles onto a game, that game is marked mapped for the rest of the
    run, so a second entry is not allowed to claim it."""
    insert_route, _, link_route = _mock_dev()
    entries = [
        _entry("TEST-GK-FIRST", "SEA", "NE", WK1_KICKOFF),
        _entry("TEST-GK-SECOND", "SEA", "NE", WK1_KICKOFF),
    ]
    result = await persist_schedule_entries(
        AdapterResponse(value=entries, source="sportsdataio")
    )

    assert result.reconciled == 1  # exactly one claimed it
    assert result.created == 1  # the other became its own row, never a rewrite
    assert insert_route.call_count == 1
    # Two links total: one reconciling onto the existing game, one for the new
    # row. Crucially the existing game is linked ONCE -- never rewritten.
    linked = [json.loads(c.request.content) for c in link_route.calls]
    onto_existing = [b for b in linked if b["game_id"] == "wk1-ne-sea"]
    assert len(onto_existing) == 1
    assert onto_existing[0]["provider_game_id"] == "TEST-GK-FIRST"


@pytest.mark.asyncio
@respx.mock
async def test_unresolvable_teams_are_reported_and_never_matched_by_name():
    """A team with no authoritative mapping cannot be reconciled on name text.
    The entry still persists as a new game -- it is simply never matched."""
    insert_route, _, link_route = _mock_dev(team_rows=[])
    result = await persist_schedule_entries(
        AdapterResponse(
            value=[_entry("TEST-GK-WK1-A", "SEA", "NE", WK1_KICKOFF)], source="sportsdataio"
        )
    )

    assert result.unresolved_teams == ["TEST-GK-WK1-A (NE@SEA)"]
    assert result.reconciled == 0  # nothing matched on name text
    assert result.created == 1 and insert_route.called
    # The only link written is the NEW game's own mapping, not a reconciliation
    # onto the existing SEA/NE row.
    assert json.loads(link_route.calls.last.request.content)["game_id"] == "new-1"
