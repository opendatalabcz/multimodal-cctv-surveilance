from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from cctv.config.effective import (
    UNASSIGNED_SECTOR_ID,
    normalize_agent_config,
    validate_location_removals,
    validate_sector_references,
    validate_sector_removals,
)
from cctv.config.models import (
    AgentConfig,
    ModelOption,
    clamp_control,
    default_model_catalog,
    model_by_id,
)
from cctv.utils.paths import project_root


_CAMERA_KEYS = ("sectors", "locations", "cameras")
_AGENT_KEYS = ("tools", "models", "model", "reasoning", "verbosity")


def agent_config_path() -> Path:
    """Committed model catalog, selected model, and default tool flags."""
    return project_root() / "configs" / "agent.yaml"


def camera_config_path() -> Path:
    """Committed sector, location, and camera catalog."""
    return agent_config_path().with_name("cameras.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")


def _pick(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: data[key] for key in keys if key in data}


def _combined_base(camera_data: dict[str, Any], agent_data: dict[str, Any]) -> dict[str, Any]:
    """Camera catalog from ``cameras.yaml`` when that file exists.

    A single ``agent.yaml`` that still contains cameras is the legacy layout,
    used when the camera file is absent.
    """
    if camera_data:
        data = _pick(camera_data, _CAMERA_KEYS)
        data.update(_pick(agent_data, _AGENT_KEYS))
        return data
    return agent_data


def load_base_config(path: Path | None = None) -> AgentConfig:
    if path is not None:
        data = _read_yaml(path)
    else:
        data = _combined_base(_read_yaml(camera_config_path()), _read_yaml(agent_config_path()))
    if not data:
        return normalize_agent_config(AgentConfig())
    return normalize_agent_config(AgentConfig.model_validate(data))


def _control(option: ModelOption, kind: str):
    return option.reasoning if kind == "reasoning" else option.verbosity


def _option_for(
    base_models: list[ModelOption],
    current_models: list[ModelOption],
    model_id: str,
) -> ModelOption | None:
    return model_by_id(base_models, model_id) or model_by_id(current_models, model_id)


def _setting_overrides(
    base_models: list[ModelOption],
    current_models: list[ModelOption],
    values: dict[str, str],
    kind: str,
) -> dict[str, str]:
    """Keep values that differ from each model's catalog default."""
    kept: dict[str, str] = {}
    for model_id, value in values.items():
        option = _option_for(base_models, current_models, model_id)
        if option is None or value == _control(option, kind).default:
            continue
        kept[model_id] = value
    return kept


def _filled_settings(
    models: list[ModelOption],
    values: dict[str, str],
    kind: str,
) -> dict[str, str]:
    """Fill every catalog model with its default, then clamp stored entries."""
    filled: dict[str, str] = {}
    for option in models:
        control = _control(option, kind)
        filled[option.id] = clamp_control(control, values.get(option.id), control.default)
    return filled


def _validate_setting_map(
    models: list[ModelOption],
    values: dict[str, str],
    kind: str,
    label: str,
) -> None:
    for model_id, value in values.items():
        option = model_by_id(models, model_id)
        if option is None:
            raise ValueError(f"Unknown model: {model_id}")
        control = _control(option, kind)
        allowed = control.choices if control.choices else [control.default]
        if value not in allowed:
            raise ValueError(f"Unsupported {label}: {value}")


def _synthetic_location(location_id: str) -> bool:
    return location_id == "unassigned" or location_id.endswith("_unassigned")


def _camera_document(config: AgentConfig) -> dict[str, Any]:
    """Sectors, locations, and cameras, without an unused injected Unassigned sector."""
    data = config.model_dump(mode="json", exclude_none=True)
    used_locations = {camera.get("location_id") for camera in data.get("cameras", [])}
    locations = [
        location
        for location in data.get("locations", [])
        if not _synthetic_location(str(location.get("id", "")))
        or location.get("id") in used_locations
    ]
    used_sectors = {camera.get("sector_id") for camera in data.get("cameras", [])}
    used_sectors.update(location.get("sector_id") for location in locations)
    sectors = [
        sector
        for sector in data.get("sectors", [])
        if sector.get("id") != UNASSIGNED_SECTOR_ID or sector.get("id") in used_sectors
    ]
    return {
        "sectors": sectors,
        "locations": locations,
        "cameras": data.get("cameras", []),
    }


def _agent_document(config: AgentConfig) -> dict[str, Any]:
    """Tools, model catalog, selection, and non-default reasoning or verbosity."""
    data = config.model_dump(mode="json", exclude_none=True)
    payload: dict[str, Any] = {
        "tools": data.get("tools", {}),
        "models": data.get("models", []),
        "model": data.get("model"),
    }
    reasoning = _setting_overrides(config.models, config.models, config.reasoning, "reasoning")
    verbosity = _setting_overrides(config.models, config.models, config.verbosity, "verbosity")
    if reasoning:
        payload["reasoning"] = reasoning
    if verbosity:
        payload["verbosity"] = verbosity
    return payload


def with_effective_models(config: AgentConfig) -> AgentConfig:
    """Catalog from config, plus the env deployment when it is not listed.

    The selected id is the config value when it is in that list, otherwise the
    env deployment, otherwise the first catalog entry.
    """
    load_dotenv()
    models = list(config.models) or default_model_catalog()
    env_model = (os.getenv("AZURE_OPENAI_MODEL") or "").strip()
    if env_model and all(item.id != env_model for item in models):
        models.append(ModelOption(id=env_model, label=env_model, provider="azure"))
    ids = {item.id for item in models}
    selected = config.model
    if selected not in ids:
        if env_model and env_model in ids:
            selected = env_model
        else:
            selected = models[0].id
    reasoning = _filled_settings(models, config.reasoning, "reasoning")
    verbosity = _filled_settings(models, config.verbosity, "verbosity")
    return config.model_copy(
        update={
            "models": models,
            "model": selected,
            "reasoning": reasoning,
            "verbosity": verbosity,
        }
    )


def config_with_server_catalog(incoming: AgentConfig) -> AgentConfig:
    """Drop any client-supplied model list and keep the committed catalog.

    ``incoming.model`` must be in the effective list (catalog plus env deployment).
    """
    base = load_base_config()
    effective = with_effective_models(base)
    allowed = {item.id for item in effective.models}
    if incoming.model not in allowed:
        raise ValueError(f"Unknown model: {incoming.model}")
    _validate_setting_map(effective.models, incoming.reasoning, "reasoning", "reasoning effort")
    _validate_setting_map(effective.models, incoming.verbosity, "verbosity", "verbosity")
    return incoming.model_copy(update={"models": list(base.models)})


def load_agent_config(path: Path | None = None) -> AgentConfig:
    """Load one YAML file when ``path`` is set; otherwise the two config files."""
    if path is not None:
        data = _read_yaml(path)
        if not data:
            return with_effective_models(normalize_agent_config(AgentConfig()))
        return with_effective_models(normalize_agent_config(AgentConfig.model_validate(data)))
    return with_effective_models(load_base_config())


def save_agent_config(config: AgentConfig, path: Path | None = None) -> None:
    """Write ``path`` as one file, or split the catalog across the two config files."""
    if path is None:
        base = load_base_config()
        validate_location_removals(base, config)
        validate_sector_removals(base, config)
    normalized = normalize_agent_config(config)
    validate_sector_references(normalized)
    if path is not None:
        _write_yaml(path, normalized.model_dump(mode="json"))
        return
    _write_yaml(camera_config_path(), _camera_document(normalized))
    _write_yaml(agent_config_path(), _agent_document(normalized))
