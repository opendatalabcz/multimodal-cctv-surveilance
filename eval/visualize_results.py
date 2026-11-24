"""Create accuracy comparisons and confusion matrices from evaluation reports."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from eval.prompt import PROMPT_LEVELS
from eval.scoring import STATES

STATE_TITLES = {
    "parked": "Parked",
    "tunnel_attached": "Tunnel attached",
    "doors_open": "Door(s) open",
}
STATE_CMAPS = {
    "all": "Blues",
    "parked": "Greens",
    "tunnel_attached": "Purples",
    "doors_open": "Reds",
}
ACCURACY_METRICS = (
    ("Exact match", None),
    ("Parked accuracy", "parked"),
    ("Tunnel attached accuracy", "tunnel_attached"),
    ("Door(s) open accuracy", "doors_open"),
)

ConfusionMatrix = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class Report:
    path: Path
    interval_seconds: int
    prompt_level: int
    model_level: str
    models: dict[str, dict[str, Any]]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_reports(reports_dir: Path) -> list[Report]:
    paths = sorted(reports_dir.glob("report_level*_*.json"))
    if not paths:
        raise FileNotFoundError(f"No report_level*_*.json files found in {reports_dir}")

    reports = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read report {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Report {path} must contain a JSON object")

        interval = _report_integer(data, "interval_seconds", path)
        level = _report_integer(data, "prompt_level", path)
        model_level = data.get("model_level")
        models = data.get("models")
        if interval <= 0:
            raise ValueError(f"Report {path} has a non-positive interval_seconds")
        if level not in PROMPT_LEVELS:
            raise ValueError(f"Report {path} has an unsupported prompt_level: {level}")
        if not isinstance(model_level, str) or not model_level:
            raise ValueError(f"Report {path} is missing a valid model_level")
        if not isinstance(models, dict) or not all(isinstance(name, str) for name in models):
            raise ValueError(f"Report {path} is missing a valid models object")
        reports.append(
            Report(
                path=path,
                interval_seconds=interval,
                prompt_level=level,
                model_level=model_level,
                models=models,
            )
        )
    return reports


def _report_integer(data: dict[str, Any], key: str, path: Path) -> int:
    value = data.get(key)
    if type(value) is not int:
        raise ValueError(f"Report {path} is missing a valid {key}")
    return value


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unnamed"


def create_accuracy_plots(reports: list[Report], output_dir: Path) -> list[Path]:
    groups: dict[tuple[int, str], list[Report]] = {}
    for report in reports:
        groups.setdefault((report.interval_seconds, report.model_level), []).append(report)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for (interval, model_level), group in sorted(groups.items()):
        by_level = {report.prompt_level: report for report in group}
        if len(by_level) != len(group):
            raise ValueError(
                f"Multiple reports found for interval {interval}s, model level {model_level}, "
                "and the same prompt level"
            )
        levels = sorted(by_level)
        models = sorted({model for report in group for model in report.models})
        if not models:
            raise ValueError(f"Reports for interval {interval}s, model level {model_level} have no models")

        fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
        try:
            for index, (axis, (title, state)) in enumerate(zip(axes.flat, ACCURACY_METRICS)):
                for model in models:
                    values = []
                    for level in levels:
                        summary = by_level[level].models.get(model)
                        if summary is None:
                            values.append(float("nan"))
                        else:
                            values.append(_accuracy(summary, state, by_level[level].path, model))
                    axis.plot(levels, values, marker="o", linewidth=1.8, label=model)
                axis.set_title(title)
                axis.set_xlabel("Prompt level" if index >= 2 else "")
                axis.set_ylabel("Accuracy")
                axis.set_xticks(levels)
                axis.set_ylim(0, 1)
                axis.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
                axis.grid(True, alpha=0.25)

            fig.suptitle(f"Accuracy by prompt level | every {interval}s | {model_level} models")
            handles, labels = axes.flat[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", ncol=min(4, len(models)), frameon=False)
            fig.tight_layout(rect=(0, 0.1, 1, 0.94))
            path = output_dir / f"accuracy_interval{interval}s_{_slug(model_level)}.png"
            fig.savefig(path, dpi=160, bbox_inches="tight")
        finally:
            plt.close(fig)
        paths.append(path)
    return paths


def _accuracy(summary: dict[str, Any], state: str | None, path: Path, model: str) -> float:
    overall = summary.get("overall")
    if not isinstance(overall, dict):
        raise ValueError(f"Report {path} has no overall metrics for {model}")
    value: Any
    if state is None:
        value = overall.get("exact_match")
    else:
        states = overall.get("states")
        state_metrics = states.get(state) if isinstance(states, dict) else None
        value = state_metrics.get("accuracy") if isinstance(state_metrics, dict) else None
    if value is None:
        return float("nan")
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"Report {path} has an invalid accuracy for {model} ({state or 'exact_match'})")
    return float(value)


def confusion_matrices(overall: dict[str, Any]) -> dict[str, ConfusionMatrix]:
    states = overall.get("states")
    if not isinstance(states, dict):
        raise ValueError("Overall metrics have no per-state confusion counts")

    matrices = {
        state: _state_confusion_matrix(states.get(state), state)
        for state in STATES
    }
    combined = tuple(
        tuple(sum(matrix[row][column] for matrix in matrices.values()) for column in range(2))
        for row in range(2)
    )
    return {"all": combined, **matrices}


def _state_confusion_matrix(metrics: Any, state: str) -> ConfusionMatrix:
    if not isinstance(metrics, dict):
        raise ValueError(f"Missing confusion counts for state {state}")
    tp = _count(metrics, "true_positive", state)
    fn = _count(metrics, "false_negative", state)
    fp = _count(metrics, "false_positive", state)
    tn = _count(metrics, "true_negative", state)
    return ((tp, fn), (fp, tn))


def _count(metrics: dict[str, Any], key: str, state: str) -> int:
    value = metrics.get(key)
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {key} confusion count for state {state}")
    return value


def find_report(
    reports: list[Report],
    *,
    model: str,
    prompt_level: int,
    model_level: str | None = None,
    interval_seconds: int | None = None,
) -> Report:
    matches = [
        report
        for report in reports
        if report.prompt_level == prompt_level
        and model in report.models
        and (model_level is None or report.model_level == model_level)
        and (interval_seconds is None or report.interval_seconds == interval_seconds)
    ]
    if not matches:
        raise ValueError(
            f"No report found for model {model}, prompt level {prompt_level}"
            + (f", model level {model_level}" if model_level else "")
            + (f", interval {interval_seconds}s" if interval_seconds else "")
        )
    if len(matches) > 1:
        choices = ", ".join(
            f"{report.model_level}/{report.interval_seconds}s" for report in matches
        )
        raise ValueError(f"Multiple reports match; specify --model-level and/or --interval-seconds: {choices}")
    return matches[0]


def create_confusion_plots(report: Report, model: str, output_dir: Path) -> list[Path]:
    summary = report.models[model]
    overall = summary.get("overall")
    if not isinstance(overall, dict):
        raise ValueError(f"Report {report.path} has no overall metrics for {model}")
    matrices = confusion_matrices(overall)
    parse_failures = _count(overall, "parse_failures", "overall")

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ("all", *STATES):
        path = output_dir / (
            f"confusion_{_slug(model)}_level{report.prompt_level}_"
            f"{_slug(report.model_level)}_interval{report.interval_seconds}s_{name}.png"
        )
        _draw_confusion_matrix(
            matrices[name],
            title="Confusion Matrix" if name == "all" else STATE_TITLES[name],
            cmap=STATE_CMAPS[name],
            model=model,
            prompt_level=report.prompt_level,
            parse_failures=parse_failures,
            path=path,
        )
        paths.append(path)
    return paths


def _draw_confusion_matrix(
    matrix: ConfusionMatrix,
    *,
    title: str,
    cmap: str,
    model: str,
    prompt_level: int,
    parse_failures: int,
    path: Path,
) -> None:
    maximum = max(max(row) for row in matrix)
    vmax = max(1, maximum)
    fig, axis = plt.subplots(figsize=(7, 6))
    try:
        image = axis.imshow(matrix, cmap=cmap, interpolation="nearest", vmin=0, vmax=vmax)
        fig.colorbar(image, ax=axis)
        axis.set(
            xticks=[0, 1],
            yticks=[0, 1],
            xlabel="Predicted label",
            ylabel="True label",
            title=title,
        )
        axis.set_xticklabels(["Yes", "No"], rotation=35, ha="right")
        axis.set_yticklabels(["Yes", "No"])
        threshold = maximum * 0.55
        for row in range(2):
            for column in range(2):
                value = matrix[row][column]
                color = "white" if value > threshold and maximum else "black"
                axis.text(column, row, f"{value}", ha="center", va="center", color=color, fontsize=18)
        fig.suptitle(f"{model} | prompt level {prompt_level}")
        fig.text(0.5, 0.02, f"Parse failures excluded: {parse_failures}", ha="center")
        fig.tight_layout(rect=(0, 0.06, 1, 0.93))
        fig.savefig(path, dpi=160, bbox_inches="tight")
    finally:
        plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot evaluation reports without making model or Langfuse requests.")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=project_root() / "outputs" / "vlm_eval",
        help="Directory containing report_level{n}_{model_level}.json files.",
    )
    parser.add_argument("--output-dir", type=Path, help="PNG destination (default: <reports-dir>/plots).")
    parser.add_argument("--model-level", help="Limit plots and matrix selection to a model tier, e.g. default or mid.")
    parser.add_argument("--interval-seconds", type=int, help="Limit plots and matrix selection to this sample interval.")
    parser.add_argument("--model", help="Generate confusion matrices for this model; requires --prompt-level.")
    parser.add_argument("--prompt-level", type=int, choices=PROMPT_LEVELS, help="Prompt level for confusion matrices.")
    args = parser.parse_args(argv)
    if (args.model is None) != (args.prompt_level is None):
        parser.error("--model and --prompt-level must be provided together")
    if args.interval_seconds is not None and args.interval_seconds <= 0:
        parser.error("--interval-seconds must be positive")

    try:
        reports = load_reports(args.reports_dir)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    selected = [
        report
        for report in reports
        if (args.model_level is None or report.model_level == args.model_level)
        and (args.interval_seconds is None or report.interval_seconds == args.interval_seconds)
    ]
    if not selected:
        parser.error("No reports match the selected model level and interval")

    output_dir = args.output_dir or args.reports_dir / "plots"
    accuracy_paths = create_accuracy_plots(selected, output_dir)
    for path in accuracy_paths:
        print(f"Accuracy plot: {path}")
    if args.model is not None and args.prompt_level is not None:
        try:
            report = find_report(
                selected,
                model=args.model,
                prompt_level=args.prompt_level,
                model_level=args.model_level,
                interval_seconds=args.interval_seconds,
            )
            confusion_paths = create_confusion_plots(report, args.model, output_dir)
        except ValueError as exc:
            parser.error(str(exc))
        for path in confusion_paths:
            print(f"Confusion matrix: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
