import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from cctv.analysis.azure_vision import analyze_with_tools
from cctv.utils.azure import AzureOpenAIConfig


def _fake_config() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        api_key="test-key",
        endpoint="https://example.openai.azure.com",
        model="gpt-test",
    )


def _jpeg_file(path: Path) -> None:
    Image.new("RGB", (8, 8), (255, 0, 0)).save(path, format="JPEG")


def test_analyze_with_tools_one_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    image_path = tmp_path / "frame.jpg"
    _jpeg_file(image_path)

    tool_call_id = "call_123"
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": json.dumps({"camera": "charles_bridge"}),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"total_tokens": 10},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"summary":"quiet street"}',
                    }
                }
            ],
            "usage": {"total_tokens": 20},
        },
    ]

    posted_payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        from unittest.mock import MagicMock

        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = responses[len(posted_payloads) - 1]
        return response

    fetch_result = {
        "tool_content": json.dumps(
            {
                "success": True,
                "source_type": "prague_camera",
                "filepath": str(image_path),
                "likely_unavailable": False,
            }
        ),
        "image_path": str(image_path),
        "fetch_result": {"success": True, "filepath": str(image_path)},
    }

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", return_value=fetch_result),
    ):
        result = analyze_with_tools(
            "Fetch the Prague camera and describe crowd levels.",
            config=_fake_config(),
        )

    assert result["success"] is True
    assert result["analysis"] == {"summary": "quiet street"}
    assert result["tool_rounds"] == 1
    assert result["image_count"] == 1
    assert len(posted_payloads) == 2
    tool_names = [item["function"]["name"] for item in posted_payloads[0]["tools"]]
    assert tool_names == ["list_cameras", "get_camera_image"]

    second_messages = posted_payloads[1]["messages"]
    roles = [msg["role"] for msg in second_messages]
    assert roles == ["user", "assistant", "tool", "user"]

    image_user = second_messages[-1]["content"]
    assert any(part.get("type") == "image_url" for part in image_user)


def test_analyze_with_tools_missing_config() -> None:
    config = AzureOpenAIConfig(api_key=None, endpoint=None, model=None)
    result = analyze_with_tools("hello", config=config)
    assert result["success"] is False
    assert "configuration missing" in result["error"]
