from __future__ import annotations

from pathlib import Path

import yaml

from cctv.config.models import AgentConfig
from cctv.utils.paths import project_root


def agent_config_path() -> Path:
    return project_root() / "configs" / "agent.yaml"


def load_agent_config(path: Path | None = None) -> AgentConfig:
    config_path = path or agent_config_path()
    if not config_path.is_file():
        return AgentConfig()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AgentConfig.model_validate(data)


def save_agent_config(config: AgentConfig, path: Path | None = None) -> None:
    config_path = path or agent_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    text = yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True)
    config_path.write_text(text, encoding="utf-8")
