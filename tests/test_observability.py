"""Langfuse tracing stays local: no live exporter, mocked Azure HTTP."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from cctv.analysis.azure_vision import analyze_images, chat_with_tools
from cctv.api.app import create_app
from cctv.api.chat import run_chat_turn
from cctv.api.store import Conversation
from cctv.api.stream import iter_chat_turn_sse
from cctv.config.models import AgentConfig
from cctv.observability.sanitize import sanitize_for_export
from cctv.observability.tracing import flush_traces
from cctv.observability.usage import normalize_usage
from cctv.utils.azure import AzureOpenAIConfig
from langfuse.media import LangfuseMedia


def _submit(answer: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_submit",
                "type": "function",
                "function": {
                    "name": "submit_answer",
                    "arguments": json.dumps(
                        {"answer": answer, "camera_ids": [], "followups": []}
                    ),
                },
            }
        ],
    }


def _azure() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        api_key="test-key",
        endpoint="https://example.openai.azure.com",
        model="gpt-test",
    )


def _jpeg(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 4), (10, 20, 30)).save(path, format="JPEG")


class RecordingSpan:
    def __init__(self, client: RecordingClient, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.updates: list[dict] = []
        self.children: list[RecordingSpan] = []
        self.parent = client.stack[-1] if client.stack else None
        if self.parent is not None:
            self.parent.children.append(self)
        else:
            client.roots.append(self)
        self._client = client

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)

    def __enter__(self) -> RecordingSpan:
        self._client.stack.append(self)
        return self

    def __exit__(self, *args) -> bool:
        self._client.stack.pop()
        return False


class RecordingClient:
    def __init__(self) -> None:
        self.roots: list[RecordingSpan] = []
        self.stack: list[RecordingSpan] = []
        self.flushed = 0

    def start_as_current_observation(self, **kwargs) -> RecordingSpan:
        return RecordingSpan(self, kwargs)

    def flush(self) -> None:
        self.flushed += 1


class BoomClient:
    def start_as_current_observation(self, **kwargs):
        raise RuntimeError("langfuse down")

    def flush(self) -> None:
        raise RuntimeError("flush down")


class AngrySpan:
    def update(self, **kwargs) -> None:
        raise RuntimeError("update down")

    def __enter__(self) -> AngrySpan:
        return self

    def __exit__(self, *args) -> bool:
        return False


class AngryClient:
    def start_as_current_observation(self, **kwargs) -> AngrySpan:
        return AngrySpan()


def _enable(monkeypatch, client) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    monkeypatch.setattr("cctv.observability.tracing._get_client", lambda: client)


def _ok_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.ok = True
    response.json.return_value = body
    return response


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _walk_media(value):
    if isinstance(value, LangfuseMedia):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_media(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_media(item)


def test_sanitize_strips_secrets_reasoning_and_images() -> None:
    payload = {
        "api-key": "secret",
        "nested": {"encrypted_content": "blob", "text": "keep me"},
        "include": ["reasoning.encrypted_content", "keep"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,aGVsbG8=",
                            "detail": "high",
                        },
                    },
                    {"type": "input_image", "image_url": "data:image/png;base64,aGVsbG8="},
                ],
            }
        ],
    }
    original = json.dumps(payload)
    cleaned = sanitize_for_export(payload)
    assert json.dumps(payload) == original
    assert "api-key" not in cleaned
    assert "encrypted_content" not in json.dumps(cleaned)
    assert "reasoning.encrypted_content" not in json.dumps(cleaned)
    assert cleaned["nested"]["text"] == "keep me"
    assert cleaned["include"] == ["keep"]
    image = cleaned["messages"][0]["content"][1]
    assert image["omitted"] is True
    assert image["media_type"] == "image/jpeg"
    assert image["detail"] == "high"
    assert image["byte_length"] == len(b"hello")
    assert "aGVsbG8=" not in json.dumps(cleaned)
    kept = sanitize_for_export(payload, include_images=True)
    assert kept["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg")


def test_normalize_usage_for_both_azure_transports() -> None:
    assert normalize_usage(
        {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
    ) == {"input": 3, "output": 4, "total": 7}
    assert normalize_usage(
        {
            "input_tokens": 8,
            "output_tokens": 2,
            "input_tokens_details": {"cached_tokens": 1},
        }
    ) == {"input": 8, "output": 2, "total": 10}
    assert normalize_usage({}) is None
    assert normalize_usage(None) is None
    assert normalize_usage({"prompt_tokens": True}) is None


def test_disabled_tracing_does_not_construct_a_client(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    constructed: list[object] = []

    class Exploding:
        def __init__(self, *args, **kwargs) -> None:
            constructed.append(kwargs)

    monkeypatch.setattr("langfuse.Langfuse", Exploding)

    def fake_post(url, headers=None, json=None, timeout=None):
        return _ok_response(
            {
                "choices": [{"message": _submit("Quiet.")}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_azure(),
            parse_json=False,
        )

    assert result["success"] is True
    assert constructed == []


def test_missing_keys_stay_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    from cctv.observability.tracing import tracing_enabled

    assert tracing_enabled() is False


def test_turn_nests_generation_and_tool_and_correlates_the_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LANGFUSE_CAPTURE_IMAGES", "false")
    client = RecordingClient()
    _enable(monkeypatch, client)
    sessions: list[dict] = []

    def fake_propagate(**kwargs):
        sessions.append(kwargs)

        class _Context:
            def __enter__(self):
                return None

            def __exit__(self, *args):
                return False

        return _Context()

    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate)
    jpeg = tmp_path / "frame.jpg"
    _jpeg(jpeg)
    bodies = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_camera_image",
                                    "arguments": '{"camera": "bridge"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        },
        {
            "choices": [{"message": _submit("The bridge is quiet.")}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 6, "total_tokens": 26},
        },
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        return _ok_response(bodies[len(posted) - 1])

    def fake_execute(name, arguments):
        return {
            "tool_content": json.dumps({"success": True, "camera_id": "bridge"}),
            "image_path": str(jpeg),
            "image_paths": [str(jpeg)],
            "image_labels": [
                {"path": str(jpeg), "camera_id": "bridge", "camera_name": "Bridge"}
            ],
        }

    conversation = Conversation(id="conv-trace")
    with (
        patch("cctv.api.chat.load_agent_config", return_value=AgentConfig()),
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
    ):
        updated, result = run_chat_turn(conversation, "How busy is the bridge?", config=_azure())

    assert result["success"] is True
    assert updated.messages[-1].content == "The bridge is quiet."
    assert len(client.roots) == 1
    turn = client.roots[0]
    assert turn.kwargs["as_type"] == "agent"
    assert turn.kwargs["name"] == "answer-chat"
    assert turn.kwargs["trace_context"]["trace_id"]
    assert [child.kwargs["as_type"] for child in turn.children] == [
        "generation",
        "tool",
        "generation",
    ]
    assert turn.children[1].kwargs["name"] == "get_camera_image"
    tool_output = turn.children[1].updates[-1]["output"]
    assert tool_output["images"][0]["camera_id"] == "bridge"
    assert tool_output["images"][0]["width"] == 8
    assert tool_output["images"][0]["height"] == 4
    assert "media" not in tool_output["images"][0]
    assert turn.children[0].updates[-1]["usage_details"] == {"input": 11, "output": 5, "total": 16}
    assert turn.children[-1].updates[-1]["usage_details"]["total"] == 26
    assert turn.updates[-1]["output"] == "The bridge is quiet."
    assert sessions == [
        {"session_id": "conv-trace", "trace_name": "answer-chat", "tags": ["chat"]}
    ]
    for generation in (turn.children[0], turn.children[2]):
        exported = json.dumps(generation.kwargs["input"])
        assert "base64" not in exported
        assert list(_walk_media(generation.kwargs["input"])) == []
    assert "data:image/jpeg;base64," in json.dumps(posted[1])
    entry = json.loads((tmp_path / "logs" / "chat_turns.jsonl").read_text(encoding="utf-8"))
    assert entry["turn_id"] == turn.kwargs["trace_context"]["trace_id"]
    assert entry["conversation_id"] == "conv-trace"


def test_capture_images_attaches_each_frame_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_IMAGES", "true")
    client = RecordingClient()
    _enable(monkeypatch, client)
    jpeg = tmp_path / "frame.jpg"
    _jpeg(jpeg)

    def fake_post(url, headers=None, json=None, timeout=None):
        if not hasattr(fake_post, "n"):
            fake_post.n = 0
        fake_post.n += 1
        if fake_post.n == 1:
            body = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_camera_image",
                                        "arguments": '{"camera": "bridge"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
        else:
            body = {
                "choices": [{"message": _submit("Seen.")}],
                "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            }
        return _ok_response(body)

    def fake_execute(name, arguments):
        return {
            "tool_content": '{"success": true}',
            "image_paths": [str(jpeg)],
            "image_labels": [{"path": str(jpeg), "camera_id": "bridge", "camera_name": "Bridge"}],
        }

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Look"}],
            config=_azure(),
            parse_json=False,
        )

    assert result["success"] is True
    generations = [span for span in client.roots if span.kwargs["as_type"] == "generation"]
    tools = [span for span in client.roots if span.kwargs["name"] == "get_camera_image"]
    assert len(tools) == 1
    media = list(_walk_media(tools[0].updates[-1]["output"]))
    assert len(media) == 1
    assert media[0]._content_type == "image/jpeg"
    for generation in generations:
        assert list(_walk_media(generation.kwargs["input"])) == []
        assert all("base64," not in text for text in _walk_strings(generation.kwargs["input"]))


def test_analyze_images_can_include_the_frame(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_IMAGES", "true")
    client = RecordingClient()
    _enable(monkeypatch, client)
    jpeg = tmp_path / "meta.jpg"
    _jpeg(jpeg)

    def fake_post(url, headers=None, json=None, timeout=None):
        return _ok_response(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": '{"description":"A road."}'}}
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            }
        )

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = analyze_images([jpeg], "Describe the view.", config=_azure())

    assert result["success"] is True
    generation = client.roots[0]
    assert generation.kwargs["name"] == "describe-camera"
    assert list(_walk_media(generation.kwargs["input"]))
    assert generation.updates[-1]["usage_details"] == {"input": 4, "output": 2, "total": 6}


def test_responses_usage_and_encrypted_content_are_normalized(monkeypatch) -> None:
    client = RecordingClient()
    _enable(monkeypatch, client)

    arguments = json.dumps({"answer": "Clear.", "camera_ids": [], "followups": []})

    def fake_post(url, headers=None, json=None, timeout=None):
        return _ok_response(
            {
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "encrypted_content": "do-not-export",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_submit",
                        "name": "submit_answer",
                        "arguments": arguments,
                    },
                ],
                "usage": {"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
            }
        )

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_azure(),
            transport="responses",
            parse_json=False,
        )

    assert result["success"] is True
    generation = client.roots[0]
    assert generation.kwargs["name"] == "generate-reply"
    assert generation.kwargs["model_parameters"]["transport"] == "responses"
    assert "reasoning.encrypted_content" not in json.dumps(generation.kwargs["input"])
    exported_output = json.dumps(generation.updates[-1]["output"])
    assert "do-not-export" not in exported_output
    assert generation.updates[-1]["usage_details"] == {"input": 9, "output": 3, "total": 12}
    assert generation.updates[-1]["metadata"]["http_status"] == 200


def test_azure_error_is_traced_and_does_not_raise(monkeypatch) -> None:
    client = RecordingClient()
    _enable(monkeypatch, client)

    def fake_post(url, headers=None, json=None, timeout=None):
        response = MagicMock()
        response.ok = False
        response.status_code = 429
        response.reason = "Too Many Requests"
        response.text = "slow down"
        response.url = "https://example.openai.azure.com/openai/v1/chat/completions"
        return response

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_azure(),
            parse_json=False,
        )

    assert result["success"] is False
    assert "429" in result["error"]
    generation = client.roots[0]
    assert any(update.get("level") == "ERROR" for update in generation.updates)
    assert any(
        (update.get("metadata") or {}).get("http_status") == 429 for update in generation.updates
    )


def test_tracing_failures_do_not_fail_the_chat(monkeypatch) -> None:
    _enable(monkeypatch, BoomClient())

    def fake_post(url, headers=None, json=None, timeout=None):
        return _ok_response(
            {"choices": [{"message": _submit("Still here.")}], "usage": {}}
        )

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_azure(),
            parse_json=False,
        )

    assert result["success"] is True
    assert result["analysis"] == "Still here."

    _enable(monkeypatch, AngryClient())
    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        again = chat_with_tools(
            [{"role": "user", "content": "Hello"}],
            config=_azure(),
            parse_json=False,
        )
    assert again["success"] is True
    flush_traces()


def test_stream_flushes_after_the_answer_is_queued(monkeypatch) -> None:
    flushed = []

    def fake_flush() -> None:
        flushed.append("flush")

    def fake_turn(conversation, content, on_progress=None):
        return conversation, {
            "success": True,
            "analysis": "Done",
            "messages": [{"role": "assistant", "content": "Done"}],
        }

    monkeypatch.setattr("cctv.api.stream.flush_traces", fake_flush)
    monkeypatch.setattr("cctv.api.stream.run_chat_turn", fake_turn)
    events = list(iter_chat_turn_sse(Conversation(id="conv"), "hello"))
    deadline = time.monotonic() + 2
    while not flushed and time.monotonic() < deadline:
        time.sleep(0.01)

    assert any("done" in event for event in events)
    assert flushed == ["flush"]


def test_shutdown_flushes(monkeypatch) -> None:
    import importlib

    app_module = importlib.import_module("cctv.api.app")
    calls = []
    monkeypatch.setattr(app_module, "flush_traces", lambda: calls.append("flush"))
    with TestClient(create_app()):
        pass
    assert calls == ["flush"]


def test_tool_failure_is_an_error_span(monkeypatch) -> None:
    client = RecordingClient()
    _enable(monkeypatch, client)

    def fake_post(url, headers=None, json=None, timeout=None):
        if not hasattr(fake_post, "n"):
            fake_post.n = 0
        fake_post.n += 1
        if fake_post.n == 1:
            body = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"place": "Prague"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {},
            }
        else:
            body = {
                "choices": [{"message": _submit("Weather is down.")}],
                "usage": {},
            }
        return _ok_response(body)

    def fake_execute(name, arguments):
        return {"tool_content": json.dumps({"success": False, "error": "timeout"}), "image_path": None}

    with (
        patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post),
        patch("cctv.analysis.azure_vision.execute_tool", side_effect=fake_execute),
    ):
        result = chat_with_tools(
            [{"role": "user", "content": "Weather?"}],
            config=_azure(),
            parse_json=False,
        )

    assert result["success"] is True
    tool = next(span for span in client.roots if span.kwargs["name"] == "get_weather")
    assert tool.updates[-1]["level"] == "ERROR"
    assert tool.updates[-1]["status_message"] == "timeout"
    assert tool.updates[-1]["metadata"]["success"] is False
