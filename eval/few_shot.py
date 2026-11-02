"""Held-out frames that can be sent ahead of each scored frame.

The times fall halfway between the 60-second sample grid, inside stable parts of
night_6: one with the cargo holds open, one with the holds closed while the
aircraft is still parked and the bridge is still docked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FewShotExample:
    example_id: str
    video: str
    timestamp_s: int
    parked: bool
    tunnel_attached: bool
    doors_open: bool
    note: str

    def label(self) -> dict[str, bool | str]:
        return {
            "parked": self.parked,
            "tunnel_attached": self.tunnel_attached,
            "doors_open": self.doors_open,
            "description": self.note,
        }

    def caption(self) -> str:
        body = json.dumps(self.label(), indent=2)
        return f"Example ({self.example_id}). Correct JSON:\n{body}"


EXAMPLES = (
    FewShotExample(
        example_id="night-doors-open",
        video="night_6",
        timestamp_s=1530,
        parked=True,
        tunnel_attached=True,
        doors_open=True,
        note="The aircraft is parked and the bridge is docked. A cargo hold is open; the rear hold may sit partly behind the wing.",
    ),
    FewShotExample(
        example_id="night-doors-closed",
        video="night_6",
        timestamp_s=2430,
        parked=True,
        tunnel_attached=True,
        doors_open=False,
        note="The aircraft is parked and the bridge is docked. Both cargo holds are closed.",
    ),
)


def few_shot_id(examples: tuple[FewShotExample, ...] = EXAMPLES) -> str:
    payload = [
        {
            "example_id": example.example_id,
            "video": example.video,
            "timestamp_s": example.timestamp_s,
            "label": example.label(),
        }
        for example in examples
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def held_out_keys(examples: tuple[FewShotExample, ...] = EXAMPLES) -> set[tuple[str, int]]:
    return {(example.video, example.timestamp_s) for example in examples}


def example_path(output_dir: Path, example: FewShotExample) -> Path:
    return output_dir / "few_shot" / f"{example.video}_t{example.timestamp_s:06d}.jpg"


def prepare_examples(videos_dir: Path, output_dir: Path, examples: tuple[FewShotExample, ...] = EXAMPLES) -> list[tuple[Path, str]]:
    """Extract the example JPEGs and return (path, caption) pairs in order."""
    from eval.frames import extract_jpeg

    prepared: list[tuple[Path, str]] = []
    for example in examples:
        dest = example_path(output_dir, example)
        source = videos_dir / f"{example.video}.mp4"
        extract_jpeg(source, example.timestamp_s, dest)
        prepared.append((dest, example.caption()))
    write_example_page(output_dir, examples)
    return prepared


def write_example_page(output_dir: Path, examples: tuple[FewShotExample, ...] = EXAMPLES) -> Path:
    """A small page that shows the JPEGs and the JSON sent with them."""
    page = output_dir / "few_shot" / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Few-shot examples</title>",
        "<style>body{font-family:sans-serif;margin:24px;background:#111;color:#eee}",
        "img{max-width:960px;height:auto} pre{white-space:pre-wrap}</style></head><body>",
        "<h1>Few-shot examples</h1>",
        "<p>These two frames are sent before the frame being judged when <code>--few-shot</code> is on.</p>",
    ]
    for example in examples:
        image = example_path(output_dir, example).name
        parts.append(f"<h2>{example.example_id}</h2>")
        parts.append(f"<p>{example.video} at {example.timestamp_s}s</p>")
        parts.append(f"<img src='{image}' alt='{example.example_id}'>")
        parts.append(f"<pre>{example.caption()}</pre>")
    parts.append("</body></html>")
    page.write_text("\n".join(parts), encoding="utf-8")
    return page
