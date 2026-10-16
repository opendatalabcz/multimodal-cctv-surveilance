from cctv.analysis.presentation import (
    FetchedFrame,
    frames_from_tool_result,
    normalize_followups,
    select_presented_images,
)


def _frames() -> list[FetchedFrame]:
    return [
        FetchedFrame("/tmp/a.jpg", camera_id="cam_a", camera_name="A"),
        FetchedFrame("/tmp/b.jpg", camera_id="cam_b", camera_name="B"),
        FetchedFrame("/tmp/c.jpg", camera_id="cam_c", camera_name="C"),
    ]


def test_normalize_followups_caps_at_three_and_drops_long_lines() -> None:
    followups = normalize_followups(["1. One?", "2. Two?", "3. Three?", "4. Four?"])
    assert followups == ["One?", "Two?", "Three?"]
    assert normalize_followups(["x" * 200 + "?"]) == []


def test_normalize_followups_deduplicates() -> None:
    assert normalize_followups(["Same?", "same?", "Other?"]) == ["Same?", "Other?"]


def test_select_presented_images_filters_and_preserves_order() -> None:
    presented = select_presented_images(
        _frames(),
        [
            {"camera_id": "B", "annotations": []},
            {"camera_id": "cam_a", "annotations": []},
            {"camera_id": "missing"},
            "not-an-image",
        ],
    )
    assert [item.frame.path for item in presented] == ["/tmp/b.jpg", "/tmp/a.jpg"]
    assert select_presented_images(_frames(), []) == []
    assert select_presented_images(_frames(), None) == []


def test_select_presented_images_drops_duplicate_frames() -> None:
    presented = select_presented_images(
        _frames(),
        [
            {"camera_id": "cam_a", "annotations": []},
            {"camera_id": "A", "annotations": []},
        ],
    )
    assert [item.frame.path for item in presented] == ["/tmp/a.jpg"]


def test_select_presented_images_keeps_valid_shapes_and_drops_bad_geometry() -> None:
    presented = select_presented_images(
        _frames(),
        [
            {
                "camera_id": "cam_a",
                "annotations": [
                    {"type": "box", "label": "Stopped vehicle", "points": [[420, 510], [600, 670]]},
                    {"type": "point", "label": "Signal", "points": [[755.0, 180]]},
                    {"type": "line", "points": [[100, 800], [900, 820]]},
                    {
                        "type": "polygon",
                        "label": "Crosswalk",
                        "points": [[100, 700], [400, 680], [420, 900]],
                    },
                    {"type": "box", "points": [[1, 2]]},
                    {"type": "point", "points": [[-1, 10]]},
                    {"type": "point", "points": [[1200, 10]]},
                    {"type": "point", "points": [[10.5, 10]]},
                    {"type": "arrow", "points": [[1, 1]]},
                    {"type": "point", "label": "x" * 81, "points": [[1, 1]]},
                    {"type": "point", "label": 12, "points": [[1, 1]]},
                    {
                        "type": "line",
                        "points": [[1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6], [7, 7], [8, 8], [9, 9]],
                    },
                ],
            }
        ],
    )
    assert [annotation.as_dict() for annotation in presented[0].annotations] == [
        {"type": "box", "label": "Stopped vehicle", "points": [[420, 510], [600, 670]]},
        {"type": "point", "label": "Signal", "points": [[755, 180]]},
        {"type": "line", "points": [[100, 800], [900, 820]]},
        {"type": "polygon", "label": "Crosswalk", "points": [[100, 700], [400, 680], [420, 900]]},
    ]


def test_select_presented_images_caps_annotations_at_eight() -> None:
    presented = select_presented_images(
        _frames(),
        [
            {
                "camera_id": "cam_a",
                "annotations": [
                    {"type": "point", "label": str(index), "points": [[index, index]]}
                    for index in range(10)
                ],
            }
        ],
    )
    assert [annotation.label for annotation in presented[0].annotations] == [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    ]


def test_missing_annotations_still_shows_the_frame() -> None:
    presented = select_presented_images(_frames(), [{"camera_id": "cam_c"}])
    assert presented[0].frame.path == "/tmp/c.jpg"
    assert presented[0].annotations == ()


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
