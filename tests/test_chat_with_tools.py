from unittest.mock import MagicMock, patch

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
