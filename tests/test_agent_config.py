from cctv.config.agent_yaml import (
    load_agent_config,
    load_overlay,
    overlay_from_diff,
    save_agent_config,
)
from cctv.config.models import AgentConfig, CameraConfig, ToolsConfig


def _cam(camera_id: str, name: str, source: str = "101048") -> CameraConfig:
    return CameraConfig(id=camera_id, name=name, source=source)


def test_load_default_agent_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        """\
cameras:
  - id: test_cam
    name: Test Camera
    lat: 50.0
    lon: 14.0
    source: "101048"
tools:
  internet: true
  weather: false
  maps: false
""",
        encoding="utf-8",
    )

    config = load_agent_config(config_path)
    assert len(config.cameras) == 1
    assert config.cameras[0].id == "test_cam"
    assert config.cameras[0].name == "Test Camera"
    assert config.tools.internet is True
    assert config.tools.weather is False
    assert config.tools.maps is False


def test_legacy_google_maps_migrates_to_maps(tmp_path) -> None:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        """\
tools:
  internet: true
  google_maps: true
""",
        encoding="utf-8",
    )

    config = load_agent_config(config_path)
    assert config.tools.maps is True
    assert config.tools.weather is False
    assert config.tools.internet is True


def test_internet_on_does_not_enable_weather(tmp_path) -> None:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text("tools:\n  internet: true\n", encoding="utf-8")
    config = load_agent_config(config_path)
    assert config.tools.internet is True
    assert config.tools.weather is False
    assert config.tools.maps is False


def test_save_agent_config_round_trip(tmp_path) -> None:
    config_path = tmp_path / "configs" / "agent.yaml"
    original = AgentConfig(
        cameras=[
            CameraConfig(
                id="hybernska",
                name="Hybernská",
                lat=None,
                lon=None,
                source="https://example.test/cameras/101048/image",
            )
        ],
        tools=ToolsConfig(internet=False, weather=False, maps=True),
    )

    save_agent_config(original, config_path)
    loaded = load_agent_config(config_path)

    assert loaded.model_dump() == original.model_dump()


def test_load_missing_config_returns_defaults(tmp_path) -> None:
    config = load_agent_config(tmp_path / "missing.yaml")
    assert config.cameras == []
    assert config.tools.internet is False
    assert config.tools.weather is False
    assert config.tools.maps is False


def test_overlay_tools_and_extra_camera(tmp_path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Bridge")],
            tools=ToolsConfig(internet=False, weather=False, maps=False),
        ),
        base_path,
    )

    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Bridge"), _cam("airport", "Airport", "https://youtu.be/x")],
            tools=ToolsConfig(internet=True, weather=False, maps=False),
        )
    )

    overlay = load_overlay()
    assert overlay.tools is not None
    assert overlay.tools.internet is True
    assert overlay.tools.weather is False
    assert [camera.id for camera in overlay.cameras] == ["airport"]
    assert overlay.remove_camera_ids == []

    merged = load_agent_config()
    assert [camera.id for camera in merged.cameras] == ["bridge", "airport"]
    assert merged.tools.internet is True
    assert load_agent_config(base_path).tools.internet is False


def test_overlay_edit_and_remove_camera(tmp_path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Bridge"), _cam("street", "Street")],
            tools=ToolsConfig(),
        ),
        base_path,
    )

    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Charles Bridge")],
            tools=ToolsConfig(),
        )
    )

    overlay = load_overlay()
    assert overlay.remove_camera_ids == ["street"]
    assert overlay.cameras[0].name == "Charles Bridge"

    merged = load_agent_config()
    assert [camera.id for camera in merged.cameras] == ["bridge"]
    assert merged.cameras[0].name == "Charles Bridge"


def test_save_matching_base_deletes_overlay(tmp_path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    base = AgentConfig(cameras=[_cam("bridge", "Bridge")], tools=ToolsConfig())
    save_agent_config(base, base_path)
    overlay_path.write_text("tools:\n  internet: true\n  maps: false\n", encoding="utf-8")

    save_agent_config(base)
    assert not overlay_path.is_file()
    assert overlay_from_diff(base, base).tools is None
