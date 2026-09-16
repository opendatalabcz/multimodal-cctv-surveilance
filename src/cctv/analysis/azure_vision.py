from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import cctv.tools  # noqa: F401  — register default tools
from cctv.tools.registry import default_tool_schemas, execute_tool
from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config
from cctv.utils.paths import data_root, experiments_dir


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


def save_experiment(result: dict, place_id: str, kind: str = "run") -> Path:
    """Write a normalized analysis result to ``experiments/<place>/<kind>_<timestamp>.json``."""
    folder = experiments_dir(place_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = folder / f"{kind}_{stamp}.json"

    image_paths = result.get("image_paths")
    if image_paths:
        image_paths = [_relative_to_data_root(p) for p in image_paths]

    payload = {
        "place_id": place_id,
        "kind": kind,
        "success": result.get("success", "error" not in result),
        "timestamp": result.get("timestamp") or datetime.now().isoformat(),
        "model": result.get("model"),
        "usage": result.get("usage", {}),
        "image_paths": image_paths or [],
        "image_count": result.get("image_count", len(image_paths or [])),
        "analysis": result.get("analysis"),
        "raw_response": result.get("raw_response"),
        "error": result.get("error"),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


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
        "messages": messages,
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


def _fetched_images_message(image_paths: list[str]) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Here are the fetched frames for analysis, in tool-call order: "
                + ", ".join(Path(path).name for path in image_paths)
            ),
        }
    ]
    content.extend(_vision_image_part(path) for path in image_paths)
    return {"role": "user", "content": content}


def _finalize_tool_chat_result(
    message: dict[str, Any],
    result: dict[str, Any],
    *,
    messages: list[dict[str, Any]],
    fetched_images: list[str],
    tool_rounds: int,
    parse_json: bool,
    config: AzureOpenAIConfig,
) -> dict[str, Any]:
    analysis_text = message.get("content") or ""
    if parse_json:
        try:
            analysis = _parse_json_payload(analysis_text)
        except json.JSONDecodeError:
            analysis = {"raw_response": analysis_text}
    else:
        analysis = analysis_text
    final_messages = messages + [message]
    return {
        "success": True,
        "analysis": analysis,
        "raw_response": analysis_text,
        "usage": result.get("usage", {}),
        "timestamp": datetime.now().isoformat(),
        "image_paths": [_relative_to_data_root(path) for path in fetched_images],
        "image_count": len(fetched_images),
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
    uses the Azure chat format (roles such as user/assistant/tool). When a
    tool returns ``image_path``, the JPEG is injected in a follow-up user
    message so the VLM can see the frame. On success, ``messages`` in the
    result is the full history including the final assistant reply.
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
    fetched_images: list[str] = []
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
                    fetched_images=fetched_images,
                    tool_rounds=tool_rounds,
                    parse_json=parse_json,
                    config=config,
                )

            conversation.append(message)
            round_images: list[str] = []
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

                image_path = exec_result.get("image_path")
                if image_path:
                    fetched_images.append(image_path)
                    round_images.append(image_path)

            # Azure rejects the request unless every tool_call_id is answered by an
            # uninterrupted run of tool messages, so images follow the whole batch.
            if round_images:
                conversation.append(_fetched_images_message(round_images))

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


def analyze_camera_image(
    image_path: str | Path,
    prompt: str,
    config: AzureOpenAIConfig | None = None,
    *,
    parse_json: bool = True,
    max_tokens: int = 1000,
    temperature: float | None = None,
) -> dict:
    """Analyze a single image. ``prompt`` is required (use ``load_place_prompt``)."""
    result = analyze_images(
        [image_path],
        prompt,
        config=config,
        parse_json=parse_json,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if "image_paths" in result:
        result["image_path"] = result["image_paths"][0]
    return result
