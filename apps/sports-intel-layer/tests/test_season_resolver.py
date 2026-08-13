"""Tests for app.persistence.seasons (Phase 3E-2).

The zero-match scenario is not hypothetical -- it's dev's actual current
state as of this writing (today 2026-08-13 is before the only seasons
row's start_date 2026-09-04), confirmed live against Supabase before
writing this code.
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.persistence.seasons import SeasonResolutionError, fetch_current_season_string, resolve_current_season_year

SUPABASE_URL = "https://test-project.supabase.co"


def _headers() -> dict:
    return {"Authorization": "Bearer test-key", "apikey": "test-key"}


def test_resolves_year_when_today_within_range():
    seasons = [{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}]
    assert resolve_current_season_year(date(2026, 9, 9), seasons) == 2026


def test_raises_when_today_is_before_the_only_seasons_row():
    # Dev's real current state, confirmed live 2026-08-13.
    seasons = [{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}]
    with pytest.raises(SeasonResolutionError):
        resolve_current_season_year(date(2026, 8, 13), seasons)


def test_raises_when_no_seasons_rows_at_all():
    with pytest.raises(SeasonResolutionError):
        resolve_current_season_year(date(2026, 9, 9), [])


def test_raises_on_overlapping_seasons_rather_than_guessing():
    seasons = [
        {"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"},
        {"year": 2027, "start_date": "2026-12-01", "end_date": "2027-06-01"},
    ]
    with pytest.raises(SeasonResolutionError):
        resolve_current_season_year(date(2027, 1, 1), seasons)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_current_season_string_builds_reg_suffix():
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(
        return_value=httpx.Response(200, json=[{"id": "league-1"}])
    )
    respx.get(f"{SUPABASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(
            200, json=[{"year": 2026, "start_date": "2026-09-04", "end_date": "2027-02-14"}]
        )
    )
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        result = await fetch_current_season_string(
            client, _headers(), league_code="nfl", today=date(2026, 9, 9)
        )
    assert result == "2026REG"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_current_season_string_raises_when_league_missing():
    respx.get(f"{SUPABASE_URL}/rest/v1/leagues").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=SUPABASE_URL) as client:
        with pytest.raises(SeasonResolutionError):
            await fetch_current_season_string(client, _headers(), league_code="nfl", today=date(2026, 9, 9))
