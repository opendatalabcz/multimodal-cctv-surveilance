from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import cctv.tools  # noqa: F401  — register default tools
from cctv.analysis.azure_vision import _chat_completion_payload, _post_json, chat_with_tools
from cctv.config.models import AgentConfig, ModelOption
from cctv.utils.openrouter import OPENROUTER_CHAT_URL, OpenRouterConfig
from cctv.utils.providers import resolve_model_config

GEMMA = "google/gemma-4-31b-it:free"


def _openrouter_agent() -> AgentConfig:
    return AgentConfig(
        models=[ModelOption(id=GEMMA, label="Gemma", provider="openrouter")],
        model=GEMMA,
    )


def test_openrouter_model_resolves_with_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    resolved = resolve_model_config(_openrouter_agent())

    assert isinstance(resolved, OpenRouterConfig)
    assert resolved.api_key == "or-key"
    assert resolved.model == GEMMA
    assert resolved.api_url == OPENROUTER_CHAT_URL
    assert resolved.responses_url is None
    assert resolved.is_configured


def test_openrouter_without_key_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OpenRouterConfig(api_key=None, model=GEMMA)

    assert not config.is_configured


def test_openrouter_payload_uses_max_tokens_not_max_completion_tokens() -> None:
    config = OpenRouterConfig(api_key="or-key", model=GEMMA)

    payload = _chat_completion_payload(
        [{"role": "user", "content": "hello"}],
        config,
        max_tokens=123,
    )

    assert payload["model"] == GEMMA
    assert payload["max_tokens"] == 123
    assert "max_completion_tokens" not in payload


def test_openrouter_payload_sends_empty_content_on_tool_call_turns() -> None:
    # Qwen via Alibaba returns content: null on tool-call turns and rejects replaying it.
    config = OpenRouterConfig(api_key="or-key", model="qwen/qwen3.8-flash")
    history = [
        {"role": "user", "content": "Walk on the bridge?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_list",
                    "type": "function",
                    "function": {"name": "list_cameras", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_list", "content": "[]"},
    ]

    payload = _chat_completion_payload(history, config)

    assistant = payload["messages"][1]
    assert assistant["content"] == ""
    assert assistant["tool_calls"][0]["id"] == "call_list"
    assert all(message.get("content") is not None for message in payload["messages"])
    # The stored transcript itself is not mutated.
    assert history[1]["content"] is None


def test_openrouter_chat_with_tools_replays_null_content_as_empty_string() -> None:
    config = OpenRouterConfig(api_key="or-key", model="qwen/qwen3.8-flash")
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_list",
                                "type": "function",
                                "function": {"name": "list_cameras", "arguments": "{}"},
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
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_submit",
                                "type": "function",
                                "function": {
                                    "name": "submit_answer",
                                    "arguments": json.dumps(
                                        {"answer": "Quiet.", "images": [], "followups": []}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {},
        },
    ]
    posted: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.append(json)
        response = MagicMock(ok=True)
        response.json.return_value = responses[len(posted) - 1]
        return response

    with patch("cctv.analysis.azure_vision.requests.post", side_effect=fake_post):
        result = chat_with_tools(
            [{"role": "user", "content": "Walk on the bridge?"}],
            config=config,
        )

    assert result["success"] is True
    assert result["analysis"] == "Quiet."
    assert len(posted) == 2
    replayed = [message for message in posted[1]["messages"] if message["role"] == "assistant"]
    assert replayed[0]["content"] == ""


def test_openrouter_request_sends_bearer_token_to_chat_url() -> None:
    config = OpenRouterConfig(api_key="or-key", model=GEMMA)
    response = MagicMock(ok=True)
    response.json.return_value = {"choices": []}

    with patch("cctv.analysis.azure_vision.requests.post", return_value=response) as post:
        _post_json(OPENROUTER_CHAT_URL, {"model": GEMMA}, config)

    assert post.call_args.args[0] == OPENROUTER_CHAT_URL
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer or-key"
    assert "api-key" not in headers
