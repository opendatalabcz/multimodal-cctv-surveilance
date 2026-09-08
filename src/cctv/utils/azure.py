from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

V1_SUFFIX = "/openai/v1"


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Settings for the Azure OpenAI ``/openai/v1`` API.

    This route needs no ``api-version``; the deployment travels in the request
    body as ``model``.
    """

    api_key: str | None
    endpoint: str | None
    model: str | None

    @property
    def api_url(self) -> str | None:
        if not self.endpoint:
            return None
        base = self.endpoint.rstrip("/")
        if not base.endswith(V1_SUFFIX):
            base += V1_SUFFIX
        return f"{base}/chat/completions"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint and self.model)


def load_azure_openai_config() -> AzureOpenAIConfig:
    load_dotenv()
    return AzureOpenAIConfig(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        model=os.getenv("AZURE_OPENAI_MODEL"),
    )
