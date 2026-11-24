"""Prompt levels and JSON parsing for the three stand states.

Prompt level 1 names the states and the output format only. Level 2 adds advice on
what to look at and what to avoid. Levels 3 and 4 send the level 2 text with a
held-out example set (see eval/few_shot.py).
"""

from __future__ import annotations

import hashlib
import json

_OUTPUT_FORMAT = """Use JSON booleans.
{"parked": false, "tunnel_attached": false, "doors_open": false, "description": "..."}
"""

# Level 1: the three states and the output format. No visual pointers.
SIMPLE_PROMPT = (
    """You are looking at one frame from a fixed airport apron camera.

Return a single JSON object and nothing else, with exactly these keys:
- parked: an aircraft nose wheel is stopped on the yellow parking cross painted on the apron.
- tunnel_attached: the passenger jet bridge is docked to the aircraft.
- doors_open: a cargo hold door is open.
- description: one or two sentences describing the apron, the aircraft if present, the jet bridge, and the cargo doors.

"""
    + _OUTPUT_FORMAT
)

# Level 2: the same states, with advice on what to focus on and what to avoid.
DESCRIPTIVE_PROMPT = (
    """You are looking at one frame from a fixed airport apron camera. Judge only what is visible in this frame.

Return a single JSON object and nothing else, with exactly these keys:
- parked: true only if an aircraft nose wheel is stopped on the yellow parking cross painted on the apron.
  Focus on the nose wheel and where it sits, not on the rest of the fuselage.
  Avoid: an aircraft that is taxiing, waiting, or standing beside the cross is false.
- tunnel_attached: true only if the passenger jet bridge is fully docked to the aircraft, with its head against the fuselage and its canopy down.
  Focus on the contact point between the bridge head and the fuselage.
  Avoid: a bridge that is near, still moving, or retracting is false, even when it is close to the aircraft.
- doors_open: true only if a cargo hold door is open. The state is true if either the front or the rear hold is open.
  On a larger aircraft the door swings outward and is visible. On a smaller aircraft the door folds inward and the open hold is a dark opening in the fuselage.
  Focus on the whole fuselage, including the rear hold, which the wing can partly hide.
  Avoid: passenger doors, closed hatches, and ground equipment near the aircraft do not count.
- description: one or two sentences describing the apron, the aircraft if present, the jet bridge, and the cargo doors.

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
        "The previous reply was not valid JSON. Look at the image again and return only "
        "one JSON object with keys parked, tunnel_attached, doors_open, and description.\n\n"
        f"Previous reply:\n{clipped}"
    )
