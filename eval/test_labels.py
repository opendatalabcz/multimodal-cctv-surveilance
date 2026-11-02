"""Checks for timestamp labels. Run with python -m eval.test_labels."""

from pathlib import Path

from eval.cost import cost_usd, summarize_usage, token_counts
from eval.labels import build_samples
from eval.scoring import flicker, prediction_row, summarize

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = {
    "cloudy_6": 2700.037,
    "night_6": 3600.144,
    "rainy_6": 4500.06,
    "sunny_6": 6300.232,
}


def _at(samples, video: str, timestamp: int):
    return next(sample for sample in samples if sample.video == video and sample.timestamp_s == timestamp)


def _timestamps():
    candidate = ROOT / "timestamps.csv"
    if candidate.exists():
        return candidate
    return ROOT / "others" / "timestamps.csv"


def test_grid_and_states() -> None:
    samples = build_samples(_timestamps(), DURATIONS, 60)
    counts = {}
    for sample in samples:
        counts[sample.video] = counts.get(sample.video, 0) + 1
    assert counts == {"cloudy_6": 45, "night_6": 60, "rainy_6": 75, "sunny_6": 105}

    cloudy_start = _at(samples, "cloudy_6", 0)
    assert cloudy_start.truth() == {"parked": False, "tunnel_attached": False, "doors_open": False}
    assert cloudy_start.near_boundary is False

    just_parked = _at(samples, "cloudy_6", 60)
    assert just_parked.parked is True
    assert just_parked.tunnel_attached is False
    assert just_parked.doors_open is False
    assert just_parked.near_boundary is True

    full = _at(samples, "cloudy_6", 120)
    assert full.truth() == {"parked": True, "tunnel_attached": True, "doors_open": True}

    after_doors = _at(samples, "cloudy_6", 1920)
    assert after_doors.parked is True
    assert after_doors.tunnel_attached is True
    assert after_doors.doors_open is False

    rainy_after_tunnel = _at(samples, "rainy_6", 3360)
    assert rainy_after_tunnel.parked is True
    assert rainy_after_tunnel.tunnel_attached is False
    assert rainy_after_tunnel.doors_open is True

    night_before = _at(samples, "night_6", 600)
    assert night_before.parked is False
    night_parked = _at(samples, "night_6", 660)
    assert night_parked.parked is True
    assert night_parked.tunnel_attached is False
    assert night_parked.doors_open is False


def test_prompt_versions_and_few_shot_labels() -> None:
    from eval.few_shot import EXAMPLES
    from eval.labels import parse_clock
    from eval.prompt import PROMPT_VERSIONS, prompt_id

    assert set(PROMPT_VERSIONS) == {"basic", "detailed"}
    assert prompt_id(PROMPT_VERSIONS["detailed"]) == "b7178b3ab807"
    assert prompt_id(PROMPT_VERSIONS["basic"]) != prompt_id(PROMPT_VERSIONS["detailed"])
    assert "front or back door" in PROMPT_VERSIONS["detailed"]
    assert "front or back door" not in PROMPT_VERSIONS["basic"]

    rows = {row["file_name"]: row for row in __import__("csv").DictReader(_timestamps().open())}
    night = rows["night_6"]
    bounds = {
        "parked": (parse_clock(night["parked"]), parse_clock(night["left_parking"])),
        "tunnel_attached": (parse_clock(night["tunnel_attached"]), parse_clock(night["tunnel_detached"])),
        "doors_open": (parse_clock(night["doors_open"]), parse_clock(night["doors_closed"])),
    }
    for example in EXAMPLES:
        assert example.video == "night_6"
        assert example.timestamp_s % 60 != 0
        for state, (start, end) in bounds.items():
            assert getattr(example, state) is (start <= example.timestamp_s < end)


def test_parse_failure_counts_as_wrong_and_flicker_ignores_real_changes() -> None:
    timestamps = ROOT / "timestamps.csv"
    if not timestamps.exists():
        timestamps = ROOT / "others" / "timestamps.csv"
    samples = build_samples(timestamps, DURATIONS, 60)[:3]
    rows = [
        prediction_row(samples[0], {"parse_ok": True, "parsed": {**samples[0].truth(), "description": "a"}}),
        prediction_row(samples[1], {"parse_ok": False, "parsed": None, "error": "bad json"}),
        prediction_row(
            samples[2],
            {"parse_ok": True, "parsed": {"parked": False, "tunnel_attached": False, "doors_open": False, "description": "b"}},
        ),
    ]
    summary = summarize(rows, interval_seconds=60, model="gpt-4o")
    assert summary["overall"]["parse_failures"] == 1
    assert summary["overall"]["states"]["parked"]["accuracy"] == round(1 / 3, 4)
    stable = [
        prediction_row(samples[0], {"parse_ok": True, "parsed": {**samples[0].truth(), "description": ""}}),
        prediction_row(
            samples[0].__class__(**{**samples[0].to_dict(), "timestamp_s": samples[0].timestamp_s + 60, "frame_id": "x"}),
            {
                "parse_ok": True,
                "parsed": {
                    "parked": not samples[0].parked,
                    "tunnel_attached": samples[0].tunnel_attached,
                    "doors_open": samples[0].doors_open,
                    "description": "",
                },
            },
        ),
    ]
    # Same video, same truth, prediction flipped on parked.
    flips = flicker(stable)
    assert flips["stable_pairs"] == 1
    assert flips["prediction_flips"] == 1
    assert flips["by_state"]["parked"]["flips"] == 1


def test_cost_uses_cached_input_rate_and_both_usage_shapes() -> None:
    chat = token_counts(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 400},
            "completion_tokens_details": {"reasoning_tokens": 0},
        }
    )
    responses = token_counts(
        {
            "input_tokens": 1000,
            "output_tokens": 10,
            "input_tokens_details": {"cached_tokens": 400},
            "output_tokens_details": {"reasoning_tokens": 3},
        }
    )
    assert chat["input_tokens"] == responses["input_tokens"] == 1000
    assert responses["reasoning_tokens"] == 3
    priced = cost_usd("gpt-4o", {"input_tokens": 1000, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 400}})
    # 600 uncached at $2.50 and 400 cached at $1.25, plus 10 output at $10, per million.
    assert priced["total"] == round(600 * 2.5 / 1_000_000 + 400 * 1.25 / 1_000_000 + 10 * 10 / 1_000_000, 6)
    summary = summarize_usage("gpt-5.6-luna", [{"usage": {"input_tokens": 1_000_000, "output_tokens": 0}}])
    assert summary["cost_usd"]["total"] == 0.2


if __name__ == "__main__":
    test_grid_and_states()
    test_prompt_versions_and_few_shot_labels()
    test_parse_failure_counts_as_wrong_and_flicker_ignores_real_changes()
    test_cost_uses_cached_input_rate_and_both_usage_shapes()
    print("label checks passed")
