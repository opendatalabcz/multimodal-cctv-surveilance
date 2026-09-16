import json
from pathlib import Path
from unittest.mock import patch

from cctv.config.agent_yaml import load_agent_config, save_agent_config
from cctv.config.models import AgentConfig, CameraConfig
from cctv.config.prompt import build_system_prompt
import cctv.tools  # noqa: F401
from cctv.tools.get_camera import resolve_camera
from cctv.tools.registry import default_tool_schemas, execute_tool


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "agent.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: path)
    config = AgentConfig(
        cameras=[
            CameraConfig(
                id="charles_bridge",
                name="Charles Bridge",
                lat=50.0865,
                lon=14.4119,
                source="https://bezpecnost.praha.eu/Intens.CrisisPortalInfrastructureApp/cameras/101200/image",
            ),
            CameraConfig(
                id="airport",
                name="Airport cam",
                source="https://www.youtube.com/watch?v=IDXRscHtp2s",
            ),
        ]
    )
    save_agent_config(config, path)
    return path


def test_default_tool_schemas() -> None:
    names = [item["function"]["name"] for item in default_tool_schemas()]
    assert names == ["list_cameras", "get_camera_image"]


def test_list_cameras_matches_yaml(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    result = execute_tool("list_cameras", {})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is True
    assert payload["count"] == 2
    assert result["image_path"] is None
    by_id = {row["id"]: row for row in payload["cameras"]}
    assert by_id["charles_bridge"]["name"] == "Charles Bridge"
    assert by_id["charles_bridge"]["source_type"] == "prague_camera"
    assert by_id["airport"]["source_type"] == "youtube"


def test_resolve_camera_id_and_name(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    assert resolve_camera("charles_bridge") is not None
    assert resolve_camera("Charles Bridge") is not None
    assert resolve_camera("CHARLES_BRIDGE") is not None
    assert resolve_camera("missing") is None


def test_get_camera_image_unknown(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    result = execute_tool("get_camera_image", {"camera": "not-a-cam"})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "Unknown camera" in payload["error"]
    assert result["image_path"] is None


def test_get_camera_image_uses_configured_source(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    fake = {
        "tool_content": json.dumps({"success": True, "source_type": "prague_camera"}),
        "image_path": "/tmp/frame.jpg",
        "fetch_result": {"success": True},
    }
    with patch("cctv.tools.get_camera.execute_get_image", return_value=fake) as mocked:
        result = execute_tool("get_camera_image", {"camera": "charles_bridge"})
    mocked.assert_called_once()
    source = mocked.call_args[0][0]
    assert "101200" in source
    meta = json.loads(result["tool_content"])
    assert meta["camera_id"] == "charles_bridge"
    assert meta["camera_name"] == "Charles Bridge"
    assert result["image_path"] == "/tmp/frame.jpg"


def test_unknown_tool_name() -> None:
    result = execute_tool("not_a_tool", {})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "Unknown tool" in payload["error"]


def test_system_prompt_named_tools(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    prompt = build_system_prompt(load_agent_config())
    assert "get_camera_image" in prompt
    assert "list_cameras" in prompt
    assert "charles_bridge" in prompt
    assert "internet search: disabled" in prompt
    assert "google maps: disabled" in prompt
    assert "101200" not in prompt
