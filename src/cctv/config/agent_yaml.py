from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cctv.config.effective import normalize_agent_config, validate_sector_references, validate_sector_removals
from cctv.config.models import AgentConfig, AgentOverlay, CameraConfig, SectorConfig
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


def merge_agent_config(base: AgentConfig, overlay: AgentOverlay) -> AgentConfig:
    removed_sectors = {item.lower() for item in overlay.remove_sector_ids}
    overlay_sectors = {sector.id.lower(): sector for sector in overlay.sectors}
    sectors: list[SectorConfig] = []
    seen_sectors: set[str] = set()
    for sector in base.sectors:
        key = sector.id.lower()
        if key in removed_sectors:
            continue
        sectors.append(overlay_sectors.get(key, sector))
        seen_sectors.add(key)
    for sector in overlay.sectors:
        key = sector.id.lower()
        if key in seen_sectors or key in removed_sectors:
            continue
        sectors.append(sector)
        seen_sectors.add(key)

    removed = {item.lower() for item in overlay.remove_camera_ids}
    overlays = {camera.id.lower(): camera for camera in overlay.cameras}
    cameras: list[CameraConfig] = []
    seen: set[str] = set()
    for camera in base.cameras:
        key = camera.id.lower()
        if key in removed:
            continue
        cameras.append(overlays.get(key, camera))
        seen.add(key)
    for camera in overlay.cameras:
        key = camera.id.lower()
        if key in seen or key in removed:
            continue
        cameras.append(camera)
        seen.add(key)

    tools = overlay.tools if overlay.tools is not None else base.tools
    return normalize_agent_config(AgentConfig(sectors=sectors, cameras=cameras, tools=tools))


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
    return AgentOverlay(
        sectors=changed_sectors,
        remove_sector_ids=remove_sector_ids,
        cameras=changed,
        remove_camera_ids=remove_camera_ids,
        tools=tools,
    )


def load_agent_config(path: Path | None = None) -> AgentConfig:
    """Load one YAML file when ``path`` is set; otherwise merge catalog + overlay."""
    if path is not None:
        data = _read_yaml(path)
        if not data:
            return normalize_agent_config(AgentConfig())
        return normalize_agent_config(AgentConfig.model_validate(data))
    return merge_agent_config(load_base_config(), load_overlay())


def save_agent_config(config: AgentConfig, path: Path | None = None) -> None:
    """Write ``path`` as a full config, or write only the gitignored overlay."""
    if path is None:
        validate_sector_removals(load_base_config(), config)
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
    if not payload.get("cameras"):
        payload.pop("cameras", None)
    if not payload.get("remove_camera_ids"):
        payload.pop("remove_camera_ids", None)
    dest = agent_overlay_path()
    if not payload:
        if dest.is_file():
            dest.unlink()
        return
    _write_yaml(dest, payload)
