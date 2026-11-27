"""Checks for timestamp labels. Run with python -m eval.test_labels."""

from pathlib import Path
from threading import Barrier, Lock
from time import sleep

from eval.cost import cost_usd, summarize_usage, token_counts
from eval.concurrency import run_models_parallel
from eval.fingerprints import evaluation_fingerprint, sha256_file
from eval.labels import build_samples
from eval.scoring import flicker, prediction_row, summarize

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = {
    "cloudy1": 3600.133,
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
    assert counts == {"cloudy1": 60, "cloudy_6": 45, "night_6": 60, "rainy_6": 75, "sunny_6": 105}

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


def test_prompt_levels() -> None:
    from eval.prompt import PROMPT_LEVELS, prompt_id, prompt_text_for_level, selected_prompt_levels

    assert PROMPT_LEVELS == (1, 2, 3, 4)
    assert selected_prompt_levels() == (1, 2, 3, 4)
    assert selected_prompt_levels(3) == (3,)
    level_1 = prompt_text_for_level(1)
    level_2 = prompt_text_for_level(2)
    # Levels 2, 3 and 4 share one prompt text. Level 1 has no advice.
    assert prompt_text_for_level(3) == prompt_text_for_level(4) == level_2
    assert prompt_id(level_1) != prompt_id(level_2)
    assert "Judge each state independently" in level_1
    assert "Judge each state independently" in level_2
    assert "nose wheel" in level_1 and "nose wheel" in level_2
    assert "physically and fully docked" in level_2
    assert "front or rear cargo hold" in level_2
    assert "rear hold" not in level_1
    for text in (level_1, level_2):
        for key in ("parked", "tunnel_attached", "doors_open", "description"):
            assert key in text
    try:
        prompt_text_for_level(5)
    except ValueError:
        pass
    else:
        raise AssertionError("level 5 should be rejected")


def test_example_sets_are_held_out_and_labelled_from_timestamps() -> None:
    from eval.few_shot import EXAMPLE_SETS, example_set_for_level
    from eval.labels import NEAR_BOUNDARY_SECONDS, parse_clock

    rows = {row["file_name"]: row for row in __import__("csv").DictReader(_timestamps().open())}
    bounds_by_video = {}
    boundaries_by_video = {}
    for video, row in rows.items():
        bounds = {}
        boundaries = []
        for state, start_key, end_key in (
            ("parked", "parked", "left_parking"),
            ("tunnel_attached", "tunnel_attached", "tunnel_detached"),
            ("doors_open", "doors_open", "doors_closed"),
        ):
            start = parse_clock(row[start_key])
            end = parse_clock(row[end_key])
            boundaries.append(start)
            # "end" means the state lasts until the video ends; that is not a change point.
            if end is not None:
                boundaries.append(end)
            bounds[state] = (start, DURATIONS[video] if end is None else end)
        bounds_by_video[video] = bounds
        boundaries_by_video[video] = boundaries
    grid_keys = {(sample.video, sample.timestamp_s) for sample in build_samples(_timestamps(), DURATIONS, 60)}

    for name, examples in EXAMPLE_SETS.items():
        seen = set()
        for example in examples:
            key = (example.video, example.timestamp_s)
            assert key not in seen, f"{name} repeats {key}"
            seen.add(key)
            if example.video != "cloudy1":
                # The older examples are off the 60 s grid.
                assert key not in grid_keys, f"{name} example {key} is on the sample grid"
                assert example.timestamp_s % 60 != 0
            assert example.timestamp_s + 1 < DURATIONS[example.video]
            for state, (start, end) in bounds_by_video[example.video].items():
                assert getattr(example, state) is (start <= example.timestamp_s < end), (name, example.example_id, state)
            if example.video != "cloudy1":
                distance = min(abs(example.timestamp_s - boundary) for boundary in boundaries_by_video[example.video])
                assert distance > NEAR_BOUNDARY_SECONDS, (name, example.example_id, distance)

    four_shot = EXAMPLE_SETS["4-shot"]
    assert len(four_shot) == 4
    assert [(e.parked, e.tunnel_attached, e.doors_open) for e in four_shot] == [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ]

    observed = {sample.phase for sample in build_samples(_timestamps(), DURATIONS, 1)}
    assert observed == {"empty", "parked", "parked+tunnel", "parked+doors", "parked+tunnel+doors"}
    six_shot = EXAMPLE_SETS["6-shot"]
    assert len(six_shot) == 6
    assert [(e.parked, e.tunnel_attached, e.doors_open) for e in six_shot] == [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
        (True, True, True),
        (True, False, False),
    ]

    assert example_set_for_level(1) is None
    assert example_set_for_level(2) is None
    assert example_set_for_level(3) == "4-shot"
    assert example_set_for_level(4) == "6-shot"


def test_parse_failure_counts_as_wrong_and_flicker_ignores_real_changes() -> None:
    timestamps = ROOT / "timestamps.csv"
    if not timestamps.exists():
        timestamps = ROOT / "others" / "timestamps.csv"
    samples = [
        sample
        for sample in build_samples(timestamps, DURATIONS, 60)
        if sample.video == "cloudy_6"
    ][:3]
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


def test_models_run_in_parallel_with_sequential_calls_per_model() -> None:
    models = ["model-a", "model-b", "model-c"]
    start = Barrier(len(models))
    lock = Lock()
    active_by_model = {model: 0 for model in models}
    max_active_by_model = {model: 0 for model in models}
    active_total = 0
    max_active_total = 0

    def run_model(model: str) -> str:
        nonlocal active_total, max_active_total
        start.wait(timeout=5)
        for _ in range(3):
            with lock:
                active_by_model[model] += 1
                active_total += 1
                max_active_by_model[model] = max(max_active_by_model[model], active_by_model[model])
                max_active_total = max(max_active_total, active_total)
            sleep(0.01)
            with lock:
                active_by_model[model] -= 1
                active_total -= 1
        return model

    assert run_models_parallel(models, run_model, max_concurrent_models=3) == [
        (model, model) for model in models
    ]
    assert max_active_total == len(models)
    assert max(max_active_by_model.values()) == 1


def test_model_concurrency_limit_is_respected() -> None:
    models = [f"model-{index}" for index in range(5)]
    lock = Lock()
    active = 0
    maximum_active = 0

    def run_model(model: str) -> str:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        sleep(0.02)
        with lock:
            active -= 1
        return model

    assert run_models_parallel(models, run_model, max_concurrent_models=2) == [
        (model, model) for model in models
    ]
    assert maximum_active == 2


def test_model_concurrency_limit_must_be_positive() -> None:
    try:
        run_models_parallel([], lambda model: model, max_concurrent_models=0)
    except ValueError as exc:
        assert "must be positive" in str(exc)
    else:
        raise AssertionError("zero model concurrency must be rejected")


def test_evaluation_fingerprint_changes_with_input_content() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        timestamps = root / "timestamps.csv"
        video = root / "sample.mp4"
        timestamps.write_bytes(b"timestamps-v1")
        video.write_bytes(b"video-v1")
        first, sources = evaluation_fingerprint(timestamps, [video])
        assert sources["videos"]["sample.mp4"] == sha256_file(video)

        video.write_bytes(b"video-v2")
        second, _sources = evaluation_fingerprint(timestamps, [video])
        assert second != first


if __name__ == "__main__":
    test_grid_and_states()
    test_prompt_levels()
    test_example_sets_are_held_out_and_labelled_from_timestamps()
    test_parse_failure_counts_as_wrong_and_flicker_ignores_real_changes()
    test_cost_uses_cached_input_rate_and_both_usage_shapes()
    test_models_run_in_parallel_with_sequential_calls_per_model()
    test_model_concurrency_limit_is_respected()
    test_model_concurrency_limit_must_be_positive()
    test_evaluation_fingerprint_changes_with_input_content()
    print("label checks passed")
