from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import requests

from cctv.utils.azure import AzureOpenAIConfig, load_azure_openai_config


def encode_image_to_base64(image_path: str | Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _parse_json_payload(analysis_text: str) -> dict:
    json_start = analysis_text.find("{")
    json_end = analysis_text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        return json.loads(analysis_text[json_start:json_end])
    return {"raw_response": analysis_text}


def analyze_images(
    image_paths: list[str | Path],
    prompt: str,
    config: AzureOpenAIConfig | None = None,
    *,
    parse_json: bool = True,
    max_tokens: int = 1500,
) -> dict:
    """Send one or more JPEG images plus a prompt to Azure OpenAI vision."""
    config = config or load_azure_openai_config()
    if not config.is_configured or not config.api_url:
        return {"error": "Azure OpenAI configuration missing"}

    try:
        encoded_images = [encode_image_to_base64(path) for path in image_paths]
    except Exception as exc:
        return {"error": f"Failed to encode images: {exc}"}

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

    payload = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
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
            "image_paths": [str(path) for path in image_paths],
            "image_count": len(image_paths),
            "model": config.model,
        }
    except requests.exceptions.RequestException as exc:
        return {"error": f"Azure API request failed: {exc}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


_DEFAULT_TRAFFIC_PROMPT = """
Analyze this CCTV camera image and provide detailed information about:
1. Number of vehicles (cars, trucks, buses, motorcycles) - count each type
2. Number of pedestrians visible
3. Traffic conditions (light, moderate, heavy, congested)
4. Weather conditions (sunny, cloudy, rainy, night, etc.)
5. Time of day estimate (morning, midday, afternoon, evening, night)
6. Any unusual activities or incidents
7. Overall scene description

Format your response as JSON with these fields:
{
    "vehicles": {"cars": 0, "trucks": 0, "buses": 0, "motorcycles": 0},
    "pedestrians": 0,
    "traffic_level": "light|moderate|heavy|congested",
    "weather": "description",
    "time_of_day": "morning|midday|afternoon|evening|night",
    "incidents": "description or none",
    "scene_description": "brief description"
}
"""


def analyze_camera_image(
    image_path: str | Path,
    prompt: str | None = None,
    config: AzureOpenAIConfig | None = None,
    *,
    parse_json: bool = False,
    max_tokens: int = 1000,
) -> dict:
    result = analyze_images(
        [image_path],
        prompt if prompt is not None else _DEFAULT_TRAFFIC_PROMPT,
        config=config,
        parse_json=parse_json,
        max_tokens=max_tokens,
    )
    if "image_paths" in result:
        result["image_path"] = result["image_paths"][0]
    return result
