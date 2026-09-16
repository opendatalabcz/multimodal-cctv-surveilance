"""Capture a single JPEG from a YouTube **live** stream (not the YouTube Data API)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import imageio_ffmpeg
import requests
import yt_dlp
from PIL import Image

_YOUTUBE_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|youtube\.com/live/)([A-Za-z0-9_-]{6,})",
    re.I,
)
_DEFAULT_TIMEOUT_S = 45
_PREFERRED_MAX_HEIGHT = 720


def _failure(error: str, *, source_type: str = "youtube") -> dict[str, Any]:
    return {"success": False, "source_type": source_type, "error": error}


def extract_video_id(url: str) -> str | None:
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def _is_storyboard(fmt: dict[str, Any]) -> bool:
    protocol = str(fmt.get("protocol") or "").lower()
    ext = str(fmt.get("ext") or "").lower()
    format_id = str(fmt.get("format_id") or "").lower()
    note = str(fmt.get("format_note") or "").lower()
    return (
        "mhtml" in protocol
        or ext == "mhtml"
        or "storyboard" in format_id
        or "storyboard" in note
    )


def _is_video_format(fmt: dict[str, Any]) -> bool:
    if not fmt.get("url"):
        return False
    if (fmt.get("vcodec") or "none") == "none":
        return False
    return not _is_storyboard(fmt)


def _is_video_only(fmt: dict[str, Any]) -> bool:
    return (fmt.get("acodec") or "none") == "none"


def _height(fmt: dict[str, Any]) -> int:
    try:
        return int(fmt.get("height") or 0)
    except (TypeError, ValueError):
        return 0


def _pick_stream_format(info: dict[str, Any]) -> dict[str, Any] | None:
    """Choose a video-only live format. Never require muxed audio+video."""
    formats = [fmt for fmt in (info.get("formats") or []) if _is_video_format(fmt)]
    if formats:
        at_or_below = [fmt for fmt in formats if 0 < _height(fmt) <= _PREFERRED_MAX_HEIGHT]
        if at_or_below:
            return max(at_or_below, key=lambda fmt: (_height(fmt), int(_is_video_only(fmt))))
        above = [fmt for fmt in formats if _height(fmt) > _PREFERRED_MAX_HEIGHT]
        if above:
            return min(above, key=lambda fmt: (_height(fmt), -int(_is_video_only(fmt))))
        return max(formats, key=lambda fmt: (int(_is_video_only(fmt)), _height(fmt)))
    direct = info.get("url")
    if direct:
        return {"url": direct, "http_headers": info.get("http_headers") or {}}
    return None


def _pick_stream_url(info: dict[str, Any]) -> str | None:
    chosen = _pick_stream_format(info)
    url = chosen.get("url") if chosen else None
    return str(url) if url else None


def _last_playlist_media_url(playlist_text: str, playlist_url: str) -> str | None:
    media: list[str] = []
    for raw in playlist_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        media.append(urljoin(playlist_url, line))
    return media[-1] if media else None


def _download_bytes(url: str, headers: dict[str, str], timeout_s: int) -> bytes:
    response = requests.get(url, headers=headers or None, timeout=timeout_s)
    response.raise_for_status()
    return response.content


def _is_hls(url: str) -> bool:
    lowered = url.lower()
    return ".m3u8" in lowered or "manifest/hls" in lowered or "/playlist/" in lowered


def _ffmpeg_still_cmd(ffmpeg: str, input_path: str, output_path: Path) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_path,
        "-an",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]


def _run_ffmpeg(cmd: list[str], timeout_s: int) -> str | None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return f"ffmpeg timed out after {timeout_s}s"
    except subprocess.CalledProcessError as exc:
        if exc.returncode < 0:
            return f"ffmpeg crashed with signal {-exc.returncode}"
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        return f"ffmpeg failed: {stderr or exc}"
    return None


def fetch_livestream_frame(
    url: str,
    output_path: str | Path,
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Resolve a live HLS URL with yt-dlp and decode one live-edge JPEG with ffmpeg."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "live_from_start": False,
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

    chosen = _pick_stream_format(info)
    stream_url = str(chosen.get("url") or "") if chosen else ""
    if not stream_url:
        return _failure("No playable video stream URL found")
    headers = {str(key): str(value) for key, value in (chosen.get("http_headers") or {}).items()}

    video_id = info.get("id") or extract_video_id(url) or "unknown"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    http_timeout = min(20, timeout_s)

    if _is_hls(stream_url):
        try:
            playlist = _download_bytes(stream_url, headers, http_timeout).decode(
                "utf-8", errors="replace"
            )
            segment_url = _last_playlist_media_url(playlist, stream_url)
            if not segment_url:
                return _failure("HLS playlist contained no media segments")
            segment = _download_bytes(segment_url, headers, http_timeout)
        except requests.RequestException as exc:
            return _failure(f"Failed to fetch live-edge HLS segment: {exc}")
        if not segment:
            return _failure("Live-edge HLS segment was empty")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as tmp:
                tmp.write(segment)
                tmp_path = Path(tmp.name)
            error = _run_ffmpeg(_ffmpeg_still_cmd(ffmpeg, str(tmp_path), output_path), timeout_s)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        if error:
            return _failure(error)
    else:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-live_start_index",
            "-1",
            "-i",
            stream_url,
            "-an",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        error = _run_ffmpeg(cmd, timeout_s)
        if error:
            return _failure(error)

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
