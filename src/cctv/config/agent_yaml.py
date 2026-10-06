from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml
from dotenv import load_dotenv

from cctv.config.effective import (
    normalize_agent_config,
    validate_location_removals,
    validate_sector_references,
    validate_sector_removals,
)
from cctv.config.models import (
    AgentConfig,
    AgentOverlay,
    CameraConfig,
    LocationConfig,
    ModelOption,
    SectorConfig,
    clamp_control,
    default_model_catalog,
    model_by_id,
)
from cctv.utils.paths import project_root


def agent_config_path() -> Path:
    """Committed camera catalog and default tool flags."""
    return project_root() / "configs" / "agent.yaml"


def agent_overlay_path() -> Path:
    """Gitignored local overrides (toggles, extra/edited cameras)."""
    return project_root() / "configs" / "agent.local.yaml"


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


def load_base_config(path: Path | None = None) -> AgentConfig:
    data = _read_yaml(path or agent_config_path())
    if not data:
        return normalize_agent_config(AgentConfig())
    return normalize_agent_config(AgentConfig.model_validate(data))


def load_overlay(path: Path | None = None) -> AgentOverlay:
    data = _read_yaml(path or agent_overlay_path())
    if not data:
        return AgentOverlay()
    return AgentOverlay.model_validate(data)


T = TypeVar("T")


def _merge_items_by_id(
    base_items: list[T],
    overlay_items: list[T],
    removed_ids: set[str],
    get_id: Callable[[T], str],
) -> list[T]:
    overlay_by_id = {get_id(item).lower(): item for item in overlay_items}
    merged: list[T] = []
    seen: set[str] = set()
    for item in base_items:
        key = get_id(item).lower()
        if key in removed_ids:
            continue
        merged.append(overlay_by_id.get(key, item))
        seen.add(key)
    for item in overlay_items:
        key = get_id(item).lower()
        if key in seen or key in removed_ids:
            continue
        merged.append(item)
        seen.add(key)
    return merged


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
    """Fill every catalog model with its default, then clamp overlay entries."""
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


def merge_agent_config(base: AgentConfig, overlay: AgentOverlay) -> AgentConfig:
    removed_sectors = {item.lower() for item in overlay.remove_sector_ids}
    sectors = _merge_items_by_id(
        base.sectors,
        overlay.sectors,
        removed_sectors,
        lambda sector: sector.id,
    )

    removed_locations = {item.lower() for item in overlay.remove_location_ids}
    locations = _merge_items_by_id(
        base.locations,
        overlay.locations,
        removed_locations,
        lambda location: location.id,
    )

    removed_cameras = {item.lower() for item in overlay.remove_camera_ids}
    cameras = _merge_items_by_id(
        base.cameras,
        overlay.cameras,
        removed_cameras,
        lambda camera: camera.id,
    )

    tools = overlay.tools if overlay.tools is not None else base.tools
    selected = overlay.model if overlay.model is not None else base.model
    reasoning = {**base.reasoning, **overlay.reasoning}
    verbosity = {**base.verbosity, **overlay.verbosity}
    return normalize_agent_config(
        AgentConfig(
            sectors=sectors,
            locations=locations,
            cameras=cameras,
            tools=tools,
            models=list(base.models),
            model=selected,
            reasoning=reasoning,
            verbosity=verbosity,
        )
    )


def overlay_from_diff(base: AgentConfig, current: AgentConfig) -> AgentOverlay:
    base_sectors_by_id = {sector.id.lower(): sector for sector in base.sectors}
    current_sector_ids = {sector.id.lower() for sector in current.sectors}
    remove_sector_ids = [
        sector.id for sector in base.sectors if sector.id.lower() not in current_sector_ids
    ]
    changed_sectors: list[SectorConfig] = []
    for sector in current.sectors:
        original = base_sectors_by_id.get(sector.id.lower())
        if original is None or original.model_dump() != sector.model_dump():
            changed_sectors.append(sector)

    base_locations_by_id = {location.id.lower(): location for location in base.locations}
    current_location_ids = {location.id.lower() for location in current.locations}
    remove_location_ids = [
        location.id
        for location in base.locations
        if location.id.lower() not in current_location_ids
    ]
    changed_locations: list[LocationConfig] = []
    for location in current.locations:
        original = base_locations_by_id.get(location.id.lower())
        if original is None or original.model_dump() != location.model_dump():
            changed_locations.append(location)

    base_by_id = {camera.id.lower(): camera for camera in base.cameras}
    current_ids = {camera.id.lower() for camera in current.cameras}
    remove_camera_ids = [
        camera.id for camera in base.cameras if camera.id.lower() not in current_ids
    ]
    changed: list[CameraConfig] = []
    for camera in current.cameras:
        original = base_by_id.get(camera.id.lower())
        if original is None or original.model_dump() != camera.model_dump():
            changed.append(camera)
    tools = None if current.tools == base.tools else current.tools
    # The model catalog stays in the committed file. Only a non-default selection
    # is a local override. Reasoning and verbosity are stored per model, and only
    # when the value differs from that model's own catalog default.
    model = None if current.model == base.model else current.model
    return AgentOverlay(
        sectors=changed_sectors,
        remove_sector_ids=remove_sector_ids,
        locations=changed_locations,
        remove_location_ids=remove_location_ids,
        cameras=changed,
        remove_camera_ids=remove_camera_ids,
        tools=tools,
        model=model,
        reasoning=_setting_overrides(base.models, current.models, current.reasoning, "reasoning"),
        verbosity=_setting_overrides(base.models, current.models, current.verbosity, "verbosity"),
    )


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
    """Load one YAML file when ``path`` is set; otherwise merge catalog + overlay."""
    if path is not None:
        data = _read_yaml(path)
        if not data:
            return with_effective_models(normalize_agent_config(AgentConfig()))
        return with_effective_models(normalize_agent_config(AgentConfig.model_validate(data)))
    return with_effective_models(merge_agent_config(load_base_config(), load_overlay()))


def save_agent_config(config: AgentConfig, path: Path | None = None) -> None:
    """Write ``path`` as a full config, or write only the gitignored overlay."""
    if path is None:
        base = load_base_config()
        validate_location_removals(base, config)
        validate_sector_removals(base, config)
    normalized = normalize_agent_config(config)
    validate_sector_references(normalized)
    if path is not None:
        _write_yaml(path, normalized.model_dump(mode="json"))
        return

    base = load_base_config()
    overlay = overlay_from_diff(base, normalized)
    payload = overlay.model_dump(mode="json", exclude_none=True)
    if not payload.get("sectors"):
        payload.pop("sectors", None)
    if not payload.get("remove_sector_ids"):
        payload.pop("remove_sector_ids", None)
    if not payload.get("locations"):
        payload.pop("locations", None)
    if not payload.get("remove_location_ids"):
        payload.pop("remove_location_ids", None)
    if not payload.get("cameras"):
        payload.pop("cameras", None)
    if not payload.get("remove_camera_ids"):
        payload.pop("remove_camera_ids", None)
    if not payload.get("reasoning"):
        payload.pop("reasoning", None)
    if not payload.get("verbosity"):
        payload.pop("verbosity", None)
    dest = agent_overlay_path()
    if not payload:
        if dest.is_file():
            dest.unlink()
        return
    _write_yaml(dest, payload)
