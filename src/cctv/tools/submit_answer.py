"""Terminal tool: the visible answer, cited cameras, and follow-up questions."""

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
            "Put the markdown the user should see in answer, the configured camera "
            "ids that answer discusses in camera_ids, and up to three short next "
            "questions in followups. Do not mention this tool in the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Markdown reply shown to the user.",
                },
                "camera_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Configured camera ids discussed in the answer. "
                        "Use an empty list when the answer discusses no frames."
                    ),
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
            "required": ["answer", "camera_ids", "followups"],
            "additionalProperties": False,
        },
    },
}

_EMPTY_ANSWER = "submit_answer requires a non-empty answer."
_WAIT_FOR_TOOLS = (
    "Call submit_answer only after the other tools in this round have finished."
)


def execute_submit_answer(_arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """The chat loop intercepts this tool. A direct call is not a finished turn."""
    return {
        "tool_content": json.dumps({"success": False, "error": _WAIT_FOR_TOOLS}),
        "image_path": None,
        "image_paths": [],
    }


def submit_tool_error(reason: str) -> str:
    return json.dumps({"success": False, "error": reason})


def empty_answer_error() -> str:
    return submit_tool_error(_EMPTY_ANSWER)


def wait_for_tools_error() -> str:
    return submit_tool_error(_WAIT_FOR_TOOLS)
