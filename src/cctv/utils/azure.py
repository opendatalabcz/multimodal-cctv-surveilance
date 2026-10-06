from __future__ import annotations

import os
from dataclasses import dataclass, replace

from dotenv import load_dotenv

from cctv.config.models import AgentConfig

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
    def responses_url(self) -> str | None:
        if not self.endpoint:
            return None
        base = self.endpoint.rstrip("/")
        if not base.endswith(V1_SUFFIX):
            base += V1_SUFFIX
        return f"{base}/responses"

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


def resolve_azure_config(
    agent_config: AgentConfig,
    azure: AzureOpenAIConfig | None = None,
) -> AzureOpenAIConfig:
    """Copy env credentials and set ``model`` to the selected deployment.

    Unknown providers are rejected here so Azure is not called for them.
    """
    base = azure if azure is not None else load_azure_openai_config()
    selected = next(
        (item for item in agent_config.models if item.id == agent_config.model),
        None,
    )
    if selected is None:
        raise ValueError(f"Unknown model: {agent_config.model}")
    if selected.provider != "azure":
        raise ValueError(f"Unsupported model provider: {selected.provider}")
    return replace(base, model=selected.id)
