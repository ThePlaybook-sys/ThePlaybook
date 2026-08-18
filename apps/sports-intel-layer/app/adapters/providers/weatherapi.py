"""WeatherAPI adapter (Volume 2 §8, Phase 3C-i).

Implements `WeatherAdapter` against WeatherAPI.com's documented
`forecast.json` contract. Same fixture-first discipline as Phase 3B: the
HTTP client is constructor-injected, every vendor-shape assumption is
tagged CONFIRMED/ASSUMED/DEFERRED (see
tests/fixtures/weatherapi/PROVENANCE.md), and nothing here writes to
Supabase -- persistence is Milestone F's job (Mac's explicit 3C scope
boundary, 2026-08-11).

**A real design gap surfaced while building this, flagged rather than
silently worked around:** `WeatherAdapter.fetch_weather(game_external_id,
kickoff)` (3A, already closed/signed off) takes no location -- but a
weather vendor call fundamentally needs one (a lat/lon or place name), and
no vendor can tell us a game's stadium. Changing the 3A ABC is out of this
adapter's scope. Fix applied here without touching the shared interface:
this concrete adapter takes an injected `location_for_game: Callable[[str],
str]` resolver at construction time. In production that resolver would be
backed by `games.stadium` (Milestone F concern, not built here); in tests
it's a plain dict lookup. Similarly, `WeatherConditions.is_dome` is
information no weather vendor has either (it's about our stadium, not
their forecast) -- this adapter always returns `is_dome=None` (Phase
3E-6, Option A: unknown from the vendor's own perspective, never
defaulted to False) and leaves the real value to whichever layer merges
in our own stadium data later (`app.workers.weather_worker`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from app.adapters.base import WeatherAdapter
from app.adapters.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.adapters.models import AdapterResponse, WeatherConditions

#: ASSUMED: WeatherAPI's documented auth-related error codes (`error.code`
#: in the response body). WeatherAPI is known to return HTTP 400 for most
#: key problems rather than a clean 401 -- distinguishing "bad key" from
#: "bad request" requires reading the body, not just the status code. Not
#: independently re-verified via a live fetch this session.
_AUTH_ERROR_CODES = {1002, 2006, 2007, 2008, 2009}

#: ASSUMED: forecast window requested. WeatherAPI's free tier is commonly
#: limited to a few days; not confirmed for this account tier (none
#: exists yet).
_FORECAST_DAYS = 3


def _parse_error_body(response: httpx.Response) -> dict | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        return data["error"]
    return None


class WeatherAPIWeatherAdapter(WeatherAdapter):
    provider_name = "weatherapi"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        location_for_game: Callable[[str], str],
    ):
        self._client = client
        self._api_key = api_key
        self._location_for_game = location_for_game

    async def fetch_weather(
        self, game_external_id: str, kickoff: datetime
    ) -> AdapterResponse[WeatherConditions]:
        location = self._location_for_game(game_external_id)

        try:
            response = await self._client.get(
                "/v1/forecast.json",
                params={
                    "key": self._api_key,
                    "q": location,
                    "days": _FORECAST_DAYS,
                    "aqi": "no",
                    "alerts": "no",
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"transport error calling forecast.json: {exc}", provider=self.provider_name
            ) from exc

        if response.status_code == 429:
            raise ProviderRateLimitError("rate limited", provider=self.provider_name)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider returned {response.status_code}", provider=self.provider_name
            )
        if response.status_code in (401, 400):
            error_body = _parse_error_body(response)
            if response.status_code == 401 or (
                error_body and error_body.get("code") in _AUTH_ERROR_CODES
            ):
                raise ProviderAuthError("invalid or missing API key", provider=self.provider_name)
            raise ProviderDataError(
                f"bad request: {error_body or response.text}", provider=self.provider_name
            )
        if response.status_code != 200:
            raise ProviderDataError(
                f"unexpected status {response.status_code}: {response.text}",
                provider=self.provider_name,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderDataError("response body was not valid JSON", provider=self.provider_name) from exc
        if not isinstance(data, dict):
            raise ProviderDataError("expected a JSON object", provider=self.provider_name)

        try:
            conditions, observed_at = self._normalize(data, game_external_id, kickoff)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderDataError(f"malformed forecast payload: {exc}", provider=self.provider_name) from exc

        return AdapterResponse(
            value=conditions,
            source=self.provider_name,
            provider_reported_at=observed_at,
        )

    def _normalize(
        self, data: dict, game_external_id: str, kickoff: datetime
    ) -> tuple[WeatherConditions, datetime | None]:
        """Picks the forecast hour closest to kickoff; falls back to
        `current` if kickoff is outside the requested forecast window
        (ASSUMED behavior -- there is no vendor-documented "closest hour"
        endpoint, this is our own selection logic over their hourly array).
        """
        hours: list[dict] = []
        for day in data.get("forecast", {}).get("forecastday", []):
            hours.extend(day.get("hour", []))

        chosen = None
        chosen_dt = None
        smallest_delta = None
        for hour in hours:
            hour_dt = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            delta = abs((hour_dt - kickoff).total_seconds())
            if smallest_delta is None or delta < smallest_delta:
                smallest_delta = delta
                chosen = hour
                chosen_dt = hour_dt

        if chosen is not None:
            conditions = WeatherConditions(
                game_external_id=game_external_id,
                temperature_f=chosen["temp_f"],
                wind_mph=chosen["wind_mph"],
                precipitation_pct=chosen.get("chance_of_rain"),
                conditions=chosen["condition"]["text"],
                is_dome=None,
            )
            return conditions, chosen_dt

        # Outside the forecast window entirely -- fall back to current
        # conditions rather than raising, since "no forecast that far out"
        # is expected behavior, not malformed data.
        current = data["current"]
        conditions = WeatherConditions(
            game_external_id=game_external_id,
            temperature_f=current["temp_f"],
            wind_mph=current["wind_mph"],
            precipitation_pct=current.get("precip_in"),
            conditions=current["condition"]["text"],
            is_dome=False,
        )
        last_updated = current.get("last_updated")
        observed_at = (
            datetime.strptime(last_updated, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            if last_updated
            else None
        )
        return conditions, observed_at
