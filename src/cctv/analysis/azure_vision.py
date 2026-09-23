from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import cctv.tools  # noqa: F401  — register default tools
from cctv.analysis.citations import (
    FetchedFrame,
    frames_from_tool_result,
    parse_cited_cameras,
    select_cited_paths,
)
from cctv.tools.get_camera import HARD_IMAGE_CAP
from cctv.tools.registry import default_tool_schemas, execute_tool
from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config
from cctv.utils.paths import data_root

CCTV_FRAMES_TYPE = "cctv_frames"


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
    headers = {
        "Content-Type": "application/json",
        "api-key": config.api_key,
    }

    try:
        names = [Path(path).name for path in image_paths]
        print(f"Analyzing {len(image_paths)} image(s): {', '.join(names)}")
        response = requests.post(config.api_url, headers=headers, json=payload, timeout=90)
        _raise_for_azure_status(response)
        result = response.json()
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
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": materialize_for_azure(messages),
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def _post_chat_completion(
    payload: dict[str, Any],
    config: AzureOpenAIConfig,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "api-key": config.api_key,
    }
    response = requests.post(config.api_url, headers=headers, json=payload, timeout=timeout)
    _raise_for_azure_status(response)
    return response.json()


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
    display_text, citations = parse_cited_cameras(analysis_text)
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
    stripped.
    """
    config = config or load_azure_openai_config()
    if not config.is_configured or not config.api_url:
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
            payload = _chat_completion_payload(
                conversation,
                config,
                tools=active_tools if tool_rounds < max_tool_rounds else None,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            result = _post_chat_completion(payload, config, timeout=request_timeout)
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
                exec_result = execute_tool(name, args)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": exec_result["tool_content"],
                    }
                )

                frames = frames_from_tool_result(exec_result, args)
                fetched_frames.extend(frames)
                round_frames.extend(frames)

            # Azure rejects the request unless every tool_call_id is answered by an
            # uninterrupted run of tool messages, so images follow the whole batch.
            if round_frames:
                conversation.append(_fetched_images_message(round_frames))

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
