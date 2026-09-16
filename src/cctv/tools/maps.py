"""OpenStreetMap Nominatim place search and reverse geocoding."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from cctv.tools._http import get_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "multimodal-cctv-surveillance/0.1.0 (research demo; thesis project)"
MAX_SEARCH_RESULTS = 5
CACHE_TTL_SECONDS = 3600

_rate_lock = threading.Lock()
_last_request_monotonic = 0.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


SEARCH_MAP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_map",
        "description": (
            "Search OpenStreetMap for a place name or address. "
            "Returns up to 5 matches with coordinates and display names. "
            "Use for place context — not turn-by-turn routing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Place name or address to search, e.g. Charles Bridge Prague.",
                }
            },
            "required": ["query"],
        },
    },
}

REVERSE_GEOCODE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "reverse_geocode",
        "description": (
            "Resolve coordinates to an OpenStreetMap address or area label. "
            "Useful for context around configured camera GPS."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "WGS84 latitude."},
                "longitude": {"type": "number", "description": "WGS84 longitude."},
            },
            "required": ["latitude", "longitude"],
        },
    },
}


def _cache_key(endpoint: str, params: dict[str, Any]) -> str:
    items = sorted((key, str(value)) for key, value in params.items())
    return endpoint + "?" + "&".join(f"{key}={value}" for key, value in items)


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        cached_at, payload = entry
        if now - cached_at > CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), payload)


def _nominatim_get(endpoint: str, params: dict[str, Any]) -> tuple[bool, list | dict | None, str | None]:
    key = _cache_key(endpoint, params)
    cached = _cache_get(key)
    if cached is not None:
        return True, cached.get("data"), None

    global _last_request_monotonic
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_monotonic
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        ok, data, error = get_json(
            f"{NOMINATIM_URL}/{endpoint}",
            params=params,
            headers={"User-Agent": USER_AGENT},
        )
        _last_request_monotonic = time.monotonic()

    if ok:
        _cache_set(key, {"data": data})
    return ok, data, error


def _tool_error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": None,
    }


def _normalize_search_hit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": str(row.get("display_name") or "").strip(),
        "latitude": float(row.get("lat")) if row.get("lat") is not None else None,
        "longitude": float(row.get("lon")) if row.get("lon") is not None else None,
        "type": row.get("type"),
        "category": row.get("class"),
    }


def execute_search_map(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    query = str(args.get("query") or "").strip()
    if not query:
        return _tool_error("Missing required argument: query")

    ok, data, error = _nominatim_get(
        "search",
        {
            "q": query,
            "format": "json",
            "limit": MAX_SEARCH_RESULTS,
            "addressdetails": 0,
        },
    )
    if not ok or not isinstance(data, list):
        return _tool_error(error or "Map search unavailable", query=query)

    results = [_normalize_search_hit(row) for row in data if isinstance(row, dict)]
    if not results:
        return _tool_error("No map results returned", query=query)

    payload = {
        "success": True,
        "query": query,
        "results": results,
        "count": len(results),
        "source": "OpenStreetMap Nominatim",
        "attribution": "© OpenStreetMap contributors (Nominatim); max 1 req/s; demo use.",
    }
    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": None,
    }


def execute_reverse_geocode(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    try:
        lat = float(args["latitude"])
        lon = float(args["longitude"])
    except (KeyError, TypeError, ValueError):
        return _tool_error("Missing or invalid latitude/longitude")

    ok, data, error = _nominatim_get(
        "reverse",
        {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
        },
    )
    if not ok or not isinstance(data, dict):
        return _tool_error(error or "Reverse geocoding unavailable", latitude=lat, longitude=lon)

    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    payload = {
        "success": True,
        "latitude": lat,
        "longitude": lon,
        "display_name": data.get("display_name"),
        "address": address,
        "source": "OpenStreetMap Nominatim",
        "attribution": "© OpenStreetMap contributors (Nominatim); max 1 req/s; demo use.",
    }
    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": None,
    }


def reset_nominatim_state() -> None:
    """Clear cache and rate-limit clock (for tests)."""
    global _last_request_monotonic
    with _cache_lock:
        _cache.clear()
    with _rate_lock:
        _last_request_monotonic = 0.0
