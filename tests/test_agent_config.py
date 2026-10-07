from cctv.config.agent_yaml import (
    load_agent_config,
    load_overlay,
    overlay_from_diff,
    save_agent_config,
)
from cctv.config.effective import UNASSIGNED_SECTOR_ID
from cctv.config.models import (
    AgentConfig,
    CameraAnalysis,
    CameraConfig,
    ModelOption,
    SectorConfig,
    ToolsConfig,
    default_model_catalog,
)


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

    assert loaded.cameras[0].id == "hybernska"
    assert loaded.cameras[0].sector_id == UNASSIGNED_SECTOR_ID
    assert any(sector.id == UNASSIGNED_SECTOR_ID for sector in loaded.sectors)
    assert loaded.tools.maps is True


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


def test_generated_camera_metadata_is_stored_in_overlay(tmp_path, monkeypatch) -> None:
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    base = AgentConfig(cameras=[_cam("bridge", "Bridge")])
    save_agent_config(base, base_path)
    current = load_agent_config()
    current.cameras[0].analysis = CameraAnalysis(
        description="A pedestrian bridge.",
        scene_tags=["bridge", "pedestrian"],
        source_fingerprint="abc",
        analyzed_at="2026-09-16T12:00:00Z",
    )
    save_agent_config(current)

    assert load_overlay().cameras[0].analysis is not None
    assert load_agent_config().cameras[0].analysis.description == "A pedestrian bridge."


def test_overlay_stores_selected_model_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-5.6-luna")
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    base = AgentConfig(cameras=[_cam("bridge", "Bridge")])
    save_agent_config(base, base_path)

    save_agent_config(base.model_copy(update={"model": "gpt-4o"}))

    overlay = load_overlay()
    assert overlay.model == "gpt-4o"
    assert overlay.cameras == []
    assert overlay.tools is None
    text = overlay_path.read_text(encoding="utf-8")
    assert "models:" not in text
    assert [item.id for item in load_agent_config(base_path).models] == [
        item.id for item in default_model_catalog()
    ]
    assert load_agent_config(base_path).model == "gpt-5.6-luna"
    merged = load_agent_config()
    assert merged.model == "gpt-4o"
    assert [item.id for item in merged.models] == [item.id for item in default_model_catalog()]


def test_env_deployment_is_appended_when_missing_from_catalog(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "custom-deploy")
    config_path = tmp_path / "agent.yaml"
    save_agent_config(AgentConfig(cameras=[_cam("bridge", "Bridge")]), config_path)

    loaded = load_agent_config(config_path)

    assert [item.id for item in loaded.models] == [
        *[item.id for item in default_model_catalog()],
        "custom-deploy",
    ]
    assert loaded.models[-1] == ModelOption(id="custom-deploy", label="custom-deploy", provider="azure")


def test_overlay_stores_non_default_settings_per_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-5.6-luna")
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(AgentConfig(cameras=[_cam("bridge", "Bridge")]), base_path)

    save_agent_config(AgentConfig(cameras=[_cam("bridge", "Bridge")], reasoning="high"))
    assert load_overlay().reasoning == {"gpt-5.6-luna": "high"}
    assert load_overlay().verbosity == {}
    assert load_overlay().model is None
    loaded = load_agent_config()
    assert loaded.reasoning["gpt-5.6-luna"] == "high"
    assert loaded.reasoning["gpt-6-astra"] == "medium"
    assert loaded.verbosity["gpt-5.6-luna"] == "medium"

    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Bridge")],
            model="gpt-6-astra",
            reasoning={"gpt-5.6-luna": "high", "gpt-6-astra": "max"},
            verbosity={"gpt-5.6-luna": "low", "gpt-6-astra": "high"},
        )
    )
    overlay = load_overlay()
    assert overlay.model == "gpt-6-astra"
    assert overlay.reasoning == {"gpt-5.6-luna": "high", "gpt-6-astra": "max"}
    assert overlay.verbosity == {"gpt-5.6-luna": "low", "gpt-6-astra": "high"}
    merged = load_agent_config()
    assert merged.model == "gpt-6-astra"
    assert merged.reasoning["gpt-5.6-luna"] == "high"
    assert merged.reasoning["gpt-6-astra"] == "max"
    assert merged.reasoning["gpt-4o"] == "default"
    assert merged.verbosity["gpt-5.6-luna"] == "low"
    assert merged.verbosity["gpt-6-astra"] == "high"
    assert merged.verbosity["gpt-4o"] == "medium"

    save_agent_config(
        AgentConfig(
            cameras=[_cam("bridge", "Bridge")],
            model="gpt-5.6-luna",
            reasoning=merged.reasoning,
            verbosity=merged.verbosity,
        )
    )
    kept = load_agent_config()
    assert kept.model == "gpt-5.6-luna"
    assert kept.reasoning["gpt-6-astra"] == "max"
    assert kept.verbosity["gpt-5.6-luna"] == "low"


def test_luna_catalog_uses_responses_with_explicit_reasoning_default() -> None:
    luna = next(item for item in default_model_catalog() if item.id == "gpt-5.6-luna")

    assert luna.transport == "responses"
    assert luna.reasoning.default == "medium"
    assert luna.reasoning.choices == ["none", "low", "medium", "high", "xhigh", "max"]
    assert "default" not in luna.reasoning.choices


def test_legacy_luna_default_reasoning_clamps_to_medium(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-5.6-luna")
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(AgentConfig(cameras=[_cam("bridge", "Bridge")]), base_path)
    overlay_path.write_text(
        "reasoning:\n  gpt-5.6-luna: default\n",
        encoding="utf-8",
    )

    merged = load_agent_config()

    assert merged.reasoning["gpt-5.6-luna"] == "medium"


def test_legacy_reasoning_string_loads_for_the_selected_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-5.6-luna")
    base_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: base_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(AgentConfig(cameras=[_cam("bridge", "Bridge")]), base_path)
    overlay_path.write_text("model: gpt-6-astra\nreasoning: low\n", encoding="utf-8")

    assert load_overlay().reasoning == {"gpt-6-astra": "low"}
    merged = load_agent_config()
    assert merged.model == "gpt-6-astra"
    assert merged.reasoning["gpt-6-astra"] == "low"
    assert merged.reasoning["gpt-5.6-luna"] == "medium"
