"""OpenWeatherMap client (spec §4.2) — ambient thermal drift forecast.

Polled for the Context Agent. 5-minute cached. Uses the current-weather 2.5
endpoint so it works with a standard free API key (no One Call 3.0
subscription required). Mocks a tropical Puchong baseline when no API key is
set or the request fails — the loop never breaks.
"""
from __future__ import annotations

import time

import httpx

from ..config import settings
from ..schemas import AmbientContext

_TTL = 300.0  # seconds


class OpenWeatherClient:
    def __init__(self) -> None:
        self._cache: tuple[float, AmbientContext] | None = None

    async def get_ambient(self) -> AmbientContext:
        if self._cache and (time.monotonic() - self._cache[0]) < _TTL:
            return self._cache[1]

        if not settings.weather_configured:
            ctx = AmbientContext(
                air_temp_c=31.0,
                humidity_pct=82.0,
                description="tropical (mock — no OWM key)",
                source="mock",
            )
            self._cache = (time.monotonic(), ctx)
            return ctx

        params = {
            "lat": settings.owm_lat,
            "lon": settings.owm_lon,
            "appid": settings.openweather_api_key,
            "units": "metric",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(settings.openweather_base_url, params=params)
                r.raise_for_status()
                data = r.json()
            ctx = AmbientContext(
                air_temp_c=float(data["main"]["temp"]),
                humidity_pct=float(data["main"]["humidity"]),
                description=str(data["weather"][0]["description"]),
                source="openweather",
            )
            self._cache = (time.monotonic(), ctx)
            return ctx
        except Exception:
            # Network/API failure must not break the loop.
            ctx = AmbientContext(
                air_temp_c=31.0,
                humidity_pct=82.0,
                description="OWM unreachable (mock)",
                source="mock",
            )
            self._cache = (time.monotonic(), ctx)
            return ctx
