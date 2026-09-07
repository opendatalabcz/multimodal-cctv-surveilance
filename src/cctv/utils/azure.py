from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AzureOpenAIConfig:
    api_key: str | None
    endpoint: str | None
    api_version: str | None
    model: str | None

    @property
    def api_url(self) -> str | None:
        if not self.endpoint or not self.model or not self.api_version:
            return None
        endpoint = self.endpoint if self.endpoint.endswith("/") else f"{self.endpoint}/"
        return (
            f"{endpoint}openai/deployments/{self.model}/chat/completions"
            f"?api-version={self.api_version}"
        )

    @property
    def is_configured(self) -> bool:
        return all([self.api_key, self.endpoint, self.api_version, self.model])


def load_azure_openai_config() -> AzureOpenAIConfig:
    load_dotenv()
    return AzureOpenAIConfig(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        model=os.getenv("AZURE_OPENAI_MODEL"),
    )
