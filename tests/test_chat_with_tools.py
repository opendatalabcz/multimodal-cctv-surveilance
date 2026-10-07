import json as json_mod
from unittest.mock import MagicMock, patch

import cctv.tools  # noqa: F401
from cctv.analysis.azure_vision import (
    _chat_completion_payload,
    _responses_payload,
    chat_with_tools,
)
from cctv.utils.azure import AzureOpenAIConfig


def _submit_message(answer: str, camera_ids: list[str] | None = None) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_submit",
                "type": "function",
                "function": {
                    "name": "submit_answer",
                    "arguments": json_mod.dumps(
                        {
                            "answer": answer,
                            "camera_ids": camera_ids or [],
                            "followups": [],
                        }
                    ),
                },
            }
        ],
    }


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
                    "message": _submit_message("I can check that camera for you."),
                }
            ],
            "usage": {"total_tokens": 5},
        },
        {
            "choices": [
                {
                    "message": _submit_message("It looks quiet now."),
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
            "choices": [
                {"message": _submit_message("Both look clear.", ["cam_a", "cam_b"])}
            ],
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
            "choices": [
                {"message": _submit_message("Both look clear.", ["cam_a", "cam_b"])}
            ],
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
    assert "id=cam_a" in sent[-1]["content"][0]["text"]
    assert "id=cam_b" in sent[-1]["content"][0]["text"]
    assert result["image_count"] == 2


def test_on_progress_emits_fetching_then_analyzing() -> None:
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
            "choices": [
                {"message": _submit_message("Both look clear.", ["cam_a", "cam_b"])}
            ],
            "usage": {},
        },
    ]
    posted_payloads: list[dict] = []
    progress: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted_payloads) - 1]
        return response

    def fake_execute(name, arguments):
        cameras = arguments["cameras"]
        return {
            "tool_content": '{"success": true}',
            "image_paths": [f"/tmp/{camera}.jpg" for camera in cameras],
            "image_labels": [
                {"path": f"/tmp/{camera}.jpg", "camera_id": camera}
                for camera in cameras
            ],
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
            parse_json=False,
            on_progress=progress.append,
        )

    assert result["success"] is True
    stages = [event["stage"] for event in progress]
    assert stages == ["thinking", "fetching", "analyzing", "thinking"]
    assert progress[1]["detail"] == "Fetching 2 cameras…"
    assert progress[2]["detail"] == "Analyzing 2 camera frames…"
    assert all(event["type"] == "status" for event in progress)
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
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        **_submit_message("Only A is busy.", ["cam_a"]),
                    }
                }
            ],
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
            "image_paths": [f"/tmp/{camera}.jpg" for camera in cameras],
            "image_labels": [
                {
                    "path": f"/tmp/{camera}.jpg",
                    "camera_id": camera,
                    "camera_name": camera,
                }
                for camera in cameras
            ],
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
    assert result["analysis"] == "Only A is busy."
    assert result["image_count"] == 1
    assert str(result["image_paths"][0]).endswith("cam_a.jpg")
    assert result["messages"][-1]["content"] == "Only A is busy."


def test_empty_cite_block_hides_all_fetched_images() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_one",
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": '{"camera": "cam_a"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        **_submit_message("I will not show a frame."),
                    }
                }
            ],
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
            "tool_content": '{"success": true}',
            "image_path": f"/tmp/{camera}.jpg",
            "image_paths": [f"/tmp/{camera}.jpg"],
            "image_labels": [{"path": f"/tmp/{camera}.jpg", "camera_id": camera}],
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": str(path)}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Do not attach images."}],
            config=_fake_config(),
            parse_json=False,
        )

    assert result["image_paths"] == []
    assert result["image_count"] == 0
    assert not any(
        isinstance(part, dict) and part.get("type") == "image_url"
        for message in result["messages"]
        if isinstance(message.get("content"), list)
        for part in message["content"]
    )


def _image_payloads(messages: list[dict]) -> list[list[str]]:
    urls: list[list[str]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        parts = [
            part["image_url"]["url"]
            for part in content
            if isinstance(part, dict) and part.get("type") == "image_url"
        ]
        if parts:
            urls.append(parts)
    return urls


def test_stored_history_keeps_frame_refs_not_base64() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_one",
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": '{"camera": "cam_a"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        **_submit_message("Busy.", ["cam_a"]),
                    }
                }
            ],
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
            "tool_content": '{"success": true}',
            "image_paths": [f"/tmp/{camera}.jpg"],
            "image_labels": [{"path": f"/tmp/{camera}.jpg", "camera_id": camera}],
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{path}"}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "How is cam_a?"}],
            config=_fake_config(),
            parse_json=False,
        )

    stored = json_mod.dumps(result["messages"])
    assert "data:image" not in stored
    assert "cctv_frames" in stored
    assert len(_image_payloads(posted_payloads[1]["messages"])) == 1


def test_follow_up_without_fetch_reattaches_last_cited_frames() -> None:
    fetch_responses = [
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
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        **_submit_message("Only A is busy.", ["cam_a"]),
                    }
                }
            ],
            "usage": {},
        },
    ]
    posted_payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        response = MagicMock()
        response.json.return_value = (
            fetch_responses[len(posted_payloads) - 1]
            if len(posted_payloads) <= 2
            else {
                "choices": [{"message": _submit_message("The left side is a railing.", ["cam_a"])}],
                "usage": {},
            }
        )
        return response

    def fake_execute(name, arguments):
        cameras = arguments["cameras"]
        return {
            "tool_content": '{"success": true}',
            "image_paths": [f"/tmp/{camera}.jpg" for camera in cameras],
            "image_labels": [
                {"path": f"/tmp/{camera}.jpg", "camera_id": camera, "camera_name": camera}
                for camera in cameras
            ],
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": str(path)}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        first = chat_with_tools(
            [{"role": "user", "content": "Compare both cameras."}],
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )
        history = list(first["messages"])
        history.append({"role": "user", "content": "What is on the left?"})
        second = chat_with_tools(
            history,
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )

    assert second["success"] is True
    follow_up = posted_payloads[2]["messages"]
    image_batches = _image_payloads(follow_up)
    assert len(image_batches) == 1
    assert image_batches[0] == ["/tmp/cam_a.jpg"]
    assert "data:image" not in json_mod.dumps(first["messages"])


def test_second_fetch_stubs_previous_frames() -> None:
    posted_payloads: list[dict] = []
    round_index = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        posted_payloads.append(json)
        round_index["n"] += 1
        n = round_index["n"]
        response = MagicMock()
        if n in {1, 3}:
            camera = "cam_a" if n == 1 else "cam_c"
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call_{camera}",
                                    "type": "function",
                                    "function": {
                                        "name": "get_camera_image",
                                        "arguments": json_mod.dumps({"camera": camera}),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {},
            }
        else:
            camera = "cam_a" if n == 2 else "cam_c"
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            **_submit_message(f"Looking at {camera}.", [camera]),
                        }
                    }
                ],
                "usage": {},
            }
        return response

    def fake_execute(name, arguments):
        camera = arguments["camera"]
        return {
            "tool_content": '{"success": true}',
            "image_paths": [f"/tmp/{camera}.jpg"],
            "image_labels": [{"path": f"/tmp/{camera}.jpg", "camera_id": camera}],
        }

    def fake_image_part(path):
        return {"type": "image_url", "image_url": {"url": str(path)}}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch("cctv.analysis.azure_vision._vision_image_part", side_effect=fake_image_part),
    ):
        first = chat_with_tools(
            [{"role": "user", "content": "Show cam_a"}],
            config=_fake_config(),
            parse_json=False,
        )
        history = list(first["messages"])
        history.append({"role": "user", "content": "Now cam_c"})
        chat_with_tools(
            history,
            config=_fake_config(),
            parse_json=False,
        )

    after_second_fetch = posted_payloads[3]["messages"]
    stubs = [
        message["content"]
        for message in after_second_fetch
        if message.get("role") == "user" and isinstance(message.get("content"), str)
        and str(message["content"]).startswith("Previously viewed")
    ]
    assert any("cam_a" in stub for stub in stubs)
    image_batches = _image_payloads(after_second_fetch)
    assert image_batches == [["/tmp/cam_c.jpg"]]


def test_chat_completions_omit_default_reasoning_and_verbosity() -> None:
    config = AzureOpenAIConfig(api_key="k", endpoint="https://example.test", model="gpt-4o")
    default_payload = _chat_completion_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="default",
    )
    medium_verbosity = _chat_completion_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="default",
        verbosity="medium",
    )
    low_verbosity = _chat_completion_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="default",
        verbosity="low",
    )
    assert "reasoning_effort" not in default_payload
    assert "verbosity" not in default_payload
    assert "verbosity" not in medium_verbosity
    assert low_verbosity["verbosity"] == "low"


def test_luna_responses_payload_normalizes_legacy_default_and_supports_none() -> None:
    config = AzureOpenAIConfig(
        api_key="k",
        endpoint="https://example.test",
        model="gpt-5.6-luna",
    )

    legacy_default = _responses_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="default",
    )
    without_reasoning = _responses_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="none",
        verbosity="high",
    )

    assert legacy_default["reasoning"] == {"effort": "medium"}
    assert without_reasoning["reasoning"] == {"effort": "none"}
    assert without_reasoning["text"] == {"verbosity": "high"}
    assert config.responses_url == "https://example.test/openai/v1/responses"


def test_astra_responses_payload_uses_medium_reasoning() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_cameras",
                "description": "List cameras",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    config = AzureOpenAIConfig(
        api_key="k",
        endpoint="https://example.test/openai/v1",
        model="gpt-6-astra",
    )
    payload = _responses_payload(
        [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
        config,
        tools=tools,
        reasoning="medium",
    )
    assert payload["reasoning"] == {"effort": "medium"}
    assert "text" not in payload
    assert "reasoning_effort" not in payload
    detailed = _responses_payload(
        [{"role": "user", "content": "hi"}],
        config,
        reasoning="max",
        verbosity="high",
    )
    assert detailed["reasoning"] == {"effort": "max"}
    assert detailed["text"] == {"verbosity": "high"}
    assert payload["instructions"] == "Be brief."
    assert payload["tools"][0]["name"] == "list_cameras"
    assert payload["tools"][0]["strict"] is False
    assert config.responses_url == "https://example.test/openai/v1/responses"


def test_luna_responses_tool_round_returns_assistant_text() -> None:
    posted: list[dict] = []
    bodies = [
        {
            "output": [
                {
                    "type": "reasoning",
                    "id": "rs_1",
                    "summary": [],
                    "encrypted_content": "enc",
                    "content": [{"type": "reasoning_text", "text": "secret plan"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "list_cameras",
                    "arguments": "{}",
                },
            ],
            "usage": {},
        },
        {
            "output": [
                {
                    "type": "reasoning",
                    "id": "rs_2",
                    "summary": [{"type": "summary_text", "text": "thinking aloud"}],
                    "encrypted_content": "enc2",
                },
                {"type": "text", "text": "leaked thought"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "also hidden"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_submit",
                    "name": "submit_answer",
                    "arguments": json_mod.dumps(
                        {
                            "answer": "Two cameras.",
                            "camera_ids": [],
                            "followups": [],
                        }
                    ),
                },
            ],
            "usage": {},
        },
    ]

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append({"url": url, "json": json})
        response = MagicMock()
        response.ok = True
        response.json.return_value = bodies.pop(0)
        return response

    config = AzureOpenAIConfig(
        api_key="k",
        endpoint="https://example.test",
        model="gpt-5.6-luna",
    )
    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch(
            "cctv.analysis.azure_vision.execute_tool",
            return_value={"tool_content": '{"cameras":[]}', "image_path": None, "image_paths": []},
        ) as execute,
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "What cameras are there?"}],
            config=config,
            system_prompt="Be brief.",
            tools=[{"type": "function", "function": {"name": "list_cameras", "parameters": {}}}],
            transport="responses",
            reasoning="high",
            verbosity="high",
            parse_json=False,
        )

    execute.assert_called_once_with("list_cameras", {})
    assert all(item["url"].endswith("/responses") for item in posted)
    assert posted[0]["json"]["reasoning"] == {"effort": "high"}
    assert posted[0]["json"]["include"] == ["reasoning.encrypted_content"]
    assert "summary" not in posted[0]["json"]["reasoning"]
    assert posted[0]["json"]["text"] == {"verbosity": "high"}
    assert "reasoning_effort" not in posted[0]["json"]
    replayed = posted[1]["json"]["input"]
    reasoning_index = next(
        index for index, item in enumerate(replayed) if item.get("type") == "reasoning"
    )
    call_index = next(
        index for index, item in enumerate(replayed) if item.get("type") == "function_call"
    )
    assert reasoning_index < call_index
    assert replayed[reasoning_index] == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "enc",
    }
    assert replayed[-1]["type"] == "function_call_output"
    assert result["success"] is True
    assert result["analysis"] == "Two cameras."
    assert "secret plan" not in result["analysis"]
    assert "leaked thought" not in result["analysis"]
    assert "thinking aloud" not in result["analysis"]


def test_submit_answer_is_stored_as_an_assistant_message() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": _submit_message(
                        "The bridge is quiet.",
                        ["charles_bridge"],
                    )
                }
            ],
            "usage": {},
        }
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted) - 1]
        return response

    message = responses[0]["choices"][0]["message"]
    message["tool_calls"][0]["function"]["arguments"] = json_mod.dumps(
        {
            "answer": "The bridge is quiet.",
            "camera_ids": ["charles_bridge"],
            "followups": [
                "Has it cleared yet?",
                "Has it cleared yet?",
                "What about Ječná?",
                "x" * 200,
            ],
        }
    )

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "How is the bridge?"}],
            config=_fake_config(),
            parse_json=False,
        )

    assert result["success"] is True
    assert result["analysis"] == "The bridge is quiet."
    assert result["followups"] == ["Has it cleared yet?", "What about Ječná?"]
    assert result["messages"][-1] == {
        "role": "assistant",
        "content": "The bridge is quiet.",
    }
    assert "tool_calls" not in result["messages"][-1]
    assert posted[0]["tool_choice"] == "auto"


def test_submit_answer_alongside_a_camera_fetch_waits() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_camera",
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": '{"camera": "cam_a"}',
                                },
                            },
                            {
                                "id": "call_submit",
                                "type": "function",
                                "function": {
                                    "name": "submit_answer",
                                    "arguments": json_mod.dumps(
                                        {
                                            "answer": "Too early.",
                                            "camera_ids": ["cam_a"],
                                            "followups": [],
                                        }
                                    ),
                                },
                            },
                        ],
                    }
                }
            ],
            "usage": {},
        },
        {
            "choices": [{"message": _submit_message("Cam A is clear.", ["cam_a"])}],
            "usage": {},
        },
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted) - 1]
        return response

    def fake_execute(name, arguments):
        assert name == "get_camera_image"
        return {
            "tool_content": '{"success": true}',
            "image_paths": ["/tmp/cam_a.jpg"],
            "image_labels": [{"path": "/tmp/cam_a.jpg", "camera_id": "cam_a"}],
        }

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
        patch(
            "cctv.analysis.azure_vision._vision_image_part",
            side_effect=lambda path: {"type": "image_url", "image_url": {"url": str(path)}},
        ),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Look at cam_a."}],
            config=_fake_config(),
            parse_json=False,
        )

    assert result["success"] is True
    assert result["analysis"] == "Cam A is clear."
    assert result["image_count"] == 1
    tool_messages = [
        message for message in posted[1]["messages"] if message["role"] == "tool"
    ]
    assert tool_messages[1]["tool_call_id"] == "call_submit"
    assert "only after the other tools" in tool_messages[1]["content"]
    assert result["messages"][-1]["content"] == "Cam A is clear."


def test_plain_text_is_replaced_by_a_forced_submit_answer() -> None:
    responses = [
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Draft ending in 国产自拍"}}
            ],
            "usage": {},
        },
        {
            "choices": [
                {
                    "message": _submit_message("The street is clear."),
                }
            ],
            "usage": {},
        },
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        response = MagicMock()
        response.json.return_value = responses[len(posted) - 1]
        return response

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "What do you see?"}],
            config=_fake_config(),
            system_prompt="You are a CCTV assistant.",
            parse_json=False,
        )

    assert result["success"] is True
    assert result["analysis"] == "The street is clear."
    assert "国产自拍" not in json_mod.dumps(result["messages"])
    assert posted[1]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_answer"},
    }
    assert result["messages"][-1] == {
        "role": "assistant",
        "content": "The street is clear.",
    }


def test_responses_plain_text_forces_submit_answer_by_name() -> None:
    bodies = [
        {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Draft."}],
                }
            ],
            "usage": {},
        },
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_submit",
                    "name": "submit_answer",
                    "arguments": json_mod.dumps(
                        {"answer": "Final.", "camera_ids": [], "followups": []}
                    ),
                }
            ],
            "usage": {},
        },
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        response = MagicMock()
        response.ok = True
        response.json.return_value = bodies[len(posted) - 1]
        return response

    config = AzureOpenAIConfig(
        api_key="k",
        endpoint="https://example.test",
        model="gpt-5.6-luna",
    )
    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=config,
            transport="responses",
            parse_json=False,
        )

    assert result["success"] is True
    assert result["analysis"] == "Final."
    assert "Draft." not in json_mod.dumps(result["messages"])
    assert posted[1]["tool_choice"] == {"type": "function", "name": "submit_answer"}


def test_a_failed_forced_submit_does_not_show_the_draft() -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Draft 国产自拍"}}],
            "usage": {},
        }
        return response

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_fake_config(),
            parse_json=False,
        )

    assert result["success"] is False
    assert result["error"] == "The model did not submit an answer"
    assert "messages" not in result
