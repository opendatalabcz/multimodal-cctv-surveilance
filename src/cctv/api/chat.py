from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import ValidationError

from cctv.analysis.azure_vision import ProgressCallback, chat_with_tools
from cctv.api.schemas import ChatMessage, ImageAnnotation, PresentedImage
from cctv.api.store import Conversation, image_urls_for_paths
from cctv.api.turn_log import append_turn_log, tool_names_from_messages
from cctv.config.agent_yaml import load_agent_config
from cctv.config.models import (
    DEFAULT_MAX_IMAGES_PER_REQUEST,
    clamp_reasoning,
    clamp_verbosity,
    model_by_id,
)
from cctv.config.prompt import build_system_prompt
from cctv.observability.tracing import start_turn
from cctv.tools.registry import tool_schemas_for_config
from cctv.utils.azure import AzureOpenAIConfig, resolve_azure_config

MAX_TOOL_ROUNDS = 16


def _presented_images(images: Any) -> list[PresentedImage]:
    if not isinstance(images, list):
        return []
    presented: list[PresentedImage] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        annotations: list[ImageAnnotation] = []
        for raw in item.get("annotations") or []:
            if not isinstance(raw, dict):
                continue
            try:
                annotations.append(ImageAnnotation.model_validate(raw))
            except ValidationError:
                continue
        presented.append(
            PresentedImage(
                url=image_urls_for_paths([path])[0],
                cameraId=str(item.get("camera_id") or ""),
                annotations=annotations,
            )
        )
    return presented


def _logged_images(images: Any) -> list[dict[str, Any]]:
    if not isinstance(images, list):
        return []
    logged: list[dict[str, Any]] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        annotations = [
            annotation.get("type")
            for annotation in item.get("annotations") or []
            if isinstance(annotation, dict) and annotation.get("type")
        ]
        logged.append({"camera_id": item.get("camera_id"), "annotations": annotations})
    return logged


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
    on_progress: ProgressCallback | None = None,
) -> tuple[Conversation, dict[str, Any]]:
    agent_config = load_agent_config()
    system_prompt = build_system_prompt(agent_config)
    active_tools = tool_schemas_for_config(agent_config.tools)
    if config is not None:
        azure_config = config
    else:
        try:
            azure_config = resolve_azure_config(agent_config)
        except ValueError as exc:
            return conversation, {"success": False, "error": str(exc)}

    conversation.messages.append(ChatMessage(role="user", content=user_content))
    conversation.azure_messages.append({"role": "user", "content": user_content})

    selected_model = azure_config.model or ""
    option = model_by_id(agent_config.models, selected_model)
    transport = option.transport if option is not None else "chat_completions"
    max_images = (
        option.max_images_per_request
        if option is not None
        else DEFAULT_MAX_IMAGES_PER_REQUEST
    )
    reasoning = clamp_reasoning(option, agent_config.reasoning.get(selected_model))
    verbosity = clamp_verbosity(option, agent_config.verbosity.get(selected_model))

    started = time.perf_counter()
    turn_id = uuid.uuid4().hex
    with start_turn(
        turn_id=turn_id,
        session_id=conversation.id,
        user_input=user_content,
        metadata={
            "model": selected_model,
            "transport": transport,
            "reasoning": reasoning,
            "verbosity": verbosity,
            "tools": [
                tool["function"]["name"]
                for tool in active_tools
                if isinstance(tool.get("function"), dict) and tool["function"].get("name")
            ],
        },
    ) as turn:
        result = chat_with_tools(
            conversation.azure_messages,
            config=azure_config,
            system_prompt=system_prompt,
            tools=active_tools,
            max_tool_rounds=MAX_TOOL_ROUNDS,
            on_progress=on_progress,
            reasoning=reasoning,
            verbosity=verbosity,
            transport=transport,
            max_images=max_images,
        )
        if result.get("success"):
            turn.update(output=_assistant_text(result.get("analysis", "")))
        else:
            error = str(result.get("error") or "Chat turn failed")
            turn.update(level="ERROR", status_message=error, output={"error": error})
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not result.get("success"):
        conversation.messages.pop()
        conversation.azure_messages.pop()
        _write_turn_log(
            conversation,
            result,
            duration_ms=duration_ms,
            tools=agent_config.tools,
            turn_id=turn_id,
        )
        return conversation, result

    conversation.azure_messages = [
        message for message in result["messages"] if message.get("role") != "system"
    ]
    assistant_content = _assistant_text(result.get("analysis", ""))
    conversation.messages.append(
        ChatMessage(
            role="assistant",
            content=assistant_content,
            images=_presented_images(result.get("images") or []),
            model=result.get("model") or azure_config.model,
        )
    )
    conversation.suggestions = list(result.get("followups") or [])
    _write_turn_log(
        conversation,
        result,
        duration_ms=duration_ms,
        tools=agent_config.tools,
        turn_id=turn_id,
    )
    return conversation, result


def _write_turn_log(
    conversation: Conversation,
    result: dict[str, Any],
    *,
    duration_ms: int,
    tools: Any,
    turn_id: str,
) -> None:
    usage = result.get("usage") or {}
    append_turn_log(
        {
            "conversation_id": conversation.id,
            "turn_id": turn_id,
            "success": bool(result.get("success")),
            "tool_rounds": result.get("tool_rounds"),
            "tool_names": tool_names_from_messages(result.get("messages") or conversation.azure_messages),
            "images": _logged_images(result.get("images") or []),
            "image_count": result.get("image_count"),
            "tokens": usage,
            "duration_ms": duration_ms,
            "model": result.get("model"),
            "timestamp": result.get("timestamp"),
            "config_tools": tools.model_dump() if hasattr(tools, "model_dump") else tools,
            "error": result.get("error"),
        }
    )
