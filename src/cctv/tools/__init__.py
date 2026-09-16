from __future__ import annotations

from typing import Any

from cctv.tools.get_camera import GET_CAMERA_IMAGE_TOOL, execute_get_camera_image, resolve_camera
from cctv.tools.get_image import GET_IMAGE_TOOL, execute_get_image
from cctv.tools.list_cameras import LIST_CAMERAS_TOOL, execute_list_cameras
from cctv.tools.registry import default_tool_schemas, execute_tool, register_tool, tool_schemas


def _execute_get_image_args(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    return execute_get_image(str(args.get("source") or ""))


register_tool(LIST_CAMERAS_TOOL, execute_list_cameras)
register_tool(GET_CAMERA_IMAGE_TOOL, execute_get_camera_image)
register_tool(GET_IMAGE_TOOL, _execute_get_image_args)

__all__ = [
    "GET_CAMERA_IMAGE_TOOL",
    "GET_IMAGE_TOOL",
    "LIST_CAMERAS_TOOL",
    "default_tool_schemas",
    "execute_get_camera_image",
    "execute_get_image",
    "execute_list_cameras",
    "execute_tool",
    "resolve_camera",
    "tool_schemas",
]
