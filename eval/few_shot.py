"""Held-out frames that can be sent ahead of each scored frame.

Every example time sits 30 seconds into a minute, so it is off the 60-second sample
grid, and it is more than 20 seconds from any state change, so it is never a
near-boundary frame. Examples are therefore never scored, and the scored set stays
at the same 285 frames at every prompt level.

Two sets exist:

- TWO_SHOT: one all-false frame and one all-true frame (prompt level 3).
- TEN_SHOT: two frames for each of the five state combinations that occur in
  timestamps.csv (prompt level 4).
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


# Notes restate the ground-truth states only. They do not add visual claims.
_NOTE_EMPTY = "The aircraft is not parked on the cross, the jet bridge is not docked, and no cargo hold is open."
_NOTE_PARKED = "The aircraft is parked on the cross. The jet bridge is not docked and both cargo holds are closed."
_NOTE_PARKED_TUNNEL = "The aircraft is parked and the jet bridge is docked. Both cargo holds are closed."
_NOTE_PARKED_DOORS = "The aircraft is parked and a cargo hold is open. The jet bridge is not docked."
_NOTE_ALL_TRUE = "The aircraft is parked, the jet bridge is docked, and a cargo hold is open."

# The all-false and all-true frames are the first two entries of TEN_SHOT.
TWO_SHOT = (
    FewShotExample(
        example_id="sunny-empty",
        video="sunny_6",
        timestamp_s=30,
        parked=False,
        tunnel_attached=False,
        doors_open=False,
        note=_NOTE_EMPTY,
    ),
    FewShotExample(
        example_id="night-all-true",
        video="night_6",
        timestamp_s=1530,
        parked=True,
        tunnel_attached=True,
        doors_open=True,
        note=_NOTE_ALL_TRUE,
    ),
)

# Interleaved so that no combination is sent as one block.
TEN_SHOT = (
    FewShotExample(
        example_id="sunny-empty",
        video="sunny_6",
        timestamp_s=30,
        parked=False,
        tunnel_attached=False,
        doors_open=False,
        note=_NOTE_EMPTY,
    ),
    FewShotExample(
        example_id="night-all-true",
        video="night_6",
        timestamp_s=1530,
        parked=True,
        tunnel_attached=True,
        doors_open=True,
        note=_NOTE_ALL_TRUE,
    ),
    FewShotExample(
        example_id="sunny-parked",
        video="sunny_6",
        timestamp_s=5310,
        parked=True,
        tunnel_attached=False,
        doors_open=False,
        note=_NOTE_PARKED,
    ),
    FewShotExample(
        example_id="cloudy-parked-tunnel",
        video="cloudy_6",
        timestamp_s=2670,
        parked=True,
        tunnel_attached=True,
        doors_open=False,
        note=_NOTE_PARKED_TUNNEL,
    ),
    FewShotExample(
        example_id="rainy-parked-doors",
        video="rainy_6",
        timestamp_s=3510,
        parked=True,
        tunnel_attached=False,
        doors_open=True,
        note=_NOTE_PARKED_DOORS,
    ),
    FewShotExample(
        example_id="rainy-empty",
        video="rainy_6",
        timestamp_s=4470,
        parked=False,
        tunnel_attached=False,
        doors_open=False,
        note=_NOTE_EMPTY,
    ),
    FewShotExample(
        example_id="sunny-all-true",
        video="sunny_6",
        timestamp_s=2910,
        parked=True,
        tunnel_attached=True,
        doors_open=True,
        note=_NOTE_ALL_TRUE,
    ),
    FewShotExample(
        example_id="night-parked",
        video="night_6",
        timestamp_s=2910,
        parked=True,
        tunnel_attached=False,
        doors_open=False,
        note=_NOTE_PARKED,
    ),
    FewShotExample(
        example_id="night-parked-tunnel",
        video="night_6",
        timestamp_s=2430,
        parked=True,
        tunnel_attached=True,
        doors_open=False,
        note=_NOTE_PARKED_TUNNEL,
    ),
    FewShotExample(
        example_id="rainy-parked-doors-2",
        video="rainy_6",
        timestamp_s=3570,
        parked=True,
        tunnel_attached=False,
        doors_open=True,
        note=_NOTE_PARKED_DOORS,
    ),
)

EXAMPLE_SETS = {"2-shot": TWO_SHOT, "10-shot": TEN_SHOT}
# Prompt level -> example set name. Levels 1 and 2 send no examples.
EXAMPLE_SET_BY_LEVEL = {1: None, 2: None, 3: "2-shot", 4: "10-shot"}


def example_set_for_level(level: int) -> str | None:
    return EXAMPLE_SET_BY_LEVEL[level]


def few_shot_id(examples: tuple[FewShotExample, ...]) -> str:
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


def held_out_keys(examples: tuple[FewShotExample, ...]) -> set[tuple[str, int]]:
    return {(example.video, example.timestamp_s) for example in examples}


def example_path(output_dir: Path, example: FewShotExample) -> Path:
    return output_dir / "few_shot" / f"{example.video}_t{example.timestamp_s:06d}.jpg"


def prepare_examples(
    videos_dir: Path,
    output_dir: Path,
    set_name: str,
) -> list[tuple[Path, str]]:
    """Extract the example JPEGs for one set and return (path, caption) pairs in order."""
    from eval.frames import extract_jpeg

    examples = EXAMPLE_SETS[set_name]
    prepared: list[tuple[Path, str]] = []
    for example in examples:
        dest = example_path(output_dir, example)
        source = videos_dir / f"{example.video}.mp4"
        extract_jpeg(source, example.timestamp_s, dest)
        prepared.append((dest, example.caption()))
    write_example_page(output_dir, set_name)
    return prepared


def write_example_page(output_dir: Path, set_name: str) -> Path:
    """A small page that shows the JPEGs and the JSON sent with them."""
    examples = EXAMPLE_SETS[set_name]
    page = output_dir / "few_shot" / f"{set_name}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        "<!DOCTYPE html>",
        f"<html><head><meta charset='utf-8'><title>{set_name} examples</title>",
        "<style>body{font-family:sans-serif;margin:24px;background:#111;color:#eee}",
        "img{max-width:960px;height:auto} pre{white-space:pre-wrap}</style></head><body>",
        f"<h1>{set_name} examples</h1>",
        f"<p>These {len(examples)} frames are sent before the frame being judged at prompt levels that use the {set_name} set.</p>",
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
