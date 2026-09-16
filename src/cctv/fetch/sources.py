"""Classify image source strings (YouTube, Prague camera, generic HTTP)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from cctv.fetch.config import load_monitor_config

_YOUTUBE_PATTERNS = (
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?", re.I),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/live/", re.I),
    re.compile(r"(?:https?://)?youtu\.be/", re.I),
)
_PRAGUE_CAMERA_URL = re.compile(
    r"/cameras/(\d+)/image/?$",
    re.I,
)
_CAMERA_ID = re.compile(r"^\d{5,6}$")


class SourceType(str, Enum):
    YOUTUBE = "youtube"
    PRAGUE_CAMERA = "prague_camera"
    HTTP_IMAGE = "http_image"


def _known_camera_ids(config: dict[str, Any] | None = None) -> set[str]:
    config = config or load_monitor_config()
    ids: set[str] = set()
    for camera_ids in config.get("cameras", {}).values():
        ids.update(camera_ids)
    return ids


def _is_youtube(source: str) -> bool:
    return any(pattern.search(source) for pattern in _YOUTUBE_PATTERNS)


def _prague_camera_id_from_url(source: str) -> str | None:
    match = _PRAGUE_CAMERA_URL.search(source)
    return match.group(1) if match else None


def camera_place_id(camera_id: str, config: dict[str, Any] | None = None) -> str | None:
    """Map a Prague camera id to its place key in monitor_config, if known."""
    config = config or load_monitor_config()
    for place_id, camera_ids in config.get("cameras", {}).items():
        if camera_id in camera_ids:
            return place_id
    return None


def classify_source(
    source: str,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[SourceType, dict[str, Any]]:
    """Return ``(source_type, info)`` for a user-provided source string.

    ``info`` holds normalized fields such as ``url`` or ``camera_id``.
    """
    source = source.strip()
    if not source:
        raise ValueError("Source must not be empty")

    if _is_youtube(source):
        return SourceType.YOUTUBE, {"url": source}

    camera_id = _prague_camera_id_from_url(source)
    if camera_id:
        return SourceType.PRAGUE_CAMERA, {"camera_id": camera_id, "url": source}

    known_ids = _known_camera_ids(config)
    if _CAMERA_ID.match(source) and source in known_ids:
        return SourceType.PRAGUE_CAMERA, {"camera_id": source}

    parsed = urlparse(source)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return SourceType.HTTP_IMAGE, {"url": source}

    if _CAMERA_ID.match(source):
        return SourceType.PRAGUE_CAMERA, {"camera_id": source}

    raise ValueError(f"Unrecognized image source: {source!r}")
