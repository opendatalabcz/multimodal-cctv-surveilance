"""Prompt versions and JSON parsing for the three stand states."""

from __future__ import annotations

import hashlib
import json

_SHARED_INTRO = """You are looking at one frame from a fixed airport apron camera. Judge only what is visible in this frame.

Return a single JSON object and nothing else, with exactly these keys:
- parked: true only if an aircraft nose wheel is stopped on the yellow parking cross painted on the apron. An aircraft that is merely visible, taxiing, or waiting away from the cross is false.
- tunnel_attached: true only if the passenger jet bridge is fully docked to the aircraft, with its canopy down and the bridge head against the fuselage. A bridge that is only nearby or still moving is false.
"""

_DOOR_BASIC = (
    "- doors_open: true only if a cargo hold door is open. On a larger aircraft the door swings "
    "outward and is visible. On a smaller aircraft the door folds inward and the open hold is a "
    "dark opening in the fuselage. A closed hold does not count, and passenger doors do not count.\n"
)

_DOOR_DETAILED = (
    "- doors_open: true only if a cargo hold door is open. On a larger aircraft the door swings "
    "outward and is visible. On a smaller aircraft the door folds inward and the open hold is a "
    "dark opening in the fuselage. The state should be true if either the front or back door is "
    "open. The view of the back door can be partially obstructed by the wing, so you should pay "
    "more attention to that area. A closed hold does not count, and passenger doors do not count.\n"
)

_SHARED_END = """- description: one or two sentences describing the apron, the aircraft if present, the jet bridge, and the cargo doors.

Use JSON booleans.
{"parked": false, "tunnel_attached": false, "doors_open": false, "description": "..."}
"""

PROMPT_VERSIONS = {
    "basic": _SHARED_INTRO + _DOOR_BASIC + _SHARED_END,
    "detailed": _SHARED_INTRO + _DOOR_DETAILED + _SHARED_END,
}

# The detailed wording is the prompt used for the scored runs.
PROMPT = PROMPT_VERSIONS["detailed"]

_STATES = ("parked", "tunnel_attached", "doors_open")


def get_prompt(version: str) -> str:
    try:
        return PROMPT_VERSIONS[version]
    except KeyError as exc:
        known = ", ".join(PROMPT_VERSIONS)
        raise ValueError(f"Unknown prompt version {version!r}. Known versions: {known}") from exc


def prompt_id(text: str | None = None) -> str:
    """Short id that changes when the prompt text changes."""
    body = PROMPT if text is None else text
    return hashlib.sha256(body.encode()).hexdigest()[:12]


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
