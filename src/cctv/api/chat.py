from __future__ import annotations

import time
from typing import Any

from cctv.analysis.azure_vision import chat_with_tools
from cctv.api.schemas import ChatMessage
from cctv.api.store import Conversation, image_urls_for_paths
from cctv.api.turn_log import append_turn_log, tool_names_from_messages
from cctv.config.agent_yaml import load_agent_config
from cctv.config.prompt import build_system_prompt
from cctv.tools.registry import tool_schemas_for_config
from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config

MAX_TOOL_ROUNDS = 16


def _assistant_text(analysis: Any) -> str:
    if isinstance(analysis, str):
        return analysis
    if isinstance(analysis, dict):
        if "raw_response" in analysis:
            return str(analysis["raw_response"])
        return str(analysis)
    return str(analysis)


def run_chat_turn(
    conversation: Conversation,
    user_content: str,
    *,
    config: AzureOpenAIConfig | None = None,
) -> tuple[Conversation, dict[str, Any]]:
    agent_config = load_agent_config()
    system_prompt = build_system_prompt(agent_config)
    active_tools = tool_schemas_for_config(agent_config.tools)
    azure_config = config or load_azure_openai_config()

    conversation.messages.append(ChatMessage(role="user", content=user_content))
    conversation.azure_messages.append({"role": "user", "content": user_content})

    started = time.perf_counter()
    result = chat_with_tools(
        conversation.azure_messages,
        config=azure_config,
        system_prompt=system_prompt,
        tools=active_tools,
        parse_json=False,
        max_tool_rounds=MAX_TOOL_ROUNDS,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not result.get("success"):
        conversation.messages.pop()
        conversation.azure_messages.pop()
        _write_turn_log(conversation, result, duration_ms=duration_ms, tools=agent_config.tools)
        return conversation, result

    conversation.azure_messages = [
        message for message in result["messages"] if message.get("role") != "system"
    ]
    assistant_content = _assistant_text(result.get("analysis", ""))
    image_urls = image_urls_for_paths(result.get("image_paths") or [])
    conversation.messages.append(
        ChatMessage(
            role="assistant",
            content=assistant_content,
            imageUrls=image_urls,
        )
    )
    _write_turn_log(conversation, result, duration_ms=duration_ms, tools=agent_config.tools)
    return conversation, result


def _write_turn_log(
    conversation: Conversation,
    result: dict[str, Any],
    *,
    duration_ms: int,
    tools: Any,
) -> None:
    usage = result.get("usage") or {}
    append_turn_log(
        {
            "conversation_id": conversation.id,
            "success": bool(result.get("success")),
            "tool_rounds": result.get("tool_rounds"),
            "tool_names": tool_names_from_messages(result.get("messages") or conversation.azure_messages),
            "cameras": result.get("image_paths") or [],
            "image_count": result.get("image_count"),
            "tokens": usage,
            "duration_ms": duration_ms,
            "model": result.get("model"),
            "timestamp": result.get("timestamp"),
            "config_tools": tools.model_dump() if hasattr(tools, "model_dump") else tools,
            "error": result.get("error"),
        }
    )
