"""Prompt levels and JSON parsing for the three stand states.

Prompt level 1 names the states and the output format only. Level 2 adds advice on
what to look at and what to avoid. Levels 3 and 4 send the level 2 text with a
held-out example set (see eval/few_shot.py).
"""

from __future__ import annotations

import hashlib
import json

_OUTPUT_FORMAT = """Return JSON only. Do not use Markdown fences or add any other text.
Use JSON booleans for the three state keys and a string for description.
{"parked": false, "tunnel_attached": false, "doors_open": false, "description": "..."}
"""

# Level 1: the three states and the output format. No visual pointers.
SIMPLE_PROMPT = (
    """You are looking at one frame from a fixed airport apron camera.

Judge the aircraft and apron visible in this frame. Judge each state independently.
Do not infer a state from another state or from events outside this frame.

Return a single JSON object with exactly these keys:
- parked: true if the aircraft nose wheel is stopped on the yellow parking cross painted on the apron.
- tunnel_attached: true if the passenger jet bridge is fully docked to the aircraft.
- doors_open: true if a cargo hold door is open.
- description: one or two sentences describing what is visible in the frame.
"""
    + _OUTPUT_FORMAT
)

# Level 2: the same states, with advice on what to focus on and what to avoid.
DESCRIPTIVE_PROMPT = (
    """You are looking at one frame from a fixed airport apron camera.
Judge only what is visible in this frame. Judge each state independently.
Do not infer a state from another state or from a suspected transition outside this frame.

Return a single JSON object with exactly these keys:
- parked: true only if the nose wheel of an aircraft is stopped on the yellow parking cross.
  Inspect the nose wheel itself and its position relative to the cross. Being parked does not require the whole aircraft to be perfectly centered.
  False for a taxiing or waiting aircraft, an aircraft beside the cross, or a nose wheel that only appears stopped because the frame was captured briefly.
- tunnel_attached: true only if the passenger jet bridge is physically and fully docked to the aircraft, with the bridge head contacting the fuselage and the canopy lowered.
  Inspect the contact point between the bridge head and the aircraft. Clear contact and a lowered canopy must both be visible.
  False for a bridge that is near or overlapping in the image but not contacting, or that is approaching, retracting, or moving away.
- doors_open: true only if a cargo hold door is visibly open. Count the front or rear cargo hold; do not count passenger doors.
  On a large aircraft, look for an outward-swinging door. On a small aircraft, look for an inward-folding or missing panel that reveals a visibly dark opening.
  Inspect the whole fuselage, especially the rear hold near or behind the wing. Closed hatches and ground equipment are false.
- description: one or two sentences describing the apron, aircraft, jet bridge, and cargo hold areas visible in the frame.

"""
    + _OUTPUT_FORMAT
)

# Prompt level -> prompt text. Levels 3 and 4 use the level 2 text.
PROMPT_TEXT_BY_LEVEL = {
    1: SIMPLE_PROMPT,
    2: DESCRIPTIVE_PROMPT,
    3: DESCRIPTIVE_PROMPT,
    4: DESCRIPTIVE_PROMPT,
}

PROMPT_LEVELS = tuple(PROMPT_TEXT_BY_LEVEL)

_STATES = ("parked", "tunnel_attached", "doors_open")


def prompt_text_for_level(level: int) -> str:
    try:
        return PROMPT_TEXT_BY_LEVEL[level]
    except KeyError as exc:
        known = ", ".join(str(item) for item in PROMPT_LEVELS)
        raise ValueError(f"Unknown prompt level {level!r}. Known levels: {known}") from exc


def selected_prompt_levels(level: int | None = None) -> tuple[int, ...]:
    return PROMPT_LEVELS if level is None else (level,)


def prompt_id(text: str) -> str:
    """Short id that changes when the prompt text changes."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse_state_json(text: str) -> dict | None:
    """Return the three booleans and a description, or None when the text is not that object."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    parsed: dict = {}
    for key in _STATES:
        if key not in data:
            return None
        value = data[key]
        if isinstance(value, bool):
            parsed[key] = value
        elif isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            parsed[key] = value.strip().lower() == "true"
        else:
            return None
    description = data.get("description", "")
    parsed["description"] = description.strip() if isinstance(description, str) else str(description)
    return parsed


def repair_prompt(previous: str) -> str:
    clipped = previous.strip()[:2000]
    return (
        "The previous reply was not valid JSON or did not match the required schema. "
        "Look at the image again and return JSON only, with exactly these keys and types: "
        "parked (boolean), tunnel_attached (boolean), doors_open (boolean), "
        'and description (string). Do not include Markdown fences or extra text.\n\n'
        'Example: {"parked": false, "tunnel_attached": false, "doors_open": false, '
        '"description": "..."}\n\n'
        f"Previous reply:\n{clipped}"
    )
