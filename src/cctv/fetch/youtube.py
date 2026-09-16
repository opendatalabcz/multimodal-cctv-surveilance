"""Capture a single JPEG from a YouTube **live** stream (not the YouTube Data API)."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import yt_dlp
from PIL import Image

_YOUTUBE_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|youtube\.com/live/)([A-Za-z0-9_-]{6,})",
    re.I,
)
_DEFAULT_TIMEOUT_S = 45


def _failure(error: str, *, source_type: str = "youtube") -> dict[str, Any]:
    return {"success": False, "source_type": source_type, "error": error}


def extract_video_id(url: str) -> str | None:
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def _pick_stream_url(info: dict[str, Any]) -> str | None:
    direct = info.get("url")
    if direct:
        return direct

    formats = info.get("formats") or []
    candidates = [
        f for f in formats if f.get("url") and (f.get("vcodec") or "none") != "none"
    ]
    if not candidates:
        return None

    def _score(fmt: dict[str, Any]) -> tuple[int, int]:
        height = fmt.get("height") or 0
        has_audio = 0 if (fmt.get("acodec") or "none") == "none" else 1
        return (height, has_audio)

    best = max(candidates, key=_score)
    return best.get("url")


def fetch_livestream_frame(
    url: str,
    output_path: str | Path,
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Resolve a live HLS/DASH URL with yt-dlp and decode one JPEG with ffmpeg."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "live_from_start": False,
        "format": "best[height<=720]/best",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        return _failure(f"yt-dlp extract failed: {exc}")

    if not info:
        return _failure("yt-dlp returned no stream metadata")

    if not info.get("is_live"):
        return _failure("YouTube URL is not a live stream (livestream current window only)")

    stream_url = _pick_stream_url(info)
    if not stream_url:
        return _failure("No playable video stream URL found")

    video_id = info.get("id") or extract_video_id(url) or "unknown"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        stream_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _failure(f"ffmpeg timed out after {timeout_s}s")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        return _failure(f"ffmpeg failed: {stderr or exc}")

    if not output_path.is_file() or output_path.stat().st_size == 0:
        return _failure("ffmpeg did not produce a JPEG")

    try:
        with Image.open(output_path) as img:
            dimensions = img.size
    except Exception as exc:
        return _failure(f"Captured file is not a valid image: {exc}")

    return {
        "success": True,
        "source_type": "youtube",
        "video_id": video_id,
        "filename": output_path.name,
        "filepath": str(output_path),
        "dimensions": dimensions,
        "size_bytes": os.path.getsize(output_path),
        "captured_at": datetime.now().isoformat(),
    }
