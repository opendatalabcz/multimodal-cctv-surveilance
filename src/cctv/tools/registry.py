"""OpenAI function-calling tool registry.

Schemas are what Azure sees. ``execute_tool`` is what the chat loop runs.
Low-level ``get_image`` stays registered for tests and notebooks; the default
model-facing set is ``list_cameras`` + ``get_camera_image``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cctv.config.models import ToolsConfig

ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    schema: dict[str, Any]
    execute: ToolExecutor


_TOOLS: dict[str, RegisteredTool] = {}
_BASE_NAMES: tuple[str, ...] = ("list_cameras", "get_camera_image")
_OPTIONAL_BY_FLAG: tuple[tuple[str, str], ...] = (
    ("internet", "web_search"),
    ("weather", "get_weather"),
    ("maps", "search_map"),
    ("maps", "reverse_geocode"),
)


def register_tool(schema: dict[str, Any], execute: ToolExecutor) -> None:
    name = schema["function"]["name"]
    _TOOLS[name] = RegisteredTool(schema=schema, execute=execute)


def tool_names_for_config(tools: ToolsConfig) -> tuple[str, ...]:
    names = list(_BASE_NAMES)
    flags = tools.model_dump()
    for flag, tool_name in _OPTIONAL_BY_FLAG:
        if flags.get(flag):
            names.append(tool_name)
    return tuple(names)


def tool_schemas(names: tuple[str, ...] | list[str] | None = None) -> list[dict[str, Any]]:
    selected = names if names is not None else _BASE_NAMES
    missing = [name for name in selected if name not in _TOOLS]
    if missing:
        raise KeyError(f"Unknown tools: {', '.join(missing)}")
    return [_TOOLS[name].schema for name in selected]


def tool_schemas_for_config(tools: ToolsConfig) -> list[dict[str, Any]]:
    return tool_schemas(tool_names_for_config(tools))


def default_tool_schemas() -> list[dict[str, Any]]:
    return tool_schemas(_BASE_NAMES)


def execute_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    registered = _TOOLS.get(name)
    if registered is None:
        return {
            "tool_content": json.dumps({"success": False, "error": f"Unknown tool: {name}"}),
            "image_path": None,
        }
    return registered.execute(args)
