import json
from pathlib import Path
from unittest.mock import patch

from cctv.config.agent_yaml import load_agent_config, save_agent_config
from cctv.config.models import AgentConfig, CameraAnalysis, CameraConfig
from cctv.config.prompt import build_system_prompt
import cctv.tools  # noqa: F401
from cctv.tools.get_camera import HARD_IMAGE_CAP, PREFERRED_IMAGE_CAP, resolve_camera
from cctv.tools.registry import default_tool_schemas, execute_tool


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "agent.yaml"
    overlay = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay)
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


def test_list_cameras_includes_scene_metadata(tmp_path, monkeypatch) -> None:
    path = _write_config(tmp_path, monkeypatch)
    config = load_agent_config(path)
    config.cameras[0] = config.cameras[0].model_copy(
        update={
            "analysis": CameraAnalysis(
                description="A pedestrian bridge with no road traffic.",
                scene_tags=["bridge", "pedestrian"],
                source_fingerprint="abc",
                analyzed_at="2026-09-16T12:00:00Z",
            )
        }
    )
    save_agent_config(config, path)
    payload = json.loads(execute_tool("list_cameras", {})["tool_content"])
    bridge = next(camera for camera in payload["cameras"] if camera["id"] == "charles_bridge")
    assert bridge["scene_tags"] == ["bridge", "pedestrian"]
    assert bridge["description"] == "A pedestrian bridge with no road traffic."


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
    assert result["image_paths"] == ["/tmp/frame.jpg"]


def test_get_camera_image_list_fetches_each_source(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    calls: list[str] = []

    def fake_get(source: str):
        calls.append(source)
        name = "bridge" if "101200" in source else "airport"
        return {
            "tool_content": json.dumps({"success": True, "source": source}),
            "image_path": f"/tmp/{name}.jpg",
            "fetch_result": {"success": True},
        }

    with patch("cctv.tools.get_camera.execute_get_image", side_effect=fake_get):
        result = execute_tool(
            "get_camera_image",
            {"cameras": ["charles_bridge", "Airport cam", "charles_bridge"]},
        )
    assert len(calls) == 2
    meta = json.loads(result["tool_content"])
    assert meta["success"] is True
    assert meta["fetched"] == 2
    assert [row["camera_id"] for row in meta["results"]] == ["charles_bridge", "airport"]
    assert result["image_paths"] == ["/tmp/bridge.jpg", "/tmp/airport.jpg"]
    assert result["image_path"] == "/tmp/bridge.jpg"
    assert result["image_labels"][0]["camera_id"] == "charles_bridge"
    assert result["image_labels"][1]["camera_id"] == "airport"


def test_get_camera_image_partial_unknown(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    fake = {
        "tool_content": json.dumps({"success": True}),
        "image_path": "/tmp/frame.jpg",
        "fetch_result": {"success": True},
    }
    with patch("cctv.tools.get_camera.execute_get_image", return_value=fake):
        result = execute_tool(
            "get_camera_image",
            {"cameras": ["missing", "charles_bridge"]},
        )
    meta = json.loads(result["tool_content"])
    assert meta["success"] is True
    assert meta["fetched"] == 1
    assert meta["results"][0]["success"] is False
    assert "Unknown camera" in meta["results"][0]["error"]
    assert meta["results"][1]["camera_id"] == "charles_bridge"


def test_get_camera_image_hard_cap(tmp_path, monkeypatch) -> None:
    cameras = [
        CameraConfig(
            id=f"cam_{index}",
            name=f"Cam {index}",
            source=f"https://example.invalid/{index}.jpg",
        )
        for index in range(HARD_IMAGE_CAP + 3)
    ]
    path = tmp_path / "agent.yaml"
    overlay = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay)
    save_agent_config(AgentConfig(cameras=cameras), path)

    def fake_get(source: str):
        return {
            "tool_content": json.dumps({"success": True, "source": source}),
            "image_path": f"/tmp/{source.rsplit('/', 1)[-1]}",
            "fetch_result": {"success": True},
        }

    names = [f"cam_{index}" for index in range(HARD_IMAGE_CAP + 3)]
    with patch("cctv.tools.get_camera.execute_get_image", side_effect=fake_get):
        result = execute_tool("get_camera_image", {"cameras": names})
    meta = json.loads(result["tool_content"])
    assert meta["fetched"] == HARD_IMAGE_CAP
    assert len(meta["skipped"]) == 3
    assert PREFERRED_IMAGE_CAP < HARD_IMAGE_CAP


def test_get_camera_image_missing_arguments() -> None:
    result = execute_tool("get_camera_image", {})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "Missing camera" in payload["error"]


def test_unknown_tool_name() -> None:
    result = execute_tool("not_a_tool", {})
    payload = json.loads(result["tool_content"])
    assert payload["success"] is False
    assert "Unknown tool" in payload["error"]


def test_system_prompt_named_tools(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    prompt = build_system_prompt(load_agent_config())
    assert "get_camera_image" in prompt
    assert "cameras: [id or name, ...]" in prompt
    assert "one camera per configured location" in prompt
    assert "list_cameras" in prompt
    assert "charles_bridge" in prompt
    assert "internet search (web_search): disabled" in prompt
    assert "map access (search_map, reverse_geocode): disabled" in prompt
    assert "101200" not in prompt
