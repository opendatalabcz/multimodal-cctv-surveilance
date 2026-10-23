"""Terminal tool: the visible answer, presented images, and follow-up questions."""

from __future__ import annotations

import json
from typing import Any

SUBMIT_ANSWER = "submit_answer"

SUBMIT_ANSWER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SUBMIT_ANSWER,
        "description": (
            "Finish the turn. Call this only after every other tool has returned. "
            "Put the markdown the user should see in answer, the frames to show in "
            "images, and up to three short next questions in followups. "
            "Do not mention this tool in the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Markdown reply shown to the user.",
                },
                "images": {
                    "type": "array",
                    "description": (
                        "Frames to show, in display order. Use an empty list when "
                        "the answer shows no frames. Only include cameras fetched "
                        "in this turn."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "camera_id": {
                                "type": "string",
                                "description": "Configured id of a frame fetched in this turn.",
                            },
                            "annotations": {
                                "type": "array",
                                "description": (
                                    "Highlights on this frame. Use an empty list when none fit. "
                                    "Coordinates are integers from 0 to 1000, with x and y "
                                    "normalized independently. Omit annotations you cannot place."
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["box", "point", "line", "polygon"],
                                            "description": (
                                                "box: two opposite corners. point: one point. "
                                                "line: 2 to 8 points. polygon: 3 to 12 points."
                                            ),
                                        },
                                        "label": {
                                            "type": "string",
                                            "description": "Optional label, at most 80 characters.",
                                        },
                                        "points": {
                                            "type": "array",
                                            "items": {
                                                "type": "array",
                                                "items": {"type": "integer"},
                                                "minItems": 2,
                                                "maxItems": 2,
                                            },
                                        },
                                    },
                                    "required": ["type", "points"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["camera_id", "annotations"],
                        "additionalProperties": False,
                    },
                },
                "followups": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Up to three short questions the user could ask next, "
                        "in the user's voice. Use an empty list when none fit."
                    ),
                },
            },
            "required": ["answer", "images", "followups"],
            "additionalProperties": False,
        },
    },
}

_EMPTY_ANSWER = "submit_answer requires a non-empty answer."
_WAIT_FOR_TOOLS = (
    "Call submit_answer only after the other tools in this round have finished."
)


def submit_tool_error(reason: str) -> str:
    return json.dumps({"success": False, "error": reason})


def empty_answer_error() -> str:
    return submit_tool_error(_EMPTY_ANSWER)


def wait_for_tools_error() -> str:
    return submit_tool_error(_WAIT_FOR_TOOLS)
