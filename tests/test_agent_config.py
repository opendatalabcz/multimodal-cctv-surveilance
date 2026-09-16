from cctv.config.agent_yaml import load_agent_config, save_agent_config
from cctv.config.models import AgentConfig, CameraConfig, ToolsConfig


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
  google_maps: false
""",
        encoding="utf-8",
    )

    config = load_agent_config(config_path)
    assert len(config.cameras) == 1
    assert config.cameras[0].id == "test_cam"
    assert config.cameras[0].name == "Test Camera"
    assert config.tools.internet is True
    assert config.tools.google_maps is False


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
        tools=ToolsConfig(internet=False, google_maps=True),
    )

    save_agent_config(original, config_path)
    loaded = load_agent_config(config_path)

    assert loaded.model_dump() == original.model_dump()


def test_load_missing_config_returns_defaults(tmp_path) -> None:
    config = load_agent_config(tmp_path / "missing.yaml")
    assert config.cameras == []
    assert config.tools.internet is False
    assert config.tools.google_maps is False
