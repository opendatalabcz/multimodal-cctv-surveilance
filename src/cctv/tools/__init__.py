from __future__ import annotations

from typing import Any

from cctv.tools.get_camera import GET_CAMERA_IMAGE_TOOL, execute_get_camera_image, resolve_camera
from cctv.tools.get_image import GET_IMAGE_TOOL, execute_get_image
from cctv.tools.list_cameras import LIST_CAMERAS_TOOL, execute_list_cameras
from cctv.tools.maps import (
    REVERSE_GEOCODE_TOOL,
    SEARCH_MAP_TOOL,
    execute_reverse_geocode,
    execute_search_map,
)
from cctv.tools.registry import (
    default_tool_schemas,
    execute_tool,
    register_tool,
    tool_names_for_config,
    tool_schemas,
    tool_schemas_for_config,
)
from cctv.tools.weather import GET_WEATHER_TOOL, execute_get_weather
from cctv.tools.web_search import WEB_SEARCH_TOOL, execute_web_search


def _execute_get_image_args(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    return execute_get_image(str(args.get("source") or ""))


register_tool(LIST_CAMERAS_TOOL, execute_list_cameras)
register_tool(GET_CAMERA_IMAGE_TOOL, execute_get_camera_image)
register_tool(GET_IMAGE_TOOL, _execute_get_image_args)
register_tool(WEB_SEARCH_TOOL, execute_web_search)
register_tool(GET_WEATHER_TOOL, execute_get_weather)
register_tool(SEARCH_MAP_TOOL, execute_search_map)
register_tool(REVERSE_GEOCODE_TOOL, execute_reverse_geocode)

__all__ = [
    "GET_CAMERA_IMAGE_TOOL",
    "GET_IMAGE_TOOL",
    "GET_WEATHER_TOOL",
    "LIST_CAMERAS_TOOL",
    "REVERSE_GEOCODE_TOOL",
    "SEARCH_MAP_TOOL",
    "WEB_SEARCH_TOOL",
    "default_tool_schemas",
    "execute_get_camera_image",
    "execute_get_image",
    "execute_get_weather",
    "execute_list_cameras",
    "execute_reverse_geocode",
    "execute_search_map",
    "execute_tool",
    "execute_web_search",
    "resolve_camera",
    "tool_names_for_config",
    "tool_schemas",
    "tool_schemas_for_config",
]
