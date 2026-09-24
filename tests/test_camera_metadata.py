from unittest.mock import patch

import pytest
from pydantic import ValidationError

from cctv.analysis.camera_metadata import analyze_camera_metadata, source_fingerprint
from cctv.config.models import AgentConfig, CameraAnalysis, CameraConfig
from cctv.utils.azure import AzureOpenAIConfig


def _azure() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(api_key="key", endpoint="https://example.test", model="vision")


def _camera(source: str = "101200") -> CameraConfig:
    return CameraConfig(id="road_cam", name="Road camera", source=source)


def test_camera_analysis_rejects_unknown_tag() -> None:
    with pytest.raises(ValidationError):
        CameraAnalysis(
            description="A road",
            scene_tags=["not-a-tag"],
            source_fingerprint="abc",
            analyzed_at="2026-09-16T12:00:00Z",
        )


def test_analyze_camera_metadata_persists_validated_result(tmp_path, monkeypatch) -> None:
    frame = tmp_path / "captured.jpg"
    frame.write_bytes(b"jpeg-bytes")
    monkeypatch.setattr("cctv.analysis.camera_metadata.data_root", lambda: tmp_path)
    monkeypatch.setattr(
        "cctv.analysis.camera_metadata.images_dir",
        lambda: tmp_path / "camera_images",
    )
    config = AgentConfig(cameras=[_camera()])
    saved: list[AgentConfig] = []
    with (
        patch("cctv.analysis.camera_metadata.load_agent_config", return_value=config),
        patch(
            "cctv.analysis.camera_metadata.execute_get_image",
            return_value={"image_path": str(frame), "tool_content": '{"success": true}'},
        ),
        patch(
            "cctv.analysis.camera_metadata.analyze_images",
            return_value={
                "success": True,
                "analysis": {
                    "description": "A multilane urban road with moving vehicles.",
                    "scene_tags": ["road", "intersection"],
                },
            },
        ),
        patch("cctv.analysis.camera_metadata.save_agent_config", side_effect=saved.append),
    ):
        updated = analyze_camera_metadata("road_cam", azure_config=_azure())

    assert updated.analysis is not None
    assert updated.analysis.scene_tags == ["road", "intersection"]
    assert updated.analysis.source_fingerprint == source_fingerprint("101200")
    assert updated.analysis.preview_path == "camera_images/previews/road_cam.jpg"
    copied = tmp_path / "camera_images" / "previews" / "road_cam.jpg"
    assert copied.read_bytes() == b"jpeg-bytes"
    assert saved[0].cameras[0].analysis == updated.analysis


def test_analysis_does_not_overwrite_changed_source() -> None:
    before = AgentConfig(cameras=[_camera("old")])
    after = AgentConfig(cameras=[_camera("new")])
    with (
        patch("cctv.analysis.camera_metadata.load_agent_config", side_effect=[before, after]),
        patch(
            "cctv.analysis.camera_metadata.execute_get_image",
            return_value={"image_path": "/tmp/frame.jpg", "tool_content": '{"success": true}'},
        ),
        patch(
            "cctv.analysis.camera_metadata.analyze_images",
            return_value={
                "success": True,
                "analysis": {"description": "A road.", "scene_tags": ["road"]},
            },
        ),
        patch("cctv.analysis.camera_metadata.save_agent_config") as save,
    ):
        with pytest.raises(RuntimeError, match="source changed"):
            analyze_camera_metadata("road_cam", azure_config=_azure())
    save.assert_not_called()


def test_analysis_skips_unavailable_placeholder(tmp_path, monkeypatch) -> None:
    frame = tmp_path / "placeholder.jpg"
    frame.write_bytes(b"sleep-mode")
    preview = tmp_path / "camera_images" / "previews" / "road_cam.jpg"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"good-preview")
    existing = CameraAnalysis(
        description="A good road view.",
        scene_tags=["road"],
        source_fingerprint=source_fingerprint("101200"),
        analyzed_at="2026-09-16T12:00:00Z",
        preview_path="camera_images/previews/road_cam.jpg",
    )
    config = AgentConfig(cameras=[_camera().model_copy(update={"analysis": existing})])
    with (
        patch("cctv.analysis.camera_metadata.load_agent_config", return_value=config),
        patch(
            "cctv.analysis.camera_metadata.execute_get_image",
            return_value={
                "image_path": str(frame),
                "tool_content": '{"success": true, "likely_unavailable": true}',
                "fetch_result": {"success": True, "likely_unavailable": True},
            },
        ),
        patch("cctv.analysis.camera_metadata.analyze_images") as vision,
        patch("cctv.analysis.camera_metadata.save_agent_config") as save,
    ):
        with pytest.raises(RuntimeError, match="not currently accessible"):
            analyze_camera_metadata("road_cam", azure_config=_azure())
    vision.assert_not_called()
    save.assert_not_called()
    assert preview.read_bytes() == b"good-preview"
