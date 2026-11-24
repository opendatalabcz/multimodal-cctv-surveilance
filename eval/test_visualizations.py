"""Checks for report plots. Run with python -m eval.test_visualizations."""

import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from eval.visualize_results import (
    Report,
    confusion_matrices,
    create_accuracy_plots,
    create_confusion_plots,
    load_reports,
    main,
)


def _state_counts(tp: int, fn: int, fp: int, tn: int) -> dict:
    return {
        "true_positive": tp,
        "false_negative": fn,
        "false_positive": fp,
        "true_negative": tn,
    }


def _summary(accuracy: float) -> dict:
    return {
        "overall": {
            "n": 10,
            "parse_failures": 1,
            "exact_match": accuracy,
            "states": {
                "parked": {"accuracy": accuracy, **_state_counts(7, 2, 3, 11)},
                "tunnel_attached": {"accuracy": accuracy, **_state_counts(5, 1, 4, 12)},
                "doors_open": {"accuracy": accuracy, **_state_counts(3, 5, 2, 10)},
            },
        }
    }


def _report(level: int, tier: str, models: dict[str, dict]) -> Report:
    return Report(
        path=Path(f"report_level{level}_{tier}.json"),
        interval_seconds=60,
        prompt_level=level,
        model_level=tier,
        models=models,
    )


def test_combined_confusion_matrix_sums_state_decisions() -> None:
    matrices = confusion_matrices(_summary(0.8)["overall"])
    assert matrices["parked"] == ((7, 2), (3, 11))
    assert matrices["tunnel_attached"] == ((5, 1), (4, 12))
    assert matrices["doors_open"] == ((3, 5), (2, 10))
    assert matrices["all"] == ((15, 8), (9, 33))


def test_accuracy_and_confusion_plots_are_written_as_pngs() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        reports_dir = root / "reports"
        reports_dir.mkdir()
        report_data = (
            (1, "default", {"model-a": _summary(0.7), "model-b": _summary(0.8)}),
            (2, "default", {"model-a": _summary(0.85), "model-b": _summary(0.9)}),
            (1, "mid", {"model-a": _summary(0.75)}),
        )
        for level, tier, models in report_data:
            path = reports_dir / f"report_level{level}_{tier}.json"
            path.write_text(
                json.dumps(
                    {
                        "interval_seconds": 60,
                        "prompt_level": level,
                        "model_level": tier,
                        "models": models,
                    }
                ),
                encoding="utf-8",
            )
        reports = load_reports(reports_dir)
        assert len(reports) == 3

        output_dir = root / "plots"
        accuracy_paths = create_accuracy_plots(reports, output_dir)
        assert len(accuracy_paths) == 2
        assert all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in accuracy_paths)

        matrix_paths = create_confusion_plots(reports[0], "model-a", output_dir)
        assert len(matrix_paths) == 4
        assert all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in matrix_paths)

        with contextlib.redirect_stdout(io.StringIO()):
            assert main(
                [
                    "--reports-dir",
                    str(reports_dir),
                    "--output-dir",
                    str(output_dir),
                    "--model-level",
                    "default",
                    "--model",
                    "model-a",
                    "--prompt-level",
                    "1",
                ]
            ) == 0


if __name__ == "__main__":
    test_combined_confusion_matrix_sums_state_decisions()
    test_accuracy_and_confusion_plots_are_written_as_pngs()
    print("visualization checks passed")
