"""Unified ``get_image`` entry point for Prague cameras, HTTP URLs, and YouTube livestreams."""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from cctv.fetch.decoder import CameraImageFetcher
from cctv.fetch.http import get_url
from cctv.fetch.sources import SourceType, camera_place_id, classify_source
from cctv.fetch.youtube import extract_video_id, fetch_livestream_frame
from cctv.utils.paths import images_dir, place_data_dir

_SLEEP_PLACEHOLDER_SHA256: set[str] = set()


def register_sleep_placeholder_hash(digest: str) -> None:
    """Register a SHA-256 hex digest for the Prague camera sleep-mode placeholder."""
    _SLEEP_PLACEHOLDER_SHA256.add(digest.lower())


def _likely_unavailable(image_bytes: bytes) -> bool:
    if not _SLEEP_PLACEHOLDER_SHA256:
        return False
    digest = hashlib.sha256(image_bytes).hexdigest()
    return digest in _SLEEP_PLACEHOLDER_SHA256


def _failure(source: str, error: str, *, source_type: str) -> dict[str, Any]:
    return {
        "success": False,
        "source": source,
        "source_type": source_type,
        "error": error,
    }


def _annotate_success(result: dict[str, Any], source: str, image_bytes: bytes | None = None) -> dict[str, Any]:
    result.setdefault("source", source)
    if image_bytes is not None:
        result["likely_unavailable"] = _likely_unavailable(image_bytes)
    elif result.get("filepath"):
        try:
            image_bytes = Path(result["filepath"]).read_bytes()
            result["likely_unavailable"] = _likely_unavailable(image_bytes)
        except OSError:
            result["likely_unavailable"] = False
    return result


def _youtube_output_dir(video_id: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    return images_dir() / "youtube" / video_id


def _prague_output_dir(camera_id: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    place_id = camera_place_id(camera_id)
    if place_id:
        return place_data_dir(place_id)
    return images_dir() / "prague" / camera_id


def _http_output_dir(url: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return images_dir() / "http" / digest


def _fetch_http_image(url: str, output_dir: Path, fetcher: CameraImageFetcher) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = get_url(url, headers=fetcher.headers, timeout=fetcher.timeout)
        if response.status_code != 200:
            return _failure(url, f"HTTP {response.status_code}", source_type=SourceType.HTTP_IMAGE.value)

        content_type = (response.headers.get("Content-Type") or "").lower()
        body_text = getattr(response, "text", "") or ""
        if "json" in content_type or body_text.lstrip().startswith("{"):
            base64_data = response.json().get("contentBase64")
            if not base64_data:
                return _failure(url, "No contentBase64 in JSON response", source_type=SourceType.HTTP_IMAGE.value)
            image_bytes = base64.b64decode(base64_data)
        elif content_type.startswith("image/") or not content_type:
            image_bytes = response.content
        else:
            return _failure(
                url,
                f"Unsupported content type: {content_type or 'unknown'}",
                source_type=SourceType.HTTP_IMAGE.value,
            )

        slug = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        result = fetcher._save_frame(image_bytes, f"http_{slug}", str(output_dir))
        result["source_type"] = SourceType.HTTP_IMAGE.value
        result["url"] = url
        return _annotate_success(result, url, image_bytes)
    except Exception as exc:
        return _failure(url, str(exc), source_type=SourceType.HTTP_IMAGE.value)


def get_image(
    source: str,
    *,
    output_dir: str | Path | None = None,
    timeout: int = 30,
    verbose: bool = False,
) -> dict[str, Any]:
    """Fetch a still image from a YouTube live URL, Prague camera, or HTTP image URL."""
    try:
        source_type, info = classify_source(source)
    except ValueError as exc:
        return {"success": False, "source": source, "error": str(exc)}

    out_path = Path(output_dir) if output_dir is not None else None
    fetcher = CameraImageFetcher(timeout=timeout, verbose=verbose)

    if source_type == SourceType.YOUTUBE:
        url = info["url"]
        video_id = extract_video_id(url) or "unknown"
        target_dir = _youtube_output_dir(video_id, out_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_file = target_dir / f"youtube_{video_id}_{stamp}.jpg"
        result = fetch_livestream_frame(url, output_file, timeout_s=max(timeout, 45))
        result["source"] = source
        if result.get("success"):
            try:
                image_bytes = output_file.read_bytes()
            except OSError:
                image_bytes = None
            return _annotate_success(result, source, image_bytes)
        return result

    if source_type == SourceType.PRAGUE_CAMERA:
        camera_id = info["camera_id"]
        target_dir = _prague_output_dir(camera_id, out_path)
        result = fetcher.fetch_camera_image(
            camera_id,
            save_to_file=True,
            custom_output_dir=str(target_dir),
        )
        result["source_type"] = SourceType.PRAGUE_CAMERA.value
        result["source"] = source
        if not result.get("success"):
            return result
        try:
            image_bytes = Path(result["filepath"]).read_bytes()
        except OSError:
            image_bytes = None
        return _annotate_success(result, source, image_bytes)

    url = info["url"]
    target_dir = _http_output_dir(url, out_path)
    return _fetch_http_image(url, target_dir, fetcher)
