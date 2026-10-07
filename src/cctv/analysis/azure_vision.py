from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import cctv.tools  # noqa: F401  — register default tools
from cctv.analysis.citations import (
    FetchedFrame,
    frames_from_tool_result,
    parse_cited_cameras,
    parse_followups,
    select_cited_paths,
)
from cctv.observability.tracing import (
    capture_images_enabled,
    exported_image,
    start_generation,
    start_tool,
    tracing_enabled,
)
from cctv.observability.usage import normalize_usage
from cctv.tools.get_camera import HARD_IMAGE_CAP, _camera_queries
from cctv.tools.registry import default_tool_schemas, execute_tool
from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config
from cctv.utils.paths import data_root

CCTV_FRAMES_TYPE = "cctv_frames"
ProgressCallback = Callable[[dict[str, Any]], None]

_TOOL_STATUS: dict[str, tuple[str, str]] = {
    "web_search": ("tool", "Searching the web…"),
    "get_weather": ("tool", "Looking up weather…"),
    "search_map": ("tool", "Searching the map…"),
    "reverse_geocode": ("tool", "Looking up that place…"),
    "list_cameras": ("tool", "Listing cameras…"),
}


def _emit_progress(
    on_progress: ProgressCallback | None,
    stage: str,
    detail: str,
) -> None:
    if on_progress is None:
        return
    on_progress({"type": "status", "stage": stage, "detail": detail})


def _progress_for_tool(name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    if name == "get_camera_image":
        queries = _camera_queries(arguments)
        count = len(queries)
        if count == 1:
            return "fetching", f"Fetching {queries[0]}…"
        if count > 1:
            return "fetching", f"Fetching {count} cameras…"
        return "fetching", "Fetching cameras…"
    return _TOOL_STATUS.get(name, ("tool", f"Running {name or 'a tool'}…"))


def encode_image_to_base64(image_path: str | Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _raise_for_azure_status(response: requests.Response) -> None:
    if response.ok:
        return
    detail = (response.text or "").strip().replace("\n", " ")[:1500]
    if detail:
        raise requests.HTTPError(
            f"{response.status_code} {response.reason} for url: {response.url}: {detail}",
            response=response,
        )
    response.raise_for_status()


def _parse_json_payload(analysis_text: str) -> dict:
    json_start = analysis_text.find("{")
    json_end = analysis_text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        return json.loads(analysis_text[json_start:json_end])
    return {"raw_response": analysis_text}


def _relative_to_data_root(path: str | Path) -> str:
    path = Path(path).resolve()
    root = data_root().resolve()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def analyze_images(
    image_paths: list[str | Path],
    prompt: str,
    config: AzureOpenAIConfig | None = None,
    *,
    parse_json: bool = True,
    max_tokens: int = 1500,
    temperature: float | None = None,
) -> dict:
    """Send one or more JPEG images plus a prompt to Azure OpenAI vision.

    ``max_tokens`` is sent as ``max_completion_tokens``. ``temperature`` is only
    included when set, since newer deployments accept the default value only.
    """
    config = config or load_azure_openai_config()
    if not config.is_configured or not config.api_url:
        return {"success": False, "error": "Azure OpenAI configuration missing"}

    try:
        encoded_images = [encode_image_to_base64(path) for path in image_paths]
    except Exception as exc:
        return {"success": False, "error": f"Failed to encode images: {exc}"}

    content: list[dict] = [{"type": "text", "text": prompt}]
    for encoded in encoded_images:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}",
                    "detail": "high",
                },
            }
        )

    payload: dict = {
        "model": config.model,
        "messages": [{"role": "user", "content": content}],
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        names = [Path(path).name for path in image_paths]
        print(f"Analyzing {len(image_paths)} image(s): {', '.join(names)}")
        result = _traced_post(
            config.api_url or "",
            payload,
            config,
            timeout=90,
            name="analyze-images",
            model_parameters=_model_parameters(
                transport="chat_completions",
                max_tokens=max_tokens,
                temperature=temperature,
            ),
            metadata={
                "image_paths": [str(path) for path in image_paths],
                "image_count": len(image_paths),
            },
            include_images=capture_images_enabled(),
        )
        analysis_text = result["choices"][0]["message"]["content"]
        if parse_json:
            try:
                analysis = _parse_json_payload(analysis_text)
            except json.JSONDecodeError:
                analysis = {"raw_response": analysis_text}
        else:
            analysis = analysis_text
        return {
            "success": True,
            "analysis": analysis,
            "raw_response": analysis_text,
            "usage": result.get("usage", {}),
            "timestamp": datetime.now().isoformat(),
            "image_paths": [_relative_to_data_root(path) for path in image_paths],
            "image_count": len(image_paths),
            "model": config.model,
        }
    except requests.exceptions.RequestException as exc:
        return {"success": False, "error": f"Azure API request failed: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error: {exc}"}


def _chat_completion_payload(
    messages: list[dict[str, Any]],
    config: AzureOpenAIConfig,
    *,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1500,
    temperature: float | None = None,
    reasoning: str | None = None,
    verbosity: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": materialize_for_azure(messages),
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning and reasoning != "default":
        payload["reasoning_effort"] = reasoning
    if verbosity and verbosity != "medium":
        payload["verbosity"] = verbosity
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def _post_json(
    url: str,
    payload: dict[str, Any],
    config: AzureOpenAIConfig,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "api-key": config.api_key,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    _raise_for_azure_status(response)
    return response.json()


def _post_chat_completion(
    payload: dict[str, Any],
    config: AzureOpenAIConfig,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    if not config.api_url:
        raise requests.RequestException("Azure OpenAI configuration missing")
    return _post_json(config.api_url, payload, config, timeout=timeout)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _model_parameters(
    *,
    transport: str,
    max_tokens: int,
    temperature: float | None = None,
    reasoning: str | None = None,
    verbosity: str | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"transport": transport, "max_tokens": max_tokens}
    if temperature is not None:
        parameters["temperature"] = temperature
    if reasoning:
        parameters["reasoning"] = reasoning
    if verbosity:
        parameters["verbosity"] = verbosity
    return parameters


def _latest_image_refs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for message in reversed(messages):
        frames = _frames_from_message(message)
        if frames:
            return [
                {
                    "path": frame.path,
                    "camera_id": frame.camera_id,
                    "camera_name": frame.camera_name,
                }
                for frame in frames
            ]
    return []


def _parsed_tool_content(exec_result: dict[str, Any]) -> Any:
    content = exec_result.get("tool_content")
    if not isinstance(content, str):
        return content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def _tool_succeeded(parsed: Any) -> bool:
    return not (isinstance(parsed, dict) and parsed.get("success") is False)


def _traced_post(
    url: str,
    payload: dict[str, Any],
    config: AzureOpenAIConfig,
    *,
    timeout: int,
    name: str,
    metadata: dict[str, Any] | None = None,
    model_parameters: dict[str, Any] | None = None,
    include_images: bool = False,
) -> dict[str, Any]:
    observed = dict(metadata or {})
    with start_generation(
        name=name,
        model=config.model,
        input=payload,
        model_parameters=model_parameters,
        metadata=observed,
        include_images=include_images,
    ) as generation:
        started = time.perf_counter()
        try:
            if config.api_url and url == config.api_url:
                result = _post_chat_completion(payload, config, timeout=timeout)
            else:
                result = _post_json(url, payload, config, timeout=timeout)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            generation.update(
                level="ERROR",
                status_message=str(exc),
                metadata={**observed, "http_status": status, "duration_ms": _elapsed_ms(started)},
            )
            raise
        except Exception as exc:
            generation.update(
                level="ERROR",
                status_message=str(exc),
                metadata={**observed, "duration_ms": _elapsed_ms(started)},
            )
            raise
        generation.update(
            output=result,
            usage_details=normalize_usage(result.get("usage")),
            metadata={**observed, "http_status": 200, "duration_ms": _elapsed_ms(started)},
        )
        return result


def _responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") or {}
        converted.append(
            {
                "type": "function",
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "parameters": function.get("parameters") or {"type": "object", "properties": {}},
                "strict": False,
            }
        )
    return converted


def _responses_content(content: Any, *, role: str) -> list[dict[str, Any]] | str:
    text_type = "output_text" if role == "assistant" else "input_text"
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            parts.append({"type": text_type, "text": part.get("text") or ""})
        elif part_type == "image_url":
            image = part.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
            if url:
                parts.append({"type": "input_image", "image_url": url})
    return parts


def _responses_input(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Turn stored chat messages into Responses instructions plus input items."""
    instructions: list[str] = []
    items: list[dict[str, Any]] = []
    for message in materialize_for_azure(messages):
        role = message.get("role")
        if role == "system":
            content = message.get("content")
            if isinstance(content, str) and content:
                instructions.append(content)
            continue
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id") or "",
                    "output": message.get("content") if isinstance(message.get("content"), str) else "",
                }
            )
            continue
        tool_calls = message.get("tool_calls") or []
        if role == "assistant":
            items.extend(_stored_reasoning_items(message))
        content = _responses_content(message.get("content"), role=role or "user")
        has_text = (isinstance(content, str) and content) or (
            isinstance(content, list) and len(content) > 0
        )
        if has_text:
            items.append({"type": "message", "role": role or "user", "content": content})
        for call in tool_calls:
            function = call.get("function") or {}
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.get("id") or "",
                    "name": function.get("name") or "",
                    "arguments": function.get("arguments") or "{}",
                }
            )
    return "\n\n".join(instructions), items


def _responses_payload(
    messages: list[dict[str, Any]],
    config: AzureOpenAIConfig,
    *,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1500,
    reasoning: str | None = None,
    verbosity: str | None = None,
) -> dict[str, Any]:
    instructions, items = _responses_input(messages)
    effective_reasoning = "medium" if not reasoning or reasoning == "default" else reasoning
    payload: dict[str, Any] = {
        "model": config.model,
        "input": items,
        "max_output_tokens": max_tokens,
        "reasoning": {"effort": effective_reasoning},
        "include": ["reasoning.encrypted_content"],
    }
    if verbosity and verbosity != "medium":
        payload["text"] = {"verbosity": verbosity}
    if instructions:
        payload["instructions"] = instructions
    if tools:
        payload["tools"] = _responses_tools(tools)
    return payload


def _responses_output_text(result: dict[str, Any]) -> str:
    """Visible assistant text only. Reasoning items and summaries stay hidden."""
    chunks: list[str] = []
    for item in result.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                chunks.append(part.get("text") or "")
    return "\n".join(chunk for chunk in chunks if chunk)


def _reasoning_replay_item(item: dict[str, Any]) -> dict[str, Any]:
    """Opaque fields Azure needs to continue a thought. Readable reasoning is dropped."""
    record = {"type": "reasoning"}
    for field in ("id", "summary", "encrypted_content"):
        if field in item and item[field] is not None:
            record[field] = item[field]
    return record


def _stored_reasoning_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    stored = message.get("reasoning_items") or []
    if not isinstance(stored, list):
        return []
    return [
        item
        for item in stored
        if isinstance(item, dict) and item.get("type") == "reasoning"
    ]


def _assistant_message_from_responses(result: dict[str, Any]) -> dict[str, Any]:
    tool_calls = []
    reasoning_items = []
    for item in result.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "reasoning":
            reasoning_items.append(_reasoning_replay_item(item))
            continue
        if item.get("type") != "function_call":
            continue
        tool_calls.append(
            {
                "id": item.get("call_id") or item.get("id") or "",
                "type": "function",
                "function": {
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                },
            }
        )
    message: dict[str, Any] = {"role": "assistant", "content": _responses_output_text(result)}
    if reasoning_items:
        message["reasoning_items"] = reasoning_items
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _vision_image_part(image_path: str | Path) -> dict[str, Any]:
    encoded = encode_image_to_base64(image_path)
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{encoded}",
            "detail": "high",
        },
    }


def _frame_label(frame: FetchedFrame) -> str:
    return frame.camera_id or Path(frame.path).stem


def _frames_payload(frames: list[FetchedFrame]) -> list[dict[str, Any]]:
    return [
        {
            "path": frame.path,
            "camera_id": frame.camera_id,
            "camera_name": frame.camera_name,
        }
        for frame in frames
    ]


def _fetched_images_message(frames: list[FetchedFrame]) -> dict[str, Any]:
    labels: list[str] = []
    for index, frame in enumerate(frames, start=1):
        camera_id = _frame_label(frame)
        if frame.camera_name:
            labels.append(f"{index}. id={camera_id} name={frame.camera_name}")
        else:
            labels.append(f"{index}. id={camera_id}")
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Here are the fetched frames for analysis, in this order. "
                "Cite by camera id in a ```cite``` block when you answer. "
                "Do not use sep, ..sep, or any other fence language for citations.\n"
                + "\n".join(labels)
            ),
        },
        {"type": CCTV_FRAMES_TYPE, "frames": _frames_payload(frames)},
    ]
    return {"role": "user", "content": content}


def _frames_from_part(part: dict[str, Any]) -> list[FetchedFrame]:
    if part.get("type") != CCTV_FRAMES_TYPE:
        return []
    raw = part.get("frames")
    if not isinstance(raw, list):
        return []
    frames: list[FetchedFrame] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        camera_id = item.get("camera_id")
        camera_name = item.get("camera_name")
        frames.append(
            FetchedFrame(
                path=str(item["path"]),
                camera_id=str(camera_id) if camera_id else None,
                camera_name=str(camera_name) if camera_name else None,
            )
        )
    return frames


def _frames_from_message(message: dict[str, Any]) -> list[FetchedFrame]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    frames: list[FetchedFrame] = []
    for part in content:
        if isinstance(part, dict):
            frames.extend(_frames_from_part(part))
    return frames


def _has_visual_payload(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if not isinstance(content, list):
        return False
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == CCTV_FRAMES_TYPE and _frames_from_part(part):
            return True
        if part.get("type") == "image_url":
            return True
    return False


def _previously_viewed_text(frames: list[FetchedFrame]) -> str:
    labels = [_frame_label(frame) for frame in frames if _frame_label(frame)]
    if not labels:
        return "Previously viewed camera frames (no longer attached)."
    return "Previously viewed: " + ", ".join(labels)


def _stub_user_message(frames: list[FetchedFrame]) -> dict[str, Any]:
    return {"role": "user", "content": _previously_viewed_text(frames)}


def _expand_visual_message(
    message: dict[str, Any],
    max_images: int = HARD_IMAGE_CAP,
) -> dict[str, Any]:
    content = message.get("content")
    if not isinstance(content, list):
        return message
    text_parts = [
        part for part in content if isinstance(part, dict) and part.get("type") == "text"
    ]
    image_parts = [
        part for part in content if isinstance(part, dict) and part.get("type") == "image_url"
    ]
    frames = _frames_from_message(message)
    if image_parts and not frames:
        return {**message, "content": [*text_parts, *image_parts[:max_images]]}
    expanded = list(text_parts)
    for frame in frames[:max_images]:
        try:
            expanded.append(_vision_image_part(frame.path))
        except OSError:
            continue
    return {**message, "content": expanded}


def materialize_for_azure(
    messages: list[dict[str, Any]],
    max_images: int = HARD_IMAGE_CAP,
) -> list[dict[str, Any]]:
    """Expand only the latest frame-ref (or legacy vision) message for Azure."""
    visual_indices = [index for index, message in enumerate(messages) if _has_visual_payload(message)]
    latest = visual_indices[-1] if visual_indices else None
    materialized: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not _has_visual_payload(message):
            materialized.append(message)
            continue
        if index == latest:
            materialized.append(_expand_visual_message(message, max_images=max_images))
        else:
            materialized.append(_stub_user_message(_frames_from_message(message)))
    return materialized


def _compact_frame_refs_for_storage(
    messages: list[dict[str, Any]],
    kept_frames: list[FetchedFrame],
) -> list[dict[str, Any]]:
    visual_indices = [index for index, message in enumerate(messages) if _has_visual_payload(message)]
    latest = visual_indices[-1] if visual_indices else None
    compacted: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not _has_visual_payload(message):
            compacted.append(message)
            continue
        frames = _frames_from_message(message)
        if index == latest and kept_frames:
            compacted.append(_fetched_images_message(kept_frames))
        else:
            compacted.append(_stub_user_message(frames))
    return compacted


def _kept_frames_for_citations(
    fetched_frames: list[FetchedFrame],
    display_paths: list[str],
) -> list[FetchedFrame]:
    by_path = {str(frame.path): frame for frame in fetched_frames}
    kept: list[FetchedFrame] = []
    seen: set[str] = set()
    for path in display_paths:
        key = str(path)
        frame = by_path.get(key)
        if frame is None or key in seen:
            continue
        seen.add(key)
        kept.append(frame)
    return kept


def _finalize_tool_chat_result(
    message: dict[str, Any],
    result: dict[str, Any],
    *,
    messages: list[dict[str, Any]],
    fetched_frames: list[FetchedFrame],
    tool_rounds: int,
    parse_json: bool,
    config: AzureOpenAIConfig,
) -> dict[str, Any]:
    analysis_text = message.get("content") or ""
    without_followups, followups = parse_followups(analysis_text)
    display_text, citations = parse_cited_cameras(without_followups)
    display_paths = select_cited_paths(fetched_frames, citations)
    message = {**message, "content": display_text}
    if parse_json:
        try:
            analysis = _parse_json_payload(display_text)
        except json.JSONDecodeError:
            analysis = {"raw_response": display_text}
    else:
        analysis = display_text
    stored = list(messages)
    if fetched_frames:
        stored = _compact_frame_refs_for_storage(
            stored,
            _kept_frames_for_citations(fetched_frames, display_paths),
        )
    final_messages = stored + [message]
    return {
        "success": True,
        "analysis": analysis,
        "raw_response": analysis_text,
        "usage": result.get("usage", {}),
        "timestamp": datetime.now().isoformat(),
        "image_paths": [_relative_to_data_root(path) for path in display_paths],
        "image_count": len(display_paths),
        "model": config.model,
        "tool_rounds": tool_rounds,
        "messages": final_messages,
        "followups": followups,
    }


def chat_with_tools(
    messages: list[dict[str, Any]],
    config: AzureOpenAIConfig | None = None,
    *,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    parse_json: bool = False,
    max_tokens: int = 1500,
    temperature: float | None = None,
    max_tool_rounds: int = 3,
    request_timeout: int = 90,
    on_progress: ProgressCallback | None = None,
    reasoning: str | None = None,
    verbosity: str | None = None,
    transport: str = "chat_completions",
) -> dict[str, Any]:
    """Run a multi-turn Azure vision chat with function calling.

    Default tools are ``list_cameras`` and ``get_camera_image``. ``messages``
    uses the Azure chat format (roles such as user/assistant/tool).     When a
    tool returns ``image_path`` / ``image_paths``, a frame-ref user message is
    stored (paths, not base64). Each Azure POST expands only the latest
    frame-ref to vision parts. After the turn, older refs become text stubs
    and the latest ref is narrowed to cited frames. ``image_paths`` in the
    result are the frames cited in the final reply (or all fetched frames
    if the model omitted the cite block). On success, ``messages`` is the
    compact history including the final assistant reply with the cite fence
    stripped. ``on_progress`` receives status dicts (stage + detail) for the UI.
    """
    config = config or load_azure_openai_config()
    if not config.is_configured or not config.api_url:
        return {"success": False, "error": "Azure OpenAI configuration missing"}
    if transport == "responses" and not config.responses_url:
        return {"success": False, "error": "Azure OpenAI configuration missing"}

    active_tools = tools if tools is not None else default_tool_schemas()
    history = [message for message in messages if message.get("role") != "system"]
    conversation: list[dict[str, Any]] = []
    if system_prompt:
        conversation.append({"role": "system", "content": system_prompt})
    conversation.extend(history)
    fetched_frames: list[FetchedFrame] = []
    tool_rounds = 0

    try:
        while tool_rounds <= max_tool_rounds:
            _emit_progress(on_progress, "thinking", "Thinking…")
            round_tools = active_tools if tool_rounds < max_tool_rounds else None
            parameters = _model_parameters(
                transport=transport,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning=reasoning,
                verbosity=verbosity,
            )
            metadata: dict[str, Any] = {"round": tool_rounds + 1, "transport": transport}
            image_refs = _latest_image_refs(conversation)
            if image_refs:
                metadata["images"] = image_refs
            if transport == "responses":
                payload = _responses_payload(
                    conversation,
                    config,
                    tools=round_tools,
                    max_tokens=max_tokens,
                    reasoning=reasoning,
                    verbosity=verbosity,
                )
                result = _traced_post(
                    config.responses_url or "",
                    payload,
                    config,
                    timeout=request_timeout,
                    name="azure-responses",
                    metadata=metadata,
                    model_parameters=parameters,
                )
                message = _assistant_message_from_responses(result)
            else:
                payload = _chat_completion_payload(
                    conversation,
                    config,
                    tools=round_tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning=reasoning,
                    verbosity=verbosity,
                )
                result = _traced_post(
                    config.api_url or "",
                    payload,
                    config,
                    timeout=request_timeout,
                    name="azure-chat",
                    metadata=metadata,
                    model_parameters=parameters,
                )
                message = result["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                return _finalize_tool_chat_result(
                    message,
                    result,
                    messages=conversation,
                    fetched_frames=fetched_frames,
                    tool_rounds=tool_rounds,
                    parse_json=parse_json,
                    config=config,
                )

            conversation.append(message)
            round_frames: list[FetchedFrame] = []
            for tool_call in tool_calls:
                fn = tool_call.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                stage, detail = _progress_for_tool(name, args)
                _emit_progress(on_progress, stage, detail)
                with start_tool(name=name or "tool", arguments=args) as tool_span:
                    tool_started = time.perf_counter()
                    try:
                        exec_result = execute_tool(name, args)
                    except Exception as exc:
                        tool_span.update(
                            level="ERROR",
                            status_message=str(exc),
                            metadata={
                                "duration_ms": _elapsed_ms(tool_started),
                                "success": False,
                            },
                        )
                        raise
                    parsed = _parsed_tool_content(exec_result)
                    succeeded = _tool_succeeded(parsed)
                    frames = frames_from_tool_result(exec_result, args)
                    images = (
                        [
                            exported_image(
                                frame.path,
                                camera_id=frame.camera_id,
                                camera_name=frame.camera_name,
                            )
                            for frame in frames
                        ]
                        if tracing_enabled()
                        else []
                    )
                    tool_metadata = {
                        "duration_ms": _elapsed_ms(tool_started),
                        "success": succeeded,
                        "image_count": len(frames),
                    }
                    if succeeded:
                        tool_span.update(
                            output={"content": parsed, "images": images},
                            metadata=tool_metadata,
                        )
                    else:
                        error = parsed.get("error") if isinstance(parsed, dict) else None
                        tool_span.update(
                            output={"content": parsed, "images": images},
                            metadata=tool_metadata,
                            level="ERROR",
                            status_message=str(error or "Tool failed"),
                        )
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": exec_result["tool_content"],
                    }
                )

                fetched_frames.extend(frames)
                round_frames.extend(frames)

            # Azure rejects the request unless every tool_call_id is answered by an
            # uninterrupted run of tool messages, so images follow the whole batch.
            if round_frames:
                conversation.append(_fetched_images_message(round_frames))
                count = len(round_frames)
                analyzing = (
                    "Analyzing the camera frame…"
                    if count == 1
                    else f"Analyzing {count} camera frames…"
                )
                _emit_progress(on_progress, "analyzing", analyzing)

            tool_rounds += 1

        return {"success": False, "error": f"Exceeded max tool rounds ({max_tool_rounds})"}
    except requests.exceptions.RequestException as exc:
        return {"success": False, "error": f"Azure API request failed: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error: {exc}"}


def analyze_with_tools(
    prompt: str,
    config: AzureOpenAIConfig | None = None,
    *,
    tools: list[dict[str, Any]] | None = None,
    parse_json: bool = True,
    max_tokens: int = 1500,
    temperature: float | None = None,
    max_tool_rounds: int = 3,
    request_timeout: int = 90,
) -> dict[str, Any]:
    """Run a single-turn Azure vision chat with the default camera tools."""
    result = chat_with_tools(
        [{"role": "user", "content": prompt}],
        config=config,
        tools=tools,
        parse_json=parse_json,
        max_tokens=max_tokens,
        temperature=temperature,
        max_tool_rounds=max_tool_rounds,
        request_timeout=request_timeout,
    )
    result.pop("messages", None)
    return result
