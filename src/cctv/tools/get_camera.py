"""Model-facing tool: fetch stills by configured camera id or name."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from cctv.config.agent_yaml import load_agent_config
from cctv.config.models import CameraConfig
from cctv.tools.get_image import execute_get_image

PREFERRED_IMAGE_CAP = 10
HARD_IMAGE_CAP = 16
_FETCH_WORKERS = 4

GET_CAMERA_IMAGE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_camera_image",
        "description": (
            "Fetch current frames from cameras listed in the Config panel / agent.yaml. "
            "Pass one or more camera ids or display names in `cameras` (preferred). "
            "`camera` is accepted for a single name. Do not issue one tool call per camera. "
            "Prefer about 10 images; a place-wide question may go a little over. "
            "Unknown names: tell the user to add name, optional GPS, and source URL "
            "in the Config panel. Do not pass raw URLs here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cameras": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Configured camera ids or names, e.g. [\"charles_bridge\", \"Hybernská\"]. "
                        "A single string is also accepted."
                    ),
                },
                "camera": {
                    "type": "string",
                    "description": "Single camera id or name if you are not using cameras[].",
                },
            },
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


def _camera_queries(arguments: dict[str, Any]) -> list[str]:
    raw: list[Any] = []
    cameras = arguments.get("cameras")
    if isinstance(cameras, str):
        raw.append(cameras)
    elif isinstance(cameras, list):
        raw.extend(cameras)
    camera = arguments.get("camera")
    if camera not in (None, ""):
        raw.append(camera)

    queries: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries


def _unknown_result(query: str) -> dict[str, Any]:
    return {
        "success": False,
        "query": query,
        "error": (
            f"Unknown camera {query!r}. Call list_cameras, or ask the user to add "
            "it in the Config panel (name, optional GPS, YouTube or image URL)."
        ),
    }


def _fetch_one(query: str) -> tuple[dict[str, Any], str | None]:
    camera = resolve_camera(query)
    if camera is None:
        return _unknown_result(query), None
    result = execute_get_image(camera.source)
    meta = json.loads(result["tool_content"])
    meta["query"] = query
    meta["camera_id"] = camera.id
    meta["camera_name"] = camera.name
    path = result.get("image_path")
    return meta, path if path else None


def _fetch_many(queries: list[str]) -> list[tuple[dict[str, Any], str | None]]:
    if len(queries) == 1:
        return [_fetch_one(queries[0])]
    ordered: list[tuple[dict[str, Any], str | None] | None] = [None] * len(queries)
    workers = min(_FETCH_WORKERS, len(queries))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, query): index for index, query in enumerate(queries)}
        for future in as_completed(futures):
            ordered[futures[future]] = future.result()
    return [item for item in ordered if item is not None]


def execute_get_camera_image(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    queries = _camera_queries(args)
    if not queries:
        return {
            "tool_content": json.dumps(
                {
                    "success": False,
                    "error": "Missing camera name. Pass cameras: [id or name, ...].",
                },
                ensure_ascii=False,
            ),
            "image_path": None,
            "image_paths": [],
        }

    skipped: list[str] = []
    note = None
    if len(queries) > HARD_IMAGE_CAP:
        skipped = queries[HARD_IMAGE_CAP:]
        queries = queries[:HARD_IMAGE_CAP]
        note = (
            f"Hard cap of {HARD_IMAGE_CAP} images applied; "
            f"skipped {len(skipped)} extra camera(s)."
        )
    elif len(queries) > PREFERRED_IMAGE_CAP:
        note = (
            f"Fetched {len(queries)} cameras (preferred cap is about "
            f"{PREFERRED_IMAGE_CAP}); proceed because this looks place-wide."
        )

    rows = _fetch_many(queries)
    results: list[dict[str, Any]] = []
    image_paths: list[str] = []
    for meta, path in rows:
        results.append(meta)
        if path:
            image_paths.append(path)

    payload: dict[str, Any] = {
        "success": bool(image_paths) or (len(results) == 1 and results[0].get("success") is True),
        "count": len(results),
        "fetched": len(image_paths),
        "results": results,
    }
    if skipped:
        payload["skipped"] = skipped
    if note:
        payload["note"] = note
    if len(results) == 1:
        payload.update(results[0])

    return {
        "tool_content": json.dumps(payload, ensure_ascii=False),
        "image_path": image_paths[0] if image_paths else None,
        "image_paths": image_paths,
    }
