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


def test_analyze_camera_metadata_persists_validated_result() -> None:
    config = AgentConfig(cameras=[_camera()])
    saved: list[AgentConfig] = []
    with (
        patch("cctv.analysis.camera_metadata.load_agent_config", return_value=config),
        patch(
            "cctv.analysis.camera_metadata.execute_get_image",
            return_value={"image_path": "/tmp/frame.jpg", "tool_content": '{"success": true}'},
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
