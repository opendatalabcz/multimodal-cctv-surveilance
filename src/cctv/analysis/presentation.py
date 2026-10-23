"""Frames fetched during a chat turn, and which of them the answer shows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_FOLLOWUPS = 3
MAX_ANNOTATIONS = 1000
MAX_LABEL_CHARS = 80
COORD_MAX = 1000
_MAX_FOLLOWUP_CHARS = 120
_LIST_MARKER = re.compile(r"^(?:[-*+•]|\d+[.)])\s*")
_POINT_LIMITS: dict[str, tuple[int, int]] = {
    "point": (1, 1),
    "box": (2, 2),
    "line": (2, 8),
    "polygon": (3, 12),
}
_BAD_LABEL = object()


@dataclass(frozen=True)
class FetchedFrame:
    path: str
    camera_id: str | None = None
    camera_name: str | None = None

    def keys(self) -> set[str]:
        values = (self.camera_id, self.camera_name, Path(self.path).stem)
        return {value.strip().lower() for value in values if value and str(value).strip()}


@dataclass(frozen=True)
class ImageAnnotation:
    type: str
    points: tuple[tuple[int, int], ...]
    label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "points": [list(point) for point in self.points],
        }
        if self.label:
            payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class PresentedImage:
    frame: FetchedFrame
    annotations: tuple[ImageAnnotation, ...]


def normalize_followups(values: list[Any]) -> list[str]:
    """Keep at most three unique questions, dropping blanks and over-long lines."""
    questions: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = _LIST_MARKER.sub("", str(value).strip()).strip().strip('"').strip()
        key = stripped.lower()
        if not stripped or len(stripped) > _MAX_FOLLOWUP_CHARS or key in seen:
            continue
        seen.add(key)
        questions.append(stripped)
        if len(questions) == MAX_FOLLOWUPS:
            break
    return questions


def select_presented_images(frames: list[FetchedFrame], images: Any) -> list[PresentedImage]:
    """Keep fetched frames named in ``images``, in that order, with valid annotations."""
    by_key: dict[str, FetchedFrame] = {}
    for frame in frames:
        for key in frame.keys():
            by_key[key] = frame
    selected: list[PresentedImage] = []
    seen: set[str] = set()
    if not isinstance(images, list):
        return []
    for item in images:
        if not isinstance(item, dict):
            continue
        camera_id = item.get("camera_id")
        if not isinstance(camera_id, str) or not camera_id.strip():
            continue
        frame = by_key.get(camera_id.strip().lower())
        if frame is None or frame.path in seen:
            continue
        seen.add(frame.path)
        selected.append(
            PresentedImage(frame=frame, annotations=tuple(_annotations(item.get("annotations"))))
        )
    return selected


def frames_from_tool_result(
    exec_result: dict[str, Any],
    arguments: dict[str, Any] | None = None,
) -> list[FetchedFrame]:
    labels = exec_result.get("image_labels")
    if isinstance(labels, list) and labels:
        frames: list[FetchedFrame] = []
        for item in labels:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not path:
                continue
            frames.append(
                FetchedFrame(
                    path=str(path),
                    camera_id=_optional_str(item.get("camera_id")),
                    camera_name=_optional_str(item.get("camera_name")),
                )
            )
        if frames:
            return frames

    paths = _paths_from_exec_result(exec_result)
    if not paths:
        return []
    queries = _argument_queries(arguments)
    payload_rows = _success_rows(exec_result)
    frames = []
    for index, path in enumerate(paths):
        camera_id = None
        camera_name = None
        if index < len(payload_rows):
            camera_id = _optional_str(payload_rows[index].get("camera_id"))
            camera_name = _optional_str(payload_rows[index].get("camera_name"))
        if camera_id is None and index < len(queries):
            camera_id = queries[index]
        frames.append(FetchedFrame(path=path, camera_id=camera_id, camera_name=camera_name))
    return frames


def _annotations(value: Any) -> list[ImageAnnotation]:
    if not isinstance(value, list):
        return []
    kept: list[ImageAnnotation] = []
    for item in value:
        annotation = _annotation(item)
        if annotation is None:
            continue
        kept.append(annotation)
        if len(kept) == MAX_ANNOTATIONS:
            break
    return kept


def _annotation(value: Any) -> ImageAnnotation | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("type")
    if not isinstance(kind, str) or kind not in _POINT_LIMITS:
        return None
    raw_points = value.get("points")
    if not isinstance(raw_points, list):
        return None
    points: list[tuple[int, int]] = []
    for raw in raw_points:
        point = _point(raw)
        if point is None:
            return None
        points.append(point)
    low, high = _POINT_LIMITS[kind]
    if not low <= len(points) <= high:
        return None
    label = _label(value.get("label"))
    if label is _BAD_LABEL:
        return None
    return ImageAnnotation(type=kind, points=tuple(points), label=label)


def _point(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x = _coord(value[0])
    y = _coord(value[1])
    if x is None or y is None:
        return None
    return (x, y)


def _coord(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    number = int(value)
    if number < 0 or number > COORD_MAX:
        return None
    return number


def _label(value: Any) -> str | None | object:
    if value is None:
        return None
    if not isinstance(value, str):
        return _BAD_LABEL
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_LABEL_CHARS:
        return _BAD_LABEL
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _paths_from_exec_result(exec_result: dict[str, Any]) -> list[str]:
    paths = exec_result.get("image_paths")
    if isinstance(paths, list):
        return [str(path) for path in paths if path]
    path = exec_result.get("image_path")
    return [str(path)] if path else []


def _argument_queries(arguments: dict[str, Any] | None) -> list[str]:
    if not arguments:
        return []
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
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries


def _success_rows(exec_result: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(exec_result.get("tool_content") or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    rows: list[dict[str, Any]] = []
    if isinstance(results, list):
        for row in results:
            if isinstance(row, dict) and row.get("success") is not False:
                rows.append(row)
        return rows
    if payload.get("success") is not False and payload.get("camera_id"):
        return [payload]
    return []
