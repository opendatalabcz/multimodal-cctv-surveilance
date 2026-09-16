"""OpenAI function-calling tool that fetches a CCTV / livestream still."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cctv.fetch.image_source import get_image

GET_IMAGE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_image",
        "description": (
            "Fetch the current frame from a public CCTV or live video source. "
            "Pass a YouTube **live** stream URL, a Prague municipal camera image URL "
            "(…/cameras/{id}/image), a known Prague camera id, or any direct image URL. "
            "Prague cameras may return a sleep-mode placeholder on the first request; "
            "if likely_unavailable is true, wait a few seconds and call again. "
            "YouTube sources must be live streams, not finished VOD uploads."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "YouTube live URL, camera image URL, or Prague camera id "
                        "(e.g. 101048)."
                    ),
                }
            },
            "required": ["source"],
        },
    },
}


def _tool_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe metadata for the tool role (no image bytes)."""
    allowed = (
        "success",
        "source",
        "source_type",
        "camera_id",
        "video_id",
        "filename",
        "filepath",
        "dimensions",
        "size_bytes",
        "likely_unavailable",
        "error",
        "captured_at",
        "url",
    )
    meta = {key: result[key] for key in allowed if key in result}
    if meta.get("filepath"):
        meta["filepath"] = str(Path(meta["filepath"]))
    return meta


def execute_get_image(source: str) -> dict[str, Any]:
    """Run ``get_image`` and split metadata (tool message) from the JPEG path."""
    result = get_image(source, verbose=False)
    return {
        "tool_content": json.dumps(_tool_metadata(result), ensure_ascii=False),
        "image_path": result.get("filepath") if result.get("success") else None,
        "fetch_result": result,
    }
