"""Normalize Azure Chat Completions and Responses usage objects."""

from __future__ import annotations

from typing import Any


def normalize_usage(usage: Any) -> dict[str, int] | None:
    """Map provider token fields onto Langfuse ``input`` / ``output`` / ``total``."""
    if not isinstance(usage, dict):
        return None
    input_tokens = _first_int(usage, "input_tokens", "prompt_tokens", "input")
    output_tokens = _first_int(usage, "output_tokens", "completion_tokens", "output")
    total = _first_int(usage, "total_tokens", "total")
    if total is None and input_tokens is not None and output_tokens is not None:
        total = input_tokens + output_tokens
    details: dict[str, int] = {}
    if input_tokens is not None:
        details["input"] = input_tokens
    if output_tokens is not None:
        details["output"] = output_tokens
    if total is not None:
        details["total"] = total
    return details or None


def _first_int(usage: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
    return None
