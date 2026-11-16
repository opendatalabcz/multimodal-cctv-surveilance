from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True)
class OpenRouterConfig:
    """Settings for OpenRouter's OpenAI-compatible chat completions endpoint.

    Only chat completions is wired here. Its free endpoints accept ``max_tokens``
    and not ``max_completion_tokens``, so the payload builder checks this type.
    """

    api_key: str | None
    model: str | None

    @property
    def api_url(self) -> str:
        return OPENROUTER_CHAT_URL

    @property
    def responses_url(self) -> None:
        return None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)


def load_openrouter_config() -> OpenRouterConfig:
    load_dotenv()
    # OPENROUTER_API_KEY is the name OpenRouter's docs use. OPEN_ROUTER_API_KEY is
    # accepted so an existing .env keeps working.
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    return OpenRouterConfig(api_key=api_key or None, model=None)
