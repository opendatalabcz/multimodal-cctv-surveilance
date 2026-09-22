import pytest

from cctv.analysis.azure_vision import _parse_json_payload
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
