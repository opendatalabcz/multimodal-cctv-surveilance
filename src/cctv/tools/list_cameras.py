"""Model-facing tool: list cameras from ``configs/agent.yaml``."""

from __future__ import annotations

import json
from typing import Any

from cctv.config.agent_yaml import load_agent_config
from cctv.config.effective import camera_gps, effective_cameras, location_for_camera
from cctv.fetch.sources import classify_source

LIST_CAMERAS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_cameras",
        "description": (
            "List effectively enabled cameras configured in the UI / agent.yaml. "
            "Use this before get_camera_image if you are unsure of the id or name. "
            "Do not invent cameras that are not in this list; tell the user to add them "
            "in the Config panel."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


def _source_type(source: str) -> str:
    try:
        source_type, _info = classify_source(source)
        return source_type.value
    except ValueError:
        return "unknown"


def execute_list_cameras(_arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_agent_config()
    cameras = []
    for camera in effective_cameras(config):
        location = location_for_camera(config, camera)
        lat, lon = camera_gps(config, camera)
        cameras.append(
            {
                "id": camera.id,
                "name": camera.name,
                "lat": lat,
                "lon": lon,
                "source": camera.source,
                "source_type": _source_type(camera.source),
                "sector_id": camera.sector_id,
                "location_id": camera.location_id,
                "location_name": location.name if location else None,
                "description": camera.analysis.description if camera.analysis else None,
                "scene_tags": camera.analysis.scene_tags if camera.analysis else [],
            }
        )
    payload = {"success": True, "cameras": cameras, "count": len(cameras)}
    return {"tool_content": json.dumps(payload, ensure_ascii=False), "image_path": None}
