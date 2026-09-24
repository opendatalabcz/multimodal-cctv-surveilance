import json
from datetime import UTC, datetime
from unittest.mock import patch

import cctv.tools  # noqa: F401
from cctv.api.chat import run_chat_turn
from cctv.api.store import Conversation
from cctv.config.models import (
    AgentConfig,
    CameraAnalysis,
    CameraConfig,
    LocationConfig,
    SectorConfig,
    ToolsConfig,
)
from cctv.config.prompt import (
    build_system_prompt,
    build_welcome_message,
    build_welcome_suggestions,
)
from cctv.tools.registry import tool_names_for_config, tool_schemas_for_config
from cctv.utils.azure import AzureOpenAIConfig


def _fake_config() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        api_key="test-key",
        endpoint="https://example.openai.azure.com",
        model="gpt-test",
    )


def test_tool_names_all_toggles_off() -> None:
    names = tool_names_for_config(ToolsConfig())
    assert names == ("list_cameras", "get_camera_image")


def test_tool_names_internet_only() -> None:
    names = tool_names_for_config(ToolsConfig(internet=True))
    assert names == ("list_cameras", "get_camera_image", "web_search")


def test_tool_names_weather_only() -> None:
    names = tool_names_for_config(ToolsConfig(weather=True))
    assert "get_weather" in names
    assert "web_search" not in names


def test_tool_names_maps_only() -> None:
    names = tool_names_for_config(ToolsConfig(maps=True))
    assert "search_map" in names
    assert "reverse_geocode" in names
    assert "web_search" not in names


def test_tool_names_all_enabled() -> None:
    names = tool_names_for_config(ToolsConfig(internet=True, weather=True, maps=True))
    assert names == (
        "list_cameras",
        "get_camera_image",
        "web_search",
        "get_weather",
        "search_map",
        "reverse_geocode",
    )


def test_tool_schemas_reflect_toggle_combination() -> None:
    schemas = tool_schemas_for_config(ToolsConfig(internet=True, weather=False, maps=False))
    names = [item["function"]["name"] for item in schemas]
    assert names == ["list_cameras", "get_camera_image", "web_search"]


def test_prompt_camera_first_and_forecast_qualification() -> None:
    prompt = build_system_prompt(AgentConfig(tools=ToolsConfig(weather=True, internet=True)))
    assert "one camera per distinct place" in prompt
    assert "one get_camera_image call" in prompt
    assert "soft cap of about 10 images" in prompt
    assert "Clearly label measured/forecast data" in prompt
    assert "Do not use web_search as a weather API" in prompt
    assert "```cite" in prompt
    assert "The user only sees the images you cite" in prompt
    assert "Do not use sep, ..sep" in prompt
    assert "weather (get_weather): enabled" in prompt
    assert "internet search (web_search): enabled" in prompt


def test_prompt_disabled_capabilities() -> None:
    prompt = build_system_prompt(AgentConfig())
    assert "Do not claim you searched the web" in prompt
    assert "Do not quote measured forecasts" in prompt
    assert "Do not claim map or geocoding" in prompt


def test_prompt_routes_by_camera_scene_metadata() -> None:
    config = AgentConfig(
        cameras=[
            CameraConfig(
                id="road_cam",
                name="Road camera",
                source="101200",
                analysis=CameraAnalysis(
                    description="A multilane road carrying vehicles.",
                    scene_tags=["road", "intersection"],
                    source_fingerprint="abc",
                    analyzed_at="2026-09-16T12:00:00Z",
                ),
            )
        ]
    )
    prompt = build_system_prompt(config)
    assert "choose cameras whose scene tags and descriptions match" in prompt
    assert "scene_tags=road, intersection" in prompt
    assert "A multilane road carrying vehicles." in prompt
    assert "do not sample pedestrian, panorama, or airport views" in prompt


def test_run_chat_turn_reloads_tools_between_messages() -> None:
    conversation = Conversation(id="conv-1")
    configs = [
        AgentConfig(tools=ToolsConfig(internet=False)),
        AgentConfig(tools=ToolsConfig(internet=True, weather=True)),
    ]
    captured_tools: list[list[str]] = []

    def fake_chat(messages, *, config=None, system_prompt=None, tools=None, **kwargs):
        captured_tools.append([item["function"]["name"] for item in tools or []])
        return {
            "success": True,
            "analysis": "ok",
            "messages": list(messages) + [{"role": "assistant", "content": "ok"}],
            "image_paths": [],
        }

    with (
        patch("cctv.api.chat.load_agent_config", side_effect=configs),
        patch("cctv.api.chat.chat_with_tools", side_effect=fake_chat),
    ):
        run_chat_turn(conversation, "first question", config=_fake_config())
        run_chat_turn(conversation, "second question", config=_fake_config())

    assert captured_tools[0] == ["list_cameras", "get_camera_image"]
    assert captured_tools[1] == ["list_cameras", "get_camera_image", "web_search", "get_weather"]


def test_run_chat_turn_passes_max_tool_rounds() -> None:
    conversation = Conversation(id="conv-2")
    captured: dict = {}

    def fake_chat(*args, **kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "analysis": "done",
            "messages": [{"role": "assistant", "content": "done"}],
            "image_paths": [],
        }

    with (
        patch("cctv.api.chat.load_agent_config", return_value=AgentConfig()),
        patch("cctv.api.chat.chat_with_tools", side_effect=fake_chat),
    ):
        run_chat_turn(conversation, "hello", config=_fake_config())

    assert captured["max_tool_rounds"] == 16


def _analysis(description: str, tags: list[str]) -> CameraAnalysis:
    return CameraAnalysis(
        description=description,
        scene_tags=tags,
        source_fingerprint="fp",
        analyzed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _welcome_config(*sectors: tuple[str, str, list[str]]) -> AgentConfig:
    """One sector, one location and one analyzed camera per (name, description, tags) triple."""
    return AgentConfig(
        sectors=[SectorConfig(id=name.lower(), name=name) for name, _, _ in sectors],
        locations=[
            LocationConfig(id=f"loc_{name.lower()}", name=f"{name} centre", sector_id=name.lower())
            for name, _, _ in sectors
        ],
        cameras=[
            CameraConfig(
                id=f"cam_{name.lower()}",
                name="",
                source="101200",
                sector_id=name.lower(),
                location_id=f"loc_{name.lower()}",
                analysis=_analysis(description, tags),
            )
            for name, description, tags in sectors
        ],
    )


def test_welcome_suggestions_derive_from_scene_topics() -> None:
    config = _welcome_config(
        ("Prague", "Busy junction seen from above.", ["road", "intersection"]),
        ("Japan", "Airport apron with parked aircraft.", ["airport"]),
        ("Namibia", "Wildlife watering hole where elephants gather.", ["panorama"]),
    )
    assert build_welcome_suggestions(config) == [
        "What is the traffic like in Prague?",
        "How busy are the airports in Japan?",
        "Any animals out in Namibia right now?",
    ]


def test_welcome_suggestions_cap_at_three_places() -> None:
    config = _welcome_config(
        ("Prague", "Busy junction.", ["road"]),
        ("Japan", "Airport apron.", ["airport"]),
        ("Namibia", "Watering hole with animals.", ["panorama"]),
        ("Brno", "Pedestrian square.", ["pedestrian"]),
    )
    suggestions = build_welcome_suggestions(config)
    assert len(suggestions) == 3
    assert not any("Brno" in suggestion for suggestion in suggestions)


def test_welcome_suggestions_fall_back_when_cameras_are_unanalyzed() -> None:
    config = AgentConfig(
        locations=[LocationConfig(id="bridge", name="Charles Bridge", sector_id="unassigned")],
        cameras=[
            CameraConfig(
                id="cam_a",
                name="",
                source="101200",
                location_id="bridge",
                sector_id="unassigned",
            )
        ],
        tools=ToolsConfig(maps=True),
    )
    # No sector, so the location carries the question; no analysis, so the topic is generic.
    assert build_welcome_suggestions(config) == [
        "What can you see in Charles Bridge right now?",
        "Which cameras can you see?",
    ]


def test_welcome_message_summarizes_scope_without_repeating_suggestions() -> None:
    config = _welcome_config(
        ("Prague", "Busy junction seen from above.", ["road", "intersection"]),
        ("Japan", "Airport apron with parked aircraft.", ["airport"]),
    )
    text = build_welcome_message(config)
    assert "live CCTV cameras" in text
    assert "2 cameras across Prague and Japan." in text
    assert "traffic" not in text
    # Tool toggles are deliberately not advertised here.
    assert "weather" not in text.lower()


def test_welcome_without_cameras_points_at_config_and_offers_nothing() -> None:
    assert "No cameras are enabled yet" in build_welcome_message(AgentConfig())
    assert build_welcome_suggestions(AgentConfig()) == []
