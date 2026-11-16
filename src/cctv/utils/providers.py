from __future__ import annotations

from dataclasses import replace

from cctv.config.models import AgentConfig, model_by_id
from cctv.utils.azure import AzureOpenAIConfig, resolve_azure_config
from cctv.utils.openrouter import OpenRouterConfig, load_openrouter_config

ChatConfig = AzureOpenAIConfig | OpenRouterConfig


def resolve_model_config(
    agent_config: AgentConfig,
    azure: AzureOpenAIConfig | None = None,
) -> ChatConfig:
    """Return credentials and endpoint for the selected catalog model.

    Each provider has its own client; unknown providers raise before any request.
    """
    selected = model_by_id(agent_config.models, agent_config.model)
    if selected is None:
        raise ValueError(f"Unknown model: {agent_config.model}")
    if selected.provider == "azure":
        return resolve_azure_config(agent_config, azure=azure)
    if selected.provider == "openrouter":
        return replace(load_openrouter_config(), model=selected.id)
    raise ValueError(f"Unsupported model provider: {selected.provider}")
