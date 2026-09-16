from __future__ import annotations

import hashlib
from datetime import datetime
from threading import Lock
from typing import Any

from cctv.analysis.azure_vision import analyze_images
from cctv.config.agent_yaml import load_agent_config, save_agent_config
from cctv.config.models import CameraAnalysis, CameraConfig, SceneTag
from cctv.tools.get_image import execute_get_image
from cctv.utils.azure import AzureOpenAIConfig

SCENE_TAG_VALUES = tuple(SceneTag.__args__)
_config_write_lock = Lock()

ANALYSIS_PROMPT = f"""Describe the stable field of view of this CCTV camera, not transient details.
Return JSON only:
{{"description":"one short sentence, at most 160 characters","scene_tags":["tag"]}}
Choose zero to six scene_tags only from: {", ".join(SCENE_TAG_VALUES)}.
Describe what future frames from this camera are useful for observing. For example, distinguish
a road carrying vehicles from a pedestrian bridge, panorama, airport apron, or public square."""


def source_fingerprint(source: str) -> str:
    return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()[:16]


def analyze_camera_metadata(
    camera_id: str,
    *,
    azure_config: AzureOpenAIConfig | None = None,
) -> CameraConfig:
    config = load_agent_config()
    camera = next((item for item in config.cameras if item.id.lower() == camera_id.lower()), None)
    if camera is None:
        raise ValueError(f"Unknown camera: {camera_id}")

    expected_source = camera.source
    try:
        fetched = execute_get_image(expected_source)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch camera frame: {exc}") from exc
    image_path = fetched.get("image_path")
    if not image_path:
        metadata = _tool_error(fetched)
        raise RuntimeError(f"Could not fetch camera frame: {metadata}")

    result = analyze_images(
        [image_path],
        ANALYSIS_PROMPT,
        config=azure_config,
        parse_json=True,
        max_tokens=300,
    )
    if not result.get("success"):
        raise RuntimeError(str(result.get("error") or "Vision analysis failed"))

    analysis = _validated_analysis(result.get("analysis"), expected_source)

    # Reload immediately before writing so unrelated edits made while the model
    # was running are retained. Refuse to attach stale metadata to a changed URL.
    with _config_write_lock:
        latest = load_agent_config()
        index = next(
            (i for i, item in enumerate(latest.cameras) if item.id.lower() == camera_id.lower()),
            None,
        )
        if index is None:
            raise ValueError(f"Camera was removed during analysis: {camera_id}")
        current = latest.cameras[index]
        if current.source != expected_source:
            raise RuntimeError("Camera source changed during analysis; retry with the new source")
        updated = current.model_copy(update={"analysis": analysis})
        latest.cameras[index] = updated
        save_agent_config(latest)
    return updated


def _validated_analysis(payload: Any, source: str) -> CameraAnalysis:
    if not isinstance(payload, dict):
        raise RuntimeError("Vision model did not return camera metadata JSON")
    description = str(payload.get("description") or "").strip()
    if not description:
        raise RuntimeError("Vision model returned an empty camera description")
    description = description[:240]
    raw_tags = payload.get("scene_tags")
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = list(dict.fromkeys(str(tag).strip().lower() for tag in raw_tags if str(tag).strip()))
    invalid = [tag for tag in tags if tag not in SCENE_TAG_VALUES]
    if invalid:
        raise RuntimeError(f"Vision model returned unsupported scene tags: {', '.join(invalid)}")
    return CameraAnalysis(
        description=description,
        scene_tags=tags[:6],
        source_fingerprint=source_fingerprint(source),
        analyzed_at=datetime.now().astimezone(),
    )


def _tool_error(result: dict[str, Any]) -> str:
    try:
        import json

        payload = json.loads(result.get("tool_content") or "{}")
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except (TypeError, json.JSONDecodeError):
        pass
    return "unknown fetch error"
