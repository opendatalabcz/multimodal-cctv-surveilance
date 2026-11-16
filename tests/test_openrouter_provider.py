from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cctv.analysis.azure_vision import _chat_completion_payload, _post_json
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
