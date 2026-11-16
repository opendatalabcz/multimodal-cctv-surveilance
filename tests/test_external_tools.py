import json
from unittest.mock import patch

import cctv.tools  # noqa: F401
from cctv.tools.registry import execute_tool
from cctv.tools.weather import execute_get_weather
from cctv.tools.web_search import execute_web_search


def test_web_search_normalizes_results() -> None:
    fake_rows = [
        {"title": "Traffic update", "href": "https://example.test/a", "body": "Slow on bridge"},
        {"title": "News", "url": "https://example.test/b", "snippet": "Clear elsewhere"},
    ]

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=5):
            assert query == "Prague traffic"
            assert max_results == 5
            yield from fake_rows

    with patch("ddgs.DDGS", FakeDDGS):
        result = execute_web_search({"query": "Prague traffic"})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is True
    assert payload["count"] == 2
    assert payload["results"][0]["url"] == "https://example.test/a"
    assert payload["results"][1]["snippet"] == "Clear elsewhere"
    assert result["image_path"] is None


def test_web_search_graceful_failure() -> None:
    class BrokenDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=5):
            raise RuntimeError("rate limited")

    with patch("ddgs.DDGS", BrokenDDGS):
        result = execute_web_search({"query": "hello"})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "unavailable" in payload["error"]


def test_web_search_empty_results() -> None:
    class EmptyDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=5):
            return iter([])

    with patch("ddgs.DDGS", EmptyDDGS):
        result = execute_web_search({"query": "nothing here"})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "No search results" in payload["error"]


def test_get_weather_by_coordinates() -> None:
    forecast = {
        "current": {
            "time": "2026-09-16T12:00",
            "temperature_2m": 18.2,
            "relative_humidity_2m": 55,
            "weather_code": 2,
            "wind_speed_10m": 12.0,
        },
        "daily": {
            "time": ["2026-09-16", "2026-09-17"],
            "weather_code": [2, 3],
            "temperature_2m_max": [20.0, 19.0],
            "temperature_2m_min": [12.0, 11.0],
            "precipitation_sum": [0.0, 1.2],
        },
    }

    with patch("cctv.tools.weather.get_json", return_value=(True, forecast, None)):
        result = execute_get_weather({"latitude": 50.08, "longitude": 14.41})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is True
    assert payload["current"]["temperature_c"] == 18.2
    assert payload["current"]["weather"] == "Partly cloudy"
    assert len(payload["forecast_days"]) == 2
    assert payload["source"] == "Open-Meteo"


def test_get_weather_geocodes_place() -> None:
    geocode = {
        "results": [
            {
                "name": "Prague",
                "latitude": 50.08,
                "longitude": 14.43,
                "admin1": "Prague",
                "country": "Czechia",
            }
        ]
    }
    forecast = {
        "current": {
            "time": "2026-09-16T12:00",
            "temperature_2m": 17.0,
            "relative_humidity_2m": 60,
            "weather_code": 0,
            "wind_speed_10m": 8.0,
        },
        "daily": {"time": ["2026-09-16"], "weather_code": [0], "temperature_2m_max": [18.0]},
    }

    def fake_get_json(url, *, params=None, headers=None, timeout=10):
        if "geocoding" in url:
            return True, geocode, None
        return True, forecast, None

    with patch("cctv.tools.weather.get_json", side_effect=fake_get_json):
        result = execute_get_weather({"place": "Prague"})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is True
    assert "Prague" in payload["location"]


def test_get_weather_service_failure() -> None:
    with patch("cctv.tools.weather.get_json", return_value=(False, None, "HTTP error 503")):
        result = execute_get_weather({"latitude": 1.0, "longitude": 2.0})

    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "503" in payload["error"]


def test_execute_tool_dispatches_registered_web_search() -> None:
    class StubDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=5):
            yield {"title": "Hit", "href": "https://example.test", "body": "Snippet"}

    with patch("ddgs.DDGS", StubDDGS):
        result = execute_tool("web_search", {"query": "test"})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is True
    assert payload["count"] == 1
