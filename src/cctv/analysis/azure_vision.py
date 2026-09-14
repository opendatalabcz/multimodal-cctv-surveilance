from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import requests

from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config
from cctv.utils.paths import data_root, experiments_dir


def encode_image_to_base64(image_path: str | Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


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
        response.raise_for_status()
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
