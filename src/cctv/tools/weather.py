"""Open-Meteo current conditions and forecast (no API key)."""

from __future__ import annotations

import json
from typing import Any

from cctv.tools._http import get_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

GET_WEATHER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Fetch measured current conditions and a short forecast from Open-Meteo. "
            "Prefer latitude/longitude from configured cameras when relevant. "
            "Use place for a named location when coordinates are unknown. "
            "Label this data as measured/forecast — distinct from what cameras show."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "WGS84 latitude. Prefer a configured camera when applicable.",
                },
                "longitude": {
                    "type": "number",
                    "description": "WGS84 longitude. Prefer a configured camera when applicable.",
                },
                "place": {
                    "type": "string",
                    "description": "Place name to geocode when coordinates are not provided.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def _tool_error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": None,
    }


def _geocode_place(place: str) -> tuple[float, float, str] | None:
    ok, data, error = get_json(
        GEOCODING_URL,
        params={"name": place, "count": 1, "language": "en", "format": "json"},
    )
    if not ok or not isinstance(data, dict):
        return None
    results = data.get("results") or []
    if not results:
        return None
    hit = results[0]
    try:
        lat = float(hit["latitude"])
        lon = float(hit["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    label = str(hit.get("name") or place)
    admin = hit.get("admin1")
    country = hit.get("country")
    if admin:
        label = f"{label}, {admin}"
    if country:
        label = f"{label}, {country}"
    return lat, lon, label


def _weather_code_label(code: int | None) -> str:
    labels = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
    }
    if code is None:
        return "Unknown"
    return labels.get(int(code), f"Weather code {code}")


def execute_get_weather(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    lat = args.get("latitude")
    lon = args.get("longitude")
    place = str(args.get("place") or "").strip()
    location_label = place

    if lat is None or lon is None:
        if not place:
            return _tool_error("Provide latitude/longitude or a place name")
        geocoded = _geocode_place(place)
        if geocoded is None:
            return _tool_error(f"Could not geocode place {place!r}", place=place)
        lat, lon, location_label = geocoded
    else:
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return _tool_error("Invalid latitude or longitude")

    ok, data, error = get_json(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "forecast_days": 3,
            "timezone": "auto",
        },
    )
    if not ok or not isinstance(data, dict):
        return _tool_error(error or "Weather service unavailable", place=location_label)

    current = data.get("current") or {}
    daily = data.get("daily") or {}
    forecast_days: list[dict[str, Any]] = []
    dates = daily.get("time") or []
    for index, day in enumerate(dates[:3]):
        forecast_days.append(
            {
                "date": day,
                "weather": _weather_code_label(
                    (daily.get("weather_code") or [None])[index]
                    if daily.get("weather_code")
                    else None
                ),
                "temp_max_c": (daily.get("temperature_2m_max") or [None])[index],
                "temp_min_c": (daily.get("temperature_2m_min") or [None])[index],
                "precipitation_mm": (daily.get("precipitation_sum") or [None])[index],
            }
        )

    payload = {
        "success": True,
        "location": location_label or f"{lat:.4f}, {lon:.4f}",
        "latitude": lat,
        "longitude": lon,
        "current": {
            "time": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "relative_humidity_percent": current.get("relative_humidity_2m"),
            "weather": _weather_code_label(current.get("weather_code")),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        },
        "forecast_days": forecast_days,
        "units": {
            "temperature": "°C",
            "wind_speed": "km/h",
            "precipitation": "mm",
        },
        "source": "Open-Meteo",
        "attribution": "Weather data by Open-Meteo (https://open-meteo.com); demo/research use.",
    }
    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": None,
    }
