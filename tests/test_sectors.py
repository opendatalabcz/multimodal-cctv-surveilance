import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cctv.config.agent_yaml import (
    load_agent_config,
    load_overlay,
    overlay_from_diff,
    save_agent_config,
)
from cctv.config.effective import (
    UNASSIGNED_SECTOR_ID,
    effective_cameras,
    is_camera_effective,
    normalize_agent_config,
)
from cctv.config.models import AgentConfig, CameraConfig, LocationConfig, SectorConfig, ToolsConfig
from cctv.config.prompt import build_system_prompt
from cctv.tools.get_camera import resolve_camera
from cctv.tools.registry import execute_tool


def _location(
    location_id: str,
    name: str,
    *,
    sector_id: str | None = None,
    enabled: bool = True,
) -> LocationConfig:
    return LocationConfig(
        id=location_id,
        name=name,
        sector_id=sector_id,
        enabled=enabled,
    )


def _cam(
    camera_id: str,
    name: str,
    *,
    sector_id: str | None = None,
    location_id: str | None = None,
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


def _sector(sector_id: str, name: str, *, enabled: bool = True) -> SectorConfig:
    return SectorConfig(id=sector_id, name=name, enabled=enabled)


def _patch_paths(tmp_path: Path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)


def test_legacy_config_migrates_to_unassigned(tmp_path) -> None:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        """\
cameras:
  - id: bridge
    name: Bridge
    source: "101200"
tools:
  internet: false
""",
        encoding="utf-8",
    )

    config = load_agent_config(config_path)
    assert any(sector.id == UNASSIGNED_SECTOR_ID for sector in config.sectors)
    assert config.cameras[0].sector_id == UNASSIGNED_SECTOR_ID
    assert config.cameras[0].enabled is True
    assert config.sectors[0].enabled is True


def test_effective_camera_and_combinations() -> None:
    config = normalize_agent_config(
        AgentConfig(
            sectors=[
                _sector("prague", "Prague", enabled=True),
                _sector("tokyo", "Tokyo", enabled=False),
            ],
            locations=[
                _location("prague_loc", "Prague spot", sector_id="prague"),
                _location("tokyo_loc", "Tokyo spot", sector_id="tokyo"),
            ],
            cameras=[
                _cam("a", "A", sector_id="prague", location_id="prague_loc", enabled=True),
                _cam("b", "B", sector_id="prague", location_id="prague_loc", enabled=False),
                _cam("c", "C", sector_id="tokyo", location_id="tokyo_loc", enabled=True),
                _cam("d", "D", sector_id="tokyo", location_id="tokyo_loc", enabled=False),
            ],
        )
    )

    assert is_camera_effective(config, config.cameras[0]) is True
    assert is_camera_effective(config, config.cameras[1]) is False
    assert is_camera_effective(config, config.cameras[2]) is False
    assert is_camera_effective(config, config.cameras[3]) is False
    assert [camera.id for camera in effective_cameras(config)] == ["a"]


def test_overlay_sector_round_trip(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    base = AgentConfig(
        sectors=[_sector("prague", "Prague")],
        locations=[_location("bridge", "Bridge", sector_id="prague")],
        cameras=[_cam("bridge", "Bridge", sector_id="prague", location_id="bridge")],
        tools=ToolsConfig(),
    )
    save_agent_config(base, tmp_path / "agent.yaml")

    updated = AgentConfig(
        sectors=[_sector("prague", "Prague", enabled=False), _sector("airport", "Airport")],
        locations=[
            _location("bridge", "Bridge", sector_id="prague"),
            _location("gate", "Gate", sector_id="airport"),
        ],
        cameras=[
            _cam("bridge", "Bridge", sector_id="prague", location_id="bridge", enabled=False),
            _cam("gate", "Gate", sector_id="airport", location_id="gate"),
        ],
        tools=ToolsConfig(internet=True),
    )
    save_agent_config(updated)

    overlay = load_overlay()
    assert overlay.tools is not None
    assert overlay.tools.internet is True
    assert {sector.id for sector in overlay.sectors} == {"prague", "airport"}
    assert {camera.id for camera in overlay.cameras} == {"bridge", "gate"}

    merged = load_agent_config()
    assert merged.tools.internet is True
    assert merged.sectors[0].enabled is False
    assert merged.cameras[0].enabled is False
    assert merged.cameras[1].sector_id == "airport"


def test_block_sector_deletion_with_assigned_cameras(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    base = AgentConfig(
        sectors=[_sector("prague", "Prague"), _sector("airport", "Airport")],
        locations=[
            _location("bridge", "Bridge", sector_id="prague"),
            _location("gate", "Gate", sector_id="airport"),
        ],
        cameras=[
            _cam("bridge", "Bridge", sector_id="prague", location_id="bridge"),
            _cam("gate", "Gate", sector_id="airport", location_id="gate"),
        ],
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
                cameras=[
                    _cam("bridge", "Bridge", sector_id="prague", location_id="bridge"),
                    _cam("gate", "Gate", sector_id="airport", location_id="gate"),
                ],
            )
        )


def test_overlay_from_diff_tracks_sector_removals_only_when_empty() -> None:
    base = AgentConfig(
        sectors=[_sector("prague", "Prague"), _sector("airport", "Airport")],
        cameras=[_cam("gate", "Gate", sector_id="airport")],
    )
    current = AgentConfig(
        sectors=[_sector("airport", "Airport")],
        cameras=[_cam("gate", "Gate", sector_id="airport")],
    )
    overlay = overlay_from_diff(base, current)
    assert overlay.remove_sector_ids == ["prague"]


def test_list_cameras_only_effective(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague", enabled=False)],
            locations=[_location("bridge", "Bridge", sector_id="prague")],
            cameras=[_cam("bridge", "Bridge", sector_id="prague", location_id="bridge")],
        ),
        tmp_path / "agent.yaml",
    )

    payload = json.loads(execute_tool("list_cameras", {})["tool_content"])
    assert payload["count"] == 0


def test_get_camera_image_rejects_disabled_camera(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague")],
            locations=[_location("bridge", "Bridge", sector_id="prague")],
            cameras=[
                _cam("bridge", "Bridge", sector_id="prague", location_id="bridge", enabled=False)
            ],
        ),
        tmp_path / "agent.yaml",
    )

    assert resolve_camera("bridge") is not None
    result = execute_tool("get_camera_image", {"camera": "bridge"})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "disabled" in payload["error"].lower()
    assert result["image_path"] is None


def test_get_camera_image_partial_disabled_and_unknown(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague", enabled=False), _sector("airport", "Airport")],
            locations=[
                _location("bridge", "Bridge", sector_id="prague"),
                _location("gate", "Gate", sector_id="airport"),
            ],
            cameras=[
                _cam("bridge", "Bridge", sector_id="prague", location_id="bridge"),
                _cam("gate", "Gate", sector_id="airport", location_id="gate"),
            ],
        ),
        tmp_path / "agent.yaml",
    )

    fake = {
        "tool_content": json.dumps({"success": True}),
        "image_path": "/tmp/frame.jpg",
        "fetch_result": {"success": True},
    }
    with patch("cctv.tools.get_camera.execute_get_image", return_value=fake):
        result = execute_tool(
            "get_camera_image",
            {"cameras": ["bridge", "missing", "gate"]},
        )

    meta = json.loads(result["tool_content"])
    assert meta["success"] is True
    assert meta["fetched"] == 1
    assert meta["results"][0]["success"] is False
    assert "disabled" in meta["results"][0]["error"].lower()
    assert meta["results"][1]["success"] is False
    assert "Unknown camera" in meta["results"][1]["error"]
    assert meta["results"][2]["camera_id"] == "gate"


def test_system_prompt_lists_only_effective_cameras(tmp_path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    save_agent_config(
        AgentConfig(
            sectors=[_sector("prague", "Prague"), _sector("tokyo", "Tokyo", enabled=False)],
            locations=[
                _location("bridge", "Bridge", sector_id="prague"),
                _location("shibuya", "Shibuya", sector_id="tokyo"),
            ],
            cameras=[
                _cam("bridge", "Bridge", sector_id="prague", location_id="bridge"),
                _cam("shibuya", "Shibuya", sector_id="tokyo", location_id="shibuya"),
            ],
        ),
        tmp_path / "agent.yaml",
    )

    prompt = build_system_prompt(load_agent_config())
    assert "Bridge" in prompt
    assert "Shibuya" not in prompt
    assert "effectively enabled" in prompt
