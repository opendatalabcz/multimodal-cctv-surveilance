import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cctv.config.agent_yaml import (
    agent_config_path,
    load_agent_config,
    load_overlay,
    overlay_from_diff,
    save_agent_config,
)
from cctv.config.effective import (
    UNASSIGNED_LOCATION_ID,
    UNASSIGNED_SECTOR_ID,
    effective_cameras,
    is_camera_effective,
    normalize_agent_config,
    unassigned_location_id,
)
from cctv.config.models import AgentConfig, CameraConfig, LocationConfig, SectorConfig, ToolsConfig
from cctv.config.prompt import build_system_prompt
from cctv.tools.registry import execute_tool


def _sector(sector_id: str, name: str, *, enabled: bool = True) -> SectorConfig:
    return SectorConfig(id=sector_id, name=name, enabled=enabled)


def _location(
    location_id: str,
    name: str,
    *,
    sector_id: str = "prague",
    enabled: bool = True,
    lat: float | None = None,
    lon: float | None = None,
) -> LocationConfig:
    return LocationConfig(
        id=location_id,
        name=name,
        sector_id=sector_id,
        enabled=enabled,
        lat=lat,
        lon=lon,
    )


def _cam(
    camera_id: str,
    name: str,
    *,
    sector_id: str | None = "prague",
    location_id: str | None = "bridge",
    enabled: bool = True,
    source: str = "101048",
) -> CameraConfig:
    return CameraConfig(
        id=camera_id,
        name=name,
        source=source,
        sector_id=sector_id,
        location_id=location_id,
        enabled=enabled,
    )


def _patch_paths(tmp_path: Path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)


def test_legacy_camera_without_location_gets_unassigned_under_sector() -> None:
    config = normalize_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague")],
            cameras=[CameraConfig(id="bridge", name="Bridge", source="101200", sector_id="prague")],
        )
    )
    assert config.cameras[0].location_id == unassigned_location_id("prague")
    assert any(
        location.id == unassigned_location_id("prague") for location in config.locations
    )


def test_three_level_and_enablement() -> None:
    config = normalize_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague", enabled=True)],
            locations=[
                _location("bridge", "Bridge", enabled=False),
                _location("square", "Square", enabled=True),
            ],
            cameras=[
                _cam("a", "A", location_id="bridge", enabled=True),
                _cam("b", "B", location_id="square", enabled=False),
                _cam("c", "C", location_id="square", enabled=True),
            ],
        )
    )

    assert is_camera_effective(config, config.cameras[0]) is False
    assert is_camera_effective(config, config.cameras[1]) is False
    assert is_camera_effective(config, config.cameras[2]) is True
    assert [camera.id for camera in effective_cameras(config)] == ["c"]


def test_sector_off_hides_cameras_even_when_location_and_camera_on() -> None:
    config = normalize_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague", enabled=False)],
            locations=[_location("bridge", "Bridge", enabled=True)],
            cameras=[_cam("a", "A", location_id="bridge", enabled=True)],
        )
    )
    assert is_camera_effective(config, config.cameras[0]) is False


def test_overlay_location_round_trip(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    base = AgentConfig(
        sectors=[_sector("prague", "Prague")],
        locations=[_location("bridge", "Bridge")],
        cameras=[_cam("cam", "Cam", location_id="bridge")],
        tools=ToolsConfig(),
    )
    save_agent_config(base, tmp_path / "agent.yaml")

    updated = AgentConfig(
        sectors=[_sector("prague", "Prague", enabled=False)],
        locations=[
            _location("bridge", "Bridge", enabled=False),
            _location("square", "Square", sector_id="prague"),
        ],
        cameras=[
            _cam("cam", "Cam", location_id="bridge", enabled=False),
            _cam("gate", "Gate", location_id="square"),
        ],
        tools=ToolsConfig(internet=True),
    )
    save_agent_config(updated)

    overlay = load_overlay()
    assert overlay.tools is not None
    assert overlay.tools.internet is True
    assert {location.id for location in overlay.locations} == {"bridge", "square"}
    assert {camera.id for camera in overlay.cameras} == {"cam", "gate"}

    merged = load_agent_config()
    assert merged.tools.internet is True
    assert merged.sectors[0].enabled is False
    assert merged.locations[0].enabled is False
    assert merged.cameras[1].location_id == "square"


def test_block_location_deletion_with_assigned_cameras(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    base = AgentConfig(
        sectors=[_sector("prague", "Prague")],
        locations=[_location("bridge", "Bridge"), _location("square", "Square")],
        cameras=[
            _cam("cam", "Cam", location_id="bridge"),
            _cam("gate", "Gate", location_id="square"),
        ],
    )
    save_agent_config(base, tmp_path / "agent.yaml")

    with pytest.raises(ValueError, match="Cannot remove location"):
        save_agent_config(
            AgentConfig(
                sectors=[_sector("prague", "Prague")],
                locations=[_location("square", "Square")],
                cameras=[
                    _cam("cam", "Cam", location_id="bridge"),
                    _cam("gate", "Gate", location_id="square"),
                ],
            )
        )


def test_block_sector_deletion_with_assigned_locations(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    base = AgentConfig(
        sectors=[_sector("prague", "Prague"), _sector("airport", "Airport")],
        locations=[
            _location("bridge", "Bridge", sector_id="prague"),
            _location("gate", "Gate", sector_id="airport"),
        ],
        cameras=[],
    )
    save_agent_config(base, tmp_path / "agent.yaml")

    with pytest.raises(ValueError, match="Cannot remove sector"):
        save_agent_config(
            AgentConfig(
                sectors=[_sector("airport", "Airport")],
                locations=[
                    _location("bridge", "Bridge", sector_id="prague"),
                    _location("gate", "Gate", sector_id="airport"),
                ],
                cameras=[],
            )
        )


def test_overlay_from_diff_tracks_location_removals() -> None:
    base = AgentConfig(
        sectors=[_sector("prague", "Prague")],
        locations=[_location("bridge", "Bridge"), _location("square", "Square")],
        cameras=[_cam("cam", "Cam", location_id="square")],
    )
    current = AgentConfig(
        sectors=[_sector("prague", "Prague")],
        locations=[_location("square", "Square")],
        cameras=[_cam("cam", "Cam", location_id="square")],
    )
    overlay = overlay_from_diff(base, current)
    assert overlay.remove_location_ids == ["bridge"]


def test_committed_catalog_counts_and_entries() -> None:
    config = load_agent_config(agent_config_path())
    prague_locations = [
        location for location in config.locations if location.sector_id == "prague"
    ]
    japan_locations = [
        location for location in config.locations if location.sector_id == "japan"
    ]

    prague_cameras = [camera for camera in config.cameras if camera.sector_id == "prague"]

    assert len(config.cameras) == 15
    assert len(prague_cameras) == 14
    assert len(prague_locations) == 10
    assert len(japan_locations) == 1
    assert any(location.id == "marianske_namesti" for location in config.locations)
    assert any(
        camera.id == "tokachi_obihiro"
        and "youtube.com/watch?v=IDXRscHtp2s" in camera.source
        for camera in config.cameras
    )
    assert all(sector.enabled for sector in config.sectors if sector.id != UNASSIGNED_SECTOR_ID)
    assert all(location.enabled for location in config.locations)
    assert all(camera.enabled for camera in config.cameras)


def test_system_prompt_uses_location_grouping(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague")],
            locations=[
                _location("bridge", "Charles Bridge", lat=50.0865, lon=14.4119),
            ],
            cameras=[_cam("cam", "101200", location_id="bridge")],
        ),
        tmp_path / "agent.yaml",
    )

    prompt = build_system_prompt(load_agent_config())
    assert "Charles Bridge" in prompt
    assert "one camera per configured location" in prompt
    assert "101200" in prompt


def test_list_cameras_inherits_location_gps(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague")],
            locations=[_location("bridge", "Bridge", lat=50.1, lon=14.4)],
            cameras=[_cam("cam", "Cam", location_id="bridge")],
        ),
        tmp_path / "agent.yaml",
    )

    payload = json.loads(execute_tool("list_cameras", {})["tool_content"])
    assert payload["cameras"][0]["lat"] == 50.1
    assert payload["cameras"][0]["lon"] == 14.4
    assert payload["cameras"][0]["location_id"] == "bridge"
