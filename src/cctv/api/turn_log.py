from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cctv.utils.paths import data_root

TURN_LOG_RELATIVE = Path("logs") / "chat_turns.jsonl"


def turn_log_path() -> Path:
    return data_root() / TURN_LOG_RELATIVE


def append_turn_log(entry: dict[str, Any]) -> None:
    path = turn_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def tool_names_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            name = function.get("name")
            if name:
                names.append(str(name))
    return names
