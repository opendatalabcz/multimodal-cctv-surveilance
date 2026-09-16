"""Keyless web search via DuckDuckGo (ddgs)."""

from __future__ import annotations

import json
from typing import Any

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the public web for recent news or context. "
            "Returns up to 5 text results (title, URL, snippet). "
            "Do not use this as a weather API; use get_weather for forecasts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. Prague traffic news today.",
                }
            },
            "required": ["query"],
        },
    },
}

MAX_RESULTS = 5


def _normalize_result(row: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(row.get("title") or "").strip(),
        "url": str(row.get("href") or row.get("url") or "").strip(),
        "snippet": str(row.get("body") or row.get("snippet") or "").strip(),
    }


def execute_web_search(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    query = str(args.get("query") or "").strip()
    if not query:
        return {
            "tool_content": json.dumps(
                {"success": False, "error": "Missing required argument: query"},
                ensure_ascii=False,
            ),
            "image_path": None,
        }

    try:
        from ddgs import DDGS

        rows: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=MAX_RESULTS):
                if not isinstance(row, dict):
                    continue
                normalized = _normalize_result(row)
                if normalized["title"] or normalized["url"]:
                    rows.append(normalized)
        if not rows:
            return {
                "tool_content": json.dumps(
                    {
                        "success": False,
                        "error": "No search results returned",
                        "query": query,
                    },
                    ensure_ascii=False,
                ),
                "image_path": None,
            }
        payload = {
            "success": True,
            "query": query,
            "results": rows,
            "count": len(rows),
            "source": "DuckDuckGo",
            "attribution": "Results from DuckDuckGo (ddgs); availability not guaranteed.",
        }
        return {
            "tool_content": json.dumps(payload, ensure_ascii=False),
            "image_path": None,
        }
    except Exception as exc:
        return {
            "tool_content": json.dumps(
                {
                    "success": False,
                    "error": f"Web search unavailable: {exc}",
                    "query": query,
                },
                ensure_ascii=False,
            ),
            "image_path": None,
        }
