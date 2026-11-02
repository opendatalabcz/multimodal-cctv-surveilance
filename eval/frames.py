"""Extract one JPEG per sample time from the raw airport videos."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

from eval.labels import Sample


def video_duration_s(path: Path) -> float:
    """Read duration from the MP4 ``mvhd`` box."""
    data = path.read_bytes()

    def boxes(buf: bytes, start: int, end: int):
        cursor = start
        while cursor + 8 <= end:
            size = struct.unpack(">I", buf[cursor : cursor + 4])[0]
            box_type = buf[cursor + 4 : cursor + 8]
            header = 8
            if size == 1 and cursor + 16 <= end:
                size = struct.unpack(">Q", buf[cursor + 8 : cursor + 16])[0]
                header = 16
            elif size == 0:
                size = end - cursor
            if size < 8 or cursor + size > end:
                break
            yield box_type, cursor + header, cursor + size
            cursor += size

    for box_type, start, end in boxes(data, 0, len(data)):
        if box_type != b"moov":
            continue
        for inner_type, inner_start, _inner_end in boxes(data, start, end):
            if inner_type != b"mvhd":
                continue
            version = data[inner_start]
            if version == 0:
                timescale, duration = struct.unpack(">II", data[inner_start + 12 : inner_start + 20])
            else:
                timescale, duration = struct.unpack(">IQ", data[inner_start + 20 : inner_start + 32])
            if not timescale:
                raise ValueError(f"{path} has a zero movie timescale")
            return duration / timescale
    raise ValueError(f"No movie header in {path}")


def frame_path(output_dir: Path, sample: Sample) -> Path:
    return output_dir / f"{sample.interval_seconds}s" / f"{sample.frame_id}.jpg"


def extract_jpeg(source: Path, timestamp_s: int, dest: Path) -> None:
    import imageio_ffmpeg

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    if not source.exists():
        raise FileNotFoundError(source)
    _extract_one(imageio_ffmpeg.get_ffmpeg_exe(), source, timestamp_s, dest)


def extract_frames(samples: list[Sample], videos_dir: Path, output_dir: Path) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    total = len(samples)
    for index, sample in enumerate(samples, start=1):
        dest = frame_path(output_dir, sample)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            continue
        source = videos_dir / f"{sample.video}.mp4"
        if not source.exists():
            raise FileNotFoundError(source)
        _extract_one(ffmpeg, source, sample.timestamp_s, dest)
        if index % 25 == 0 or index == total:
            print(f"Extracted {index}/{total} frames")


def _extract_one(ffmpeg: str, source: Path, timestamp_s: int, dest: Path) -> None:
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(timestamp_s),
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(dest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed for {source.name} at {timestamp_s}s: {detail}")


def write_contact_sheet(samples: list[Sample], frames_dir: Path, html_path: Path) -> None:
    """HTML sheet of every sampled frame with the timestamp label."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    videos: list[str] = []
    for sample in samples:
        if sample.video not in videos:
            videos.append(sample.video)
    parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Stand state frames</title>",
        "<style>",
        "body{font-family:sans-serif;margin:24px;background:#111;color:#eee}",
        "figure{display:inline-block;width:320px;margin:8px;vertical-align:top}",
        "img{width:320px;height:auto;background:#000}",
        "figcaption{font-size:13px;line-height:1.4}",
        ".near{color:#f5c16c}",
        "</style></head><body>",
        f"<h1>Stand states, every {samples[0].interval_seconds}s</h1>" if samples else "<h1>No frames</h1>",
        f"<p>{len(samples)} frames. Gold text is within 20s of a state change.</p>",
    ]
    for video in videos:
        parts.append(f"<h2>{video}</h2>")
        for sample in samples:
            if sample.video != video:
                continue
            image = frame_path(frames_dir, sample)
            relative = image.relative_to(html_path.parent).as_posix()
            caption_class = "near" if sample.near_boundary else ""
            flags = (
                f"parked={str(sample.parked).lower()} "
                f"tunnel={str(sample.tunnel_attached).lower()} "
                f"doors={str(sample.doors_open).lower()}"
            )
            parts.append(
                "<figure>"
                f"<img src='{relative}' alt='{sample.frame_id}'>"
                f"<figcaption class='{caption_class}'>"
                f"{sample.timestamp_s}s · {sample.phase}<br>{flags}<br>"
                f"{sample.seconds_to_boundary:.0f}s from nearest change"
                "</figcaption></figure>"
            )
    parts.append("</body></html>")
    html_path.write_text("\n".join(parts), encoding="utf-8")
