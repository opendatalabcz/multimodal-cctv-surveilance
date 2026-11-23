import csv
import json
from pathlib import Path

import pytest

from cctv.eval.charts import SUMMARY_NAME, write_charts
from cctv.eval.cli import main

RUN_A = "2026-11-20T100000"
RUN_B = "2026-11-21T100000"
SINGLE_RUN_FILES = {
    "duration.png",
    "duration_per_call.png",
    "tokens.png",
    "model_calls.png",
    "retrieval.png",
    "selection.png",
    "correctness.png",
    SUMMARY_NAME,
}


def _result(
    run_dir: Path,
    model: str,
    verbosity: str | None,
    question: str,
    **fields,
) -> None:
    folder = run_dir / model
    if verbosity is not None:
        folder = folder / verbosity
    folder = folder / question
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "question_id": question,
        "model": model,
        "verbosity_folder": verbosity,
        "success": True,
        "duration_ms": 1000,
        "model_calls": 2,
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        "requested_camera_ids": ["a", "b"],
        "fetched_camera_ids": ["a", "b"],
        "shown_camera_ids": ["a"],
        "expected_camera_ids": ["a", "b"],
        **fields,
    }
    (folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")


def _summary(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {(row["model"], row["verbosity"]): row for row in csv.DictReader(handle)}


def _charts(roots: list[Path], out_dir: Path) -> list[Path]:
    # questions=[] and a resolver that knows no camera keep the test off the shipped config.
    return write_charts(roots, out_dir, questions=[], resolve=lambda _query: None)


def test_one_run_writes_charts_and_a_summary(tmp_path: Path) -> None:
    run = tmp_path / RUN_A
    _result(run, "gpt-4o", None, "walk", duration_ms=1000)
    _result(
        run,
        "gpt-4o",
        None,
        "traffic",
        duration_ms=3000,
        usage={"prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340},
    )
    # A failed case is left out of the charts but counted in the summary.
    _result(run, "gpt-4o", None, "airports", success=False, duration_ms=99999, error="boom")

    written = _charts([run], run / "charts")

    assert {path.name for path in written} == SINGLE_RUN_FILES
    assert all(path.stat().st_size > 0 for path in written)
    row = _summary(run / "charts" / SUMMARY_NAME)[("gpt-4o", "")]
    assert (row["runs"], row["n"], row["failed"]) == ("1", "2", "1")
    assert row["median_duration_ms"] == "2000.0"
    # prompt_tokens and completion_tokens count the same as input and output tokens.
    assert row["mean_input_tokens"] == "200.0"
    assert row["mean_output_tokens"] == "30.0"
    assert row["median_ms_per_call"] == "1000.0"


def test_pooled_runs_add_the_cross_run_chart(tmp_path: Path) -> None:
    run_a = tmp_path / RUN_A
    run_b = tmp_path / RUN_B
    _result(
        run_a,
        "gpt-5.6-luna",
        "low",
        "walk",
        usage={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
    )
    _result(run_b, "gpt-5.6-luna", "low", "walk", duration_ms=3000)
    _result(run_b, "qwen/qwen3.8-flash", None, "walk")

    written = _charts([run_a, run_b], tmp_path / "charts")

    assert {path.name for path in written} == SINGLE_RUN_FILES | {"duration_by_run.png"}
    rows = _summary(tmp_path / "charts" / SUMMARY_NAME)
    luna = rows[("gpt-5.6-luna", "low")]
    assert (luna["runs"], luna["n"]) == ("2", "2")
    assert luna["median_duration_ms"] == "2000.0"
    # Azure token names and chat-completions token names are pooled together.
    assert luna["mean_input_tokens"] == "75.0"
    assert rows[("qwen/qwen3.8-flash", "")]["runs"] == "1"


def test_retrieval_and_manual_scores_reach_the_summary(tmp_path: Path) -> None:
    run = tmp_path / RUN_A
    _result(run, "gpt-4o", None, "walk", requested_camera_ids=["a", "ghost"], fetched_camera_ids=["a"])
    with (run / "grading.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "verbosity", "question_id", "correctness_1_to_5", "clarity_1_to_5"])
        writer.writerow(["gpt-4o", "", "walk", "4", "5"])

    _charts([run], run / "charts")

    row = _summary(run / "charts" / SUMMARY_NAME)[("gpt-4o", "")]
    # Tried {a, ghost} against expected {a, b}: half were right, half of the expected were tried.
    assert row["mean_retrieval_precision"] == "0.5"
    assert row["mean_retrieval_recall"] == "0.5"
    assert (row["n_scored"], row["mean_correctness"], row["mean_clarity"]) == ("1", "4.0", "5.0")


def test_no_successful_case_is_an_error(tmp_path: Path) -> None:
    run = tmp_path / RUN_A
    _result(run, "gpt-4o", None, "walk", success=False, error="boom")

    with pytest.raises(ValueError, match="No successful results"):
        _charts([run], run / "charts")


def test_cli_writes_one_run_into_its_charts_folder(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "end_to_end_eval"
    _result(root / RUN_A, "gpt-4o", None, "walk")
    _result(root / RUN_B, "gpt-4o", None, "walk")
    monkeypatch.setattr("cctv.eval.cli.default_output_dir", lambda: root)

    assert main(["--charts"]) == 0

    assert (root / RUN_B / "charts" / SUMMARY_NAME).is_file()
    assert not (root / RUN_A / "charts").exists()
    assert main(["--charts", "--run", RUN_A]) == 0
    assert (root / RUN_A / "charts" / SUMMARY_NAME).is_file()


def test_cli_all_runs_writes_outside_the_run_folder(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "end_to_end_eval"
    _result(root / RUN_A, "gpt-4o", None, "walk")
    _result(root / RUN_B, "gpt-4o", None, "walk")
    monkeypatch.setattr("cctv.eval.cli.default_output_dir", lambda: root)

    assert main(["--charts", "--all-runs"]) == 0

    assert (tmp_path / "charts" / "duration_by_run.png").is_file()
    # A folder inside end_to_end_eval that is not a run id would be mistaken for old results.
    assert not (root / "charts").exists()
    assert _summary(tmp_path / "charts" / SUMMARY_NAME)[("gpt-4o", "")]["runs"] == "2"


@pytest.mark.parametrize(
    "args",
    [
        ["--all-runs"],
        ["--charts", "--all-runs", "--run", RUN_A],
        ["--charts", "--report"],
        ["--charts", "--run", "missing"],
    ],
)
def test_cli_rejects_bad_chart_options(tmp_path: Path, monkeypatch, args: list[str]) -> None:
    root = tmp_path / "end_to_end_eval"
    _result(root / RUN_A, "gpt-4o", None, "walk")
    monkeypatch.setattr("cctv.eval.cli.default_output_dir", lambda: root)

    assert main(args) == 2
