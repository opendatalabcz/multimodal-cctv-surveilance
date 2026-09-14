import json
from io import BytesIO

import pytest
from PIL import Image

from cctv.analysis.azure_vision import _parse_json_payload, save_experiment
from cctv.utils.prompts import load_place_prompt


@pytest.mark.parametrize("place_id", ["charles_bridge", "hybernska", "budejovicka", "jecna"])
def test_load_place_prompt(place_id: str) -> None:
    prompt = load_place_prompt(place_id)
    assert "# CCTV Camera Image Analysis Prompt" in prompt
    assert "{place}" not in prompt
    assert "{requirements}" not in prompt
    assert "{output_format}" not in prompt


def test_parse_json_payload_from_fenced_text() -> None:
    text = 'Here is the result:\n```json\n{"overcrowdedness_level": 6}\n```'
    assert _parse_json_payload(text) == {"overcrowdedness_level": 6}


def test_parse_json_payload_from_prose_wrapper() -> None:
    text = 'Analysis:\n{"traffic_flow": "light", "pedestrians": 3}'
    assert _parse_json_payload(text) == {"traffic_flow": "light", "pedestrians": 3}


def test_parse_json_payload_without_json() -> None:
    assert _parse_json_payload("no json here") == {"raw_response": "no json here"}


def test_save_experiment_writes_normalized_envelope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    result = {
        "success": True,
        "analysis": {"congestion_level": 3},
        "raw_response": '{"congestion_level": 3}',
        "usage": {"total_tokens": 100},
        "timestamp": "2026-09-07T12:00:00",
        "image_paths": [str(tmp_path / "camera_images" / "jecna" / "frame.jpg")],
        "image_count": 1,
        "model": "gpt-test",
    }
    path = save_experiment(result, "jecna", kind="single")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "experiments" / "jecna"
    assert payload["place_id"] == "jecna"
    assert payload["kind"] == "single"
    assert payload["success"] is True
    assert payload["model"] == "gpt-test"
    assert payload["usage"] == {"total_tokens": 100}
    assert payload["analysis"] == {"congestion_level": 3}
    assert payload["image_paths"] == ["camera_images/jecna/frame.jpg"]
