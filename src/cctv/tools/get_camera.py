"""Model-facing tool: fetch a still by configured camera id or name."""

from __future__ import annotations

import json
from typing import Any

from cctv.config.agent_yaml import load_agent_config
from cctv.config.models import CameraConfig
from cctv.tools.get_image import execute_get_image

GET_CAMERA_IMAGE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_camera_image",
        "description": (
            "Fetch the current frame from a camera listed in the Config panel / agent.yaml. "
            "Pass the camera id or display name (case-insensitive). "
            "If the camera is unknown, tell the user to add name, optional GPS, and source URL "
            "in the Config panel. Do not pass raw URLs here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "camera": {
                    "type": "string",
                    "description": "Configured camera id or name, e.g. charles_bridge or Charles Bridge.",
                }
            },
            "required": ["camera"],
        },
    },
}


def resolve_camera(query: str) -> CameraConfig | None:
    needle = (query or "").strip().lower()
    if not needle:
        return None
    for camera in load_agent_config().cameras:
        if camera.id.lower() == needle or camera.name.lower() == needle:
            return camera
    return None


def execute_get_camera_image(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    query = str(args.get("camera") or "")
    camera = resolve_camera(query)
    if camera is None:
        return {
            "tool_content": json.dumps(
                {
                    "success": False,
                    "error": (
                        f"Unknown camera {query!r}. Call list_cameras, or ask the user to add "
                        "it in the Config panel (name, optional GPS, YouTube or image URL)."
                    ),
                },
                ensure_ascii=False,
            ),
            "image_path": None,
        }

    result = execute_get_image(camera.source)
    meta = json.loads(result["tool_content"])
    meta["camera_id"] = camera.id
    meta["camera_name"] = camera.name
    result["tool_content"] = json.dumps(meta, ensure_ascii=False)
    return result
