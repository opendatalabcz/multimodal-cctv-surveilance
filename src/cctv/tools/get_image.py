"""Fetch a still and return tool metadata plus the JPEG path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cctv.fetch.image_source import get_image


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
