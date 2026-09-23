"""Parse cite-to-display camera ids from the assistant's final reply."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CITE_LANGUAGES = frozenset({"cite", "citations", "camera", "cameras", "sep"})
EMPTY_CITE_LANGUAGES = frozenset({"cite", "citations", "camera", "cameras"})
_FENCE_OPEN = re.compile(r"(?:^|\n)[ \t]{0,3}(`{3,}|~{3,})")
_TRAILER_JUNK = re.compile(
    r"(?:"
    r"\s*\.{2,}sep"
    r"|\s*\[SEP\]"
    r"|\s*</?sep>"
    r"|\s*={2,}SEP={2,}"
    r"|\s*-{3,}"
    r"|\s*_{3,}"
    r")+\s*\Z",
    re.IGNORECASE,
)
_ORPHAN_TICKS = re.compile(r"\s*[`~]{3,}\s*\Z")


@dataclass(frozen=True)
class FetchedFrame:
    path: str
    camera_id: str | None = None
    camera_name: str | None = None

    def keys(self) -> set[str]:
        values = (self.camera_id, self.camera_name, Path(self.path).stem)
        return {value.strip().lower() for value in values if value and str(value).strip()}


def parse_cited_cameras(text: str) -> tuple[str, list[str] | None]:
    """Split visible answer text from a trailing citation fence.

    Returns ``(display_text, citations)``. ``citations`` is ``None`` when no
    citation trailer is present (caller should keep every fetched frame). An
    empty ``cite`` / ``cameras`` fence means show no images.
    """
    raw = text or ""
    trailer = _trailing_citation_fence(raw)
    citations: list[str] | None = None
    display = raw
    if trailer is not None:
        display, language, body = trailer
        parsed = _parse_cite_body(body)
        if parsed:
            citations = parsed
        elif language in EMPTY_CITE_LANGUAGES:
            citations = []
    display = _strip_trailer_junk(display)
    return display.strip(), citations


def _strip_sep_remainder(remainder: str) -> bool:
    return bool(_TRAILER_JUNK.sub("", remainder).strip())


def _strip_trailer_junk(text: str) -> str:
    cleaned = _TRAILER_JUNK.sub("", text)
    return _ORPHAN_TICKS.sub("", cleaned)


def _trailing_citation_fence(text: str) -> tuple[str, str, str] | None:
    last: tuple[str, str, str] | None = None
    for prefix, language, body, end in _iter_fences(text):
        if _strip_sep_remainder(text[end:]):
            continue
        if language in CITE_LANGUAGES or (not language and _looks_like_id_list(body)):
            last = (prefix, language, body)
    return last


def _iter_fences(text: str) -> list[tuple[str, str, str, int]]:
    fences: list[tuple[str, str, str, int]] = []
    search_from = 0
    while True:
        match = _FENCE_OPEN.search(text, search_from)
        if match is None:
            break
        ticks = match.group(1)
        tick_at = match.start(1)
        line_start = match.end()
        newline = text.find("\n", line_start)
        if newline == -1:
            info_raw = text[line_start:]
            line_end = len(text)
        else:
            info_raw = text[line_start:newline]
            line_end = newline
        inline_close = info_raw.find(ticks)
        if inline_close != -1:
            info = info_raw[:inline_close]
            language, inline_body = _split_info(info)
            body = inline_body
            end = line_start + inline_close + len(ticks)
            while end < len(text) and text[end] in " \t":
                end += 1
            fences.append((text[:tick_at], language, body, end))
            search_from = end
            continue
        language, _ = _split_info(info_raw)
        close = _find_closing_fence(text, line_end, ticks)
        if close is None:
            body = text[line_end + 1 :] if line_end < len(text) else ""
            end = len(text)
        else:
            close_at, end = close
            body = text[line_end + 1 : close_at]
        fences.append((text[:tick_at], language, body, end))
        search_from = max(end, tick_at + 1)
    return fences


def _split_info(info: str) -> tuple[str, str]:
    stripped = info.strip()
    if not stripped:
        return "", ""
    language, _, rest = stripped.partition(" ")
    return language.lower(), rest.strip()


def _find_closing_fence(text: str, after_open_line: int, ticks: str) -> tuple[int, int] | None:
    mark = ticks[0]
    minimum = len(ticks)
    close_re = re.compile(
        rf"\n[ \t]{{0,3}}{re.escape(mark)}{{{minimum},}}[ \t]*(?=\n|$)"
    )
    match = close_re.search(text, after_open_line)
    if match is None:
        return None
    return match.start(), match.end()


def _looks_like_id_list(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    if not _parse_cite_body(text):
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(char in stripped for char in "()=;"):
            return False
    return True


def select_cited_paths(
    frames: list[FetchedFrame],
    citations: list[str] | None,
) -> list[str]:
    if citations is None:
        return [frame.path for frame in frames]
    by_key: dict[str, FetchedFrame] = {}
    for frame in frames:
        for key in frame.keys():
            by_key[key] = frame
    selected: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        frame = by_key.get(citation.strip().lower())
        if frame is None or frame.path in seen:
            continue
        selected.append(frame.path)
        seen.add(frame.path)
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


def _parse_cite_body(body: str) -> list[str]:
    text = (body or "").strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _unique_ids(str(item) for item in parsed)
        if isinstance(parsed, dict):
            cameras = parsed.get("cameras") or parsed.get("ids") or []
            if isinstance(cameras, list):
                return _unique_ids(str(item) for item in cameras)
    tokens: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*").strip()
        if not stripped:
            continue
        tokens.extend(part.strip() for part in stripped.split(","))
    return _unique_ids(tokens)


def _unique_ids(values: Any) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        ids.append(text)
    return ids
