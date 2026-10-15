from cctv.analysis.citations import (
    FetchedFrame,
    frames_from_tool_result,
    normalize_followups,
    select_cited_paths,
)


def test_normalize_followups_caps_at_three_and_drops_long_lines() -> None:
    followups = normalize_followups(["1. One?", "2. Two?", "3. Three?", "4. Four?"])
    assert followups == ["One?", "Two?", "Three?"]
    assert normalize_followups(["x" * 200 + "?"]) == []


def test_normalize_followups_deduplicates() -> None:
    assert normalize_followups(["Same?", "same?", "Other?"]) == ["Same?", "Other?"]


def test_select_cited_paths_filters_and_preserves_order() -> None:
    frames = [
        FetchedFrame("/tmp/a.jpg", camera_id="cam_a", camera_name="A"),
        FetchedFrame("/tmp/b.jpg", camera_id="cam_b", camera_name="B"),
        FetchedFrame("/tmp/c.jpg", camera_id="cam_c", camera_name="C"),
    ]
    assert select_cited_paths(frames, ["B", "cam_a", "missing"]) == [
        "/tmp/b.jpg",
        "/tmp/a.jpg",
    ]
    assert select_cited_paths(frames, []) == []


def test_frames_from_tool_result_uses_image_labels() -> None:
    frames = frames_from_tool_result(
        {
            "image_paths": ["/tmp/a.jpg"],
            "image_labels": [
                {"path": "/tmp/a.jpg", "camera_id": "cam_a", "camera_name": "A"},
            ],
        }
    )
    assert frames == [FetchedFrame("/tmp/a.jpg", camera_id="cam_a", camera_name="A")]


def test_frames_from_tool_result_falls_back_to_arguments() -> None:
    frames = frames_from_tool_result(
        {"image_paths": ["/tmp/cam_a.jpg", "/tmp/cam_b.jpg"]},
        {"cameras": ["cam_a", "cam_b"]},
    )
    assert [frame.camera_id for frame in frames] == ["cam_a", "cam_b"]
