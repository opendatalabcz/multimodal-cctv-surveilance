from cctv.analysis.azure_vision import _parse_json_payload


def test_parse_json_payload_from_fenced_text() -> None:
    text = 'Here is the result:\n```json\n{"overcrowdedness_level": 6}\n```'
    assert _parse_json_payload(text) == {"overcrowdedness_level": 6}


def test_parse_json_payload_from_prose_wrapper() -> None:
    text = 'Analysis:\n{"traffic_flow": "light", "pedestrians": 3}'
    assert _parse_json_payload(text) == {"traffic_flow": "light", "pedestrians": 3}


def test_parse_json_payload_without_json() -> None:
    assert _parse_json_payload("no json here") == {"raw_response": "no json here"}
