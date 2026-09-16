import json
from unittest.mock import patch

import cctv.tools  # noqa: F401
from cctv.api.chat import run_chat_turn
from cctv.api.store import Conversation
from cctv.config.models import AgentConfig, ToolsConfig
from cctv.config.prompt import build_system_prompt
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
    assert "weather (get_weather): enabled" in prompt
    assert "internet search (web_search): enabled" in prompt


def test_prompt_disabled_capabilities() -> None:
    prompt = build_system_prompt(AgentConfig())
    assert "Do not claim you searched the web" in prompt
    assert "Do not quote measured forecasts" in prompt
    assert "Do not claim map or geocoding" in prompt


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
