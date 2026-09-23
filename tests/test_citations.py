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


def test_parse_cited_cameras_sep_fence() -> None:
    display, citations = parse_cited_cameras(
        "Charles Bridge is busy.\n\n```sep\ncharles_bridge\n```\n"
    )
    assert display == "Charles Bridge is busy."
    assert citations == ["charles_bridge"]


def test_parse_cited_cameras_unclosed_cite_fence() -> None:
    display, citations = parse_cited_cameras("The square is quiet.\n```cite\ncharles_bridge")
    assert display == "The square is quiet."
    assert citations == ["charles_bridge"]


def test_parse_cited_cameras_same_line_fence() -> None:
    display, citations = parse_cited_cameras("Busy traffic.\n```cite charles_bridge```")
    assert display == "Busy traffic."
    assert citations == ["charles_bridge"]


def test_parse_cited_cameras_strips_trailing_sep_token() -> None:
    display, citations = parse_cited_cameras(
        "Charles Bridge is busy.\n\n```cite\ncharles_bridge\n```\n..sep\n"
    )
    assert display == "Charles Bridge is busy."
    assert citations == ["charles_bridge"]


def test_parse_cited_cameras_strips_sep_token_without_fence() -> None:
    display, citations = parse_cited_cameras("The street is wet.\n..sep\n")
    assert display == "The street is wet."
    assert citations is None


def test_parse_cited_cameras_keeps_mid_answer_code_fence() -> None:
    text = "Example:\n\n```python\nprint('ok')\n```\n\nThe road is clear."
    display, citations = parse_cited_cameras(text)
    assert display == text
    assert citations is None


def test_parse_cited_cameras_keeps_trailing_real_code_fence() -> None:
    text = "Example:\n\n```python\nprint('ok')\n```"
    display, citations = parse_cited_cameras(text)
    assert "print('ok')" in display
    assert citations is None


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
