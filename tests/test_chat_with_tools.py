from unittest.mock import MagicMock, patch

import cctv.tools  # noqa: F401
from cctv.analysis.azure_vision import chat_with_tools
from cctv.utils.azure import AzureOpenAIConfig


def _fake_config() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        api_key="test-key",
        endpoint="https://example.openai.azure.com",
        model="gpt-test",
    )


def test_chat_with_tools_multi_turn_history() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I can check that camera for you.",
                    }
                }
            ],
            "usage": {"total_tokens": 5},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "It looks quiet now.",
                    }
                }
            ],
            "usage": {"total_tokens": 8},
        },
    ]

    posted_payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = responses[len(posted_payloads) - 1]
        return response

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        first_result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )
        history = list(first_result["messages"])
        history.append({"role": "user", "content": "What changed since last time?"})
        second_result = chat_with_tools(
            history,
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )

    assert first_result["success"] is True
    assert first_result["analysis"] == "I can check that camera for you."
    assert second_result["success"] is True
    assert second_result["analysis"] == "It looks quiet now."
    assert len(posted_payloads) == 2

    second_messages = posted_payloads[1]["messages"]
    roles = [message["role"] for message in second_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert second_messages[-1]["content"] == "What changed since last time?"


def test_parallel_tool_calls_answer_every_id_before_images() -> None:
    tool_calls = [
        {
            "id": "call_one",
            "type": "function",
            "function": {"name": "get_camera_image", "arguments": '{"camera": "cam_a"}'},
        },
        {
            "id": "call_two",
            "type": "function",
            "function": {"name": "get_camera_image", "arguments": '{"camera": "cam_b"}'},
        },
    ]
    responses = [
        {
            "choices": [
                {"message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}
            ],
            "usage": {},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Both look clear."}}],
            "usage": {},
        },
    ]
    posted_payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted_payloads) - 1]
        return response

    def fake_execute(name, arguments):
        camera = arguments["camera"]
        return {
            "tool_content": f'{{"success": true, "camera": "{camera}"}}',
            "image_path": f"/tmp/{camera}.jpg",
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": str(path)}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Compare both cameras."}],
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )

    assert result["success"] is True
    sent = posted_payloads[1]["messages"]
    assert [message["role"] for message in sent] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
        "user",
    ]
    assert [message["tool_call_id"] for message in sent if message["role"] == "tool"] == [
        "call_one",
        "call_two",
    ]
    image_parts = [part for part in sent[-1]["content"] if part["type"] == "image_url"]
    assert len(image_parts) == 2
    assert result["image_count"] == 2


def test_batch_camera_tool_injects_all_image_paths() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_batch",
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": '{"cameras": ["cam_a", "cam_b"]}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Both look clear."}}],
            "usage": {},
        },
    ]
    posted_payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted_payloads) - 1]
        return response

    def fake_execute(name, arguments):
        cameras = arguments["cameras"]
        return {
            "tool_content": '{"success": true}',
            "image_path": f"/tmp/{cameras[0]}.jpg",
            "image_paths": [f"/tmp/{camera}.jpg" for camera in cameras],
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": str(path)}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Compare both cameras."}],
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )

    assert result["success"] is True
    sent = posted_payloads[1]["messages"]
    assert [message["role"] for message in sent] == [
        "system",
        "user",
        "assistant",
        "tool",
        "user",
    ]
    image_parts = [part for part in sent[-1]["content"] if part["type"] == "image_url"]
    assert [part["image_url"]["url"] for part in image_parts] == [
        "/tmp/cam_a.jpg",
        "/tmp/cam_b.jpg",
    ]
    assert result["image_count"] == 2
