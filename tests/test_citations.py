from cctv.analysis.citations import (
    FetchedFrame,
    frames_from_tool_result,
    parse_cited_cameras,
    select_cited_paths,
)


def test_parse_cited_cameras_strips_fence() -> None:
    text = "Charles Bridge is busy.\n\n```cite\ncharles_bridge\nhybernska\n```\n"
    display, citations = parse_cited_cameras(text)
    assert display == "Charles Bridge is busy."
    assert citations == ["charles_bridge", "hybernska"]


def test_parse_cited_cameras_empty_fence() -> None:
    display, citations = parse_cited_cameras("No frames needed.\n```cite\n```")
    assert display == "No frames needed."
    assert citations == []


def test_parse_cited_cameras_missing_fence() -> None:
    display, citations = parse_cited_cameras("Both look clear.")
    assert display == "Both look clear."
    assert citations is None


def test_parse_cited_cameras_json_array() -> None:
    _, citations = parse_cited_cameras('Answer.\n```cite\n["cam_a", "cam_b"]\n```')
    assert citations == ["cam_a", "cam_b"]


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
    assert select_cited_paths(frames, None) == ["/tmp/a.jpg", "/tmp/b.jpg", "/tmp/c.jpg"]
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
