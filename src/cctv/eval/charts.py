"""Charts and a summary table for the end-to-end evaluation.

Reads the same rows as ``grading.csv`` (``report.load_rows``) for one run or for
several runs pooled together, and writes PNG charts plus ``summary.csv``. Only
successful cases are charted; failed ones are counted in the summary. No model
is called.

One color and one position per model and verbosity are used in every chart, so a
bar can be followed from chart to chart. A model with no verbosity setting is
labeled "default".
"""

from __future__ import annotations

import csv
import math
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cctv.eval.questions import EvalQuestion
from cctv.eval.report import CameraResolver, load_rows

# About one LaTeX text width, in inches.
FIGURE_WIDTH = 6.5
SUMMARY_NAME = "summary.csv"
VERBOSITY_ORDER = ["low", "medium", "high"]
# Lighter for low verbosity so levels of one model read as one family.
_VERBOSITY_SHADE = {"low": 0.55, "medium": 0.78, "high": 1.0, "": 1.0}

GroupKey = tuple[str, str]

SUMMARY_COLUMNS = [
    "model",
    "verbosity",
    "runs",
    "n",
    "failed",
    "median_duration_ms",
    "median_ms_per_call",
    "mean_model_calls",
    "mean_input_tokens",
    "mean_output_tokens",
    "mean_total_tokens",
    "mean_retrieval_precision",
    "mean_retrieval_recall",
    "mean_selection_precision",
    "mean_selection_recall",
    "n_scored",
    "mean_correctness",
    "mean_clarity",
]


class ChartsUnavailable(RuntimeError):
    """matplotlib is not installed."""


def write_charts(
    roots: Sequence[Path],
    out_dir: Path,
    *,
    model_order: Sequence[str] | None = None,
    questions: list[EvalQuestion] | None = None,
    resolve: CameraResolver | None = None,
) -> list[Path]:
    """Write the charts and ``summary.csv`` into ``out_dir``. Returns the files written.

    ``roots`` are run folders. Two or more are pooled, and the cross-run chart is
    added. ``model_order`` fixes the left-to-right order, for example the catalog
    order, so Azure models come before OpenRouter ones.
    """
    plt = _pyplot()
    run_roots = list(roots)
    rows, _ = load_rows(run_roots, questions, resolve=resolve)
    done = [row for row in rows if row.get("success") is True]
    if not done:
        raise ValueError("No successful results to chart.")
    pooled = len(run_roots) > 1
    order = {model: index for index, model in enumerate(model_order or [])}
    keys = _ordered_keys(rows, order)
    by_group = {key: [row for row in done if _key(row) == key] for key in keys}
    failed = {key: sum(1 for row in rows if _key(row) == key) - len(by_group[key]) for key in keys}
    labels = [_label(key, by_group[key], pooled) for key in keys]
    colors = [_group_color(plt, key, order) for key in keys]
    scope = f"{len(run_roots)} runs pooled" if pooled else f"run {run_roots[0].name}"
    runs = sorted({str(row["run"]) for row in done})

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    style = {"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8}
    with plt.rc_context(style):
        written.append(
            _strip_chart(
                plt,
                out_dir / "duration.png",
                labels,
                [_dots(by_group[key], lambda row: _number(row.get("duration_ms"))) for key in keys],
                runs,
                ylabel="Duration per case (ms)",
                title=f"Duration per case\n{scope}",
            )
        )
        written.append(
            _strip_chart(
                plt,
                out_dir / "duration_per_call.png",
                labels,
                [_dots(by_group[key], _ms_per_call) for key in keys],
                runs,
                ylabel="Duration per model call (ms)",
                title=f"Duration per model call\n{scope}",
            )
        )
        written.append(
            _bar_chart(
                plt,
                out_dir / "tokens.png",
                labels,
                [
                    ("Input", [_mean(by_group[key], "input_tokens") for key in keys], "#4c78a8"),
                    ("Output", [_mean(by_group[key], "output_tokens") for key in keys], "#f58518"),
                ],
                ylabel="Mean tokens per case",
                title=f"Tokens per case (input plus output)\n{scope}",
                stacked=True,
                fmt="%.0f",
            )
        )
        written.append(
            _bar_chart(
                plt,
                out_dir / "model_calls.png",
                labels,
                [("Model calls", [_mean(by_group[key], "model_calls") for key in keys], colors)],
                ylabel="Mean model calls per case",
                title=f"Model calls per case\n{scope}",
                fmt="%.1f",
            )
        )
        written.append(
            _bar_chart(
                plt,
                out_dir / "retrieval.png",
                labels,
                _precision_recall_series(by_group, keys, "retrieval"),
                ylabel="Mean score",
                title=f"Retrieval: cameras the model tried vs expected cameras\n{scope}",
                ylim=(0, 1.1),
                note="Tried = requested plus fetched. Expected lists are hand-written, not ground truth.",
            )
        )
        written.append(
            _bar_chart(
                plt,
                out_dir / "selection.png",
                labels,
                _precision_recall_series(by_group, keys, "selection"),
                ylabel="Mean score",
                title=f"Selection: cameras shown in the answer vs expected cameras\n{scope}",
                ylim=(0, 1.1),
                note="Cameras that returned a placeholder image lower these scores when left out.",
            )
        )
        written.append(
            _bar_chart(
                plt,
                out_dir / "correctness.png",
                labels,
                [
                    ("Correctness", [_mean(by_group[key], "correctness_1_to_5") for key in keys], "#54a24b"),
                    ("Clarity", [_mean(by_group[key], "clarity_1_to_5") for key in keys], "#b279a2"),
                ],
                ylabel="Mean score (1 to 5)",
                title=f"Manual scores\n{scope}",
                ylim=(0, 5.5),
                empty_note=(
                    "No manual scores yet.\nFill in correctness_1_to_5 and clarity_1_to_5 in grading.csv."
                ),
            )
        )
        if pooled:
            written.append(
                _runs_chart(
                    plt,
                    out_dir / "duration_by_run.png",
                    keys,
                    by_group,
                    labels,
                    colors,
                    runs,
                    title="Median duration per run, one line per model",
                )
            )
    written.append(_write_summary(out_dir / SUMMARY_NAME, keys, by_group, failed))
    return written


def _pyplot() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ChartsUnavailable(
            "matplotlib is not installed. Run `make install_dev` first."
        ) from exc
    return plt


def _key(row: dict[str, Any]) -> GroupKey:
    return (str(row["model"]), str(row["verbosity"]))


def _ordered_keys(rows: list[dict[str, Any]], order: dict[str, int]) -> list[GroupKey]:
    keys = {_key(row) for row in rows}

    def sort_key(key: GroupKey) -> tuple[int, str, int]:
        model, verbosity = key
        verbosity_rank = (
            VERBOSITY_ORDER.index(verbosity) if verbosity in VERBOSITY_ORDER else len(VERBOSITY_ORDER)
        )
        return (order.get(model, len(order)), model, verbosity_rank)

    return sorted(keys, key=sort_key)


def _label(key: GroupKey, rows: list[dict[str, Any]], pooled: bool) -> str:
    model, verbosity = key
    runs = len({row["run"] for row in rows})
    detail = f"n={len(rows)}"
    if pooled and runs == 1:
        detail += ", 1 run"
    return f"{model.split('/')[-1]} {verbosity or 'default'} ({detail})"


def _group_color(plt: Any, key: GroupKey, order: dict[str, int]) -> tuple[float, float, float]:
    model, verbosity = key
    palette = plt.get_cmap("tab10")
    index = order.get(model, len(order) + sum(ord(char) for char in model))
    red, green, blue = palette(index % 10)[:3]
    shade = _VERBOSITY_SHADE.get(verbosity, 1.0)
    return tuple(channel * shade + (1 - shade) for channel in (red, green, blue))  # type: ignore[return-value]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _ms_per_call(row: dict[str, Any]) -> float | None:
    duration = _number(row.get("duration_ms"))
    calls = _number(row.get("model_calls"))
    if duration is None or not calls:
        return None
    return duration / calls


def _dots(rows: list[dict[str, Any]], value: Any) -> list[tuple[str, float]]:
    dots: list[tuple[str, float]] = []
    for row in rows:
        number = value(row)
        if number is not None:
            dots.append((str(row["run"]), number))
    return dots


def _values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [number for number in (_number(row.get(field)) for row in rows) if number is not None]


def _mean(rows: list[dict[str, Any]], field: str) -> float:
    values = _values(rows, field)
    return statistics.fmean(values) if values else math.nan


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def _precision_recall_series(
    by_group: dict[GroupKey, list[dict[str, Any]]],
    keys: list[GroupKey],
    prefix: str,
) -> list[tuple[str, list[float], Any]]:
    return [
        ("Precision", [_mean(by_group[key], f"{prefix}_precision") for key in keys], "#4c78a8"),
        ("Recall", [_mean(by_group[key], f"{prefix}_recall") for key in keys], "#f58518"),
    ]


def _strip_chart(
    plt: Any,
    path: Path,
    labels: list[str],
    dots: list[list[tuple[str, float]]],
    runs: list[str],
    *,
    ylabel: str,
    title: str,
) -> Path:
    from matplotlib.lines import Line2D

    figure, axes = plt.subplots(figsize=(FIGURE_WIDTH, 3.9))
    palette = plt.get_cmap("viridis")
    run_color = {
        run: palette(index / max(1, len(runs) - 1) * 0.9) for index, run in enumerate(runs)
    }
    for position, group in enumerate(dots):
        for index, (run, value) in enumerate(group):
            # A fixed pattern keeps the picture the same on every run of the command.
            jitter = ((index * 37) % 11 - 5) * 0.035
            axes.scatter(position + jitter, value, s=14, color=run_color[run], alpha=0.85, zorder=3)
        if group:
            median = _median([value for _, value in group])
            axes.hlines(median, position - 0.32, position + 0.32, color="black", linewidth=2, zorder=4)
    handles = [Line2D([], [], color="black", linewidth=2, label="median")]
    if len(runs) > 1:
        handles += [
            Line2D([], [], marker="o", linestyle="", color=run_color[run], label=run, markersize=4)
            for run in runs
        ]
    axes.legend(handles=handles, fontsize=6, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    axes.set_ylabel(ylabel)
    axes.set_title(title)
    axes.set_ylim(bottom=0)
    _style_axes(axes, labels)
    return _save(plt, figure, path)


def _bar_chart(
    plt: Any,
    path: Path,
    labels: list[str],
    series: list[tuple[str, list[float], Any]],
    *,
    ylabel: str,
    title: str,
    ylim: tuple[float, float] | None = None,
    stacked: bool = False,
    fmt: str = "%.2f",
    note: str | None = None,
    empty_note: str | None = None,
) -> Path:
    figure, axes = plt.subplots(figsize=(FIGURE_WIDTH, 3.9))
    positions = list(range(len(labels)))
    all_missing = all(math.isnan(value) for _, values, _ in series for value in values)
    width = 0.8 if stacked or len(series) == 1 else 0.8 / len(series)
    bottoms = [0.0] * len(labels)
    for index, (name, values, color) in enumerate(series):
        heights = [0.0 if math.isnan(value) else value for value in values]
        offset = 0.0 if stacked or len(series) == 1 else (index - (len(series) - 1) / 2) * width
        container = axes.bar(
            [position + offset for position in positions],
            heights,
            width,
            bottom=bottoms if stacked else None,
            color=color,
            label=name if len(series) > 1 else None,
        )
        if stacked:
            bottoms = [bottom + height for bottom, height in zip(bottoms, heights, strict=True)]
            # Segment labels collide on a stack, so only the total is written, once.
            if index == len(series) - 1:
                axes.bar_label(
                    container,
                    labels=[
                        ""
                        if all(math.isnan(values_[position]) for _, values_, _ in series)
                        else fmt % total
                        for position, total in enumerate(bottoms)
                    ],
                    fontsize=6,
                    padding=1,
                )
        else:
            axes.bar_label(
                container,
                labels=["" if math.isnan(value) else fmt % value for value in values],
                fontsize=6,
                padding=1,
            )
    if len(series) > 1:
        axes.legend(fontsize=7)
    if all_missing and empty_note:
        axes.text(
            0.5,
            0.5,
            empty_note,
            transform=axes.transAxes,
            ha="center",
            va="center",
            color="dimgray",
        )
    axes.set_ylabel(ylabel)
    axes.set_title(title)
    if ylim is not None:
        axes.set_ylim(*ylim)
    _style_axes(axes, labels, note)
    return _save(plt, figure, path)


def _runs_chart(
    plt: Any,
    path: Path,
    keys: list[GroupKey],
    by_group: dict[GroupKey, list[dict[str, Any]]],
    labels: list[str],
    colors: list[Any],
    runs: list[str],
    *,
    title: str,
) -> Path:
    figure, axes = plt.subplots(figsize=(FIGURE_WIDTH, 3.9))
    for key, label, color in zip(keys, labels, colors, strict=True):
        points: list[tuple[int, float]] = []
        for index, run in enumerate(runs):
            values = _values([row for row in by_group[key] if row["run"] == run], "duration_ms")
            if values:
                points.append((index, _median(values)))
        if points:
            axes.plot(
                [index for index, _ in points],
                [value for _, value in points],
                marker="o",
                markersize=3,
                linewidth=1,
                color=color,
                label=label,
            )
    axes.set_xticks(range(len(runs)))
    axes.set_xticklabels(runs, rotation=35, ha="right", fontsize=7)
    axes.set_ylabel("Median duration (ms)")
    axes.set_title(title)
    axes.set_ylim(bottom=0)
    axes.legend(fontsize=6, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    axes.set_xlabel(
        "A line covers only the runs in which that model appears.", fontsize=6, color="dimgray"
    )
    axes.grid(axis="y", alpha=0.25)
    return _save(plt, figure, path)


def _style_axes(axes: Any, labels: list[str], note: str | None = None) -> None:
    axes.set_xticks(range(len(labels)))
    axes.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
    axes.grid(axis="y", alpha=0.25)
    axes.set_axisbelow(True)
    if note:
        axes.set_xlabel(note, fontsize=6, color="dimgray")


def _save(plt: Any, figure: Any, path: Path) -> Path:
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return path


def _write_summary(
    path: Path,
    keys: list[GroupKey],
    by_group: dict[GroupKey, list[dict[str, Any]]],
    failed: dict[GroupKey, int],
) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for key in keys:
            group = by_group[key]
            per_call = [value for value in (_ms_per_call(row) for row in group) if value is not None]
            writer.writerow(
                {
                    "model": key[0],
                    "verbosity": key[1],
                    "runs": len({row["run"] for row in group}),
                    "n": len(group),
                    "failed": failed[key],
                    "median_duration_ms": _cell(_median(_values(group, "duration_ms"))),
                    "median_ms_per_call": _cell(_median(per_call)),
                    "mean_model_calls": _cell(_mean(group, "model_calls")),
                    "mean_input_tokens": _cell(_mean(group, "input_tokens")),
                    "mean_output_tokens": _cell(_mean(group, "output_tokens")),
                    "mean_total_tokens": _cell(_mean(group, "total_tokens")),
                    "mean_retrieval_precision": _cell(_mean(group, "retrieval_precision")),
                    "mean_retrieval_recall": _cell(_mean(group, "retrieval_recall")),
                    "mean_selection_precision": _cell(_mean(group, "selection_precision")),
                    "mean_selection_recall": _cell(_mean(group, "selection_recall")),
                    "n_scored": len(_values(group, "correctness_1_to_5")),
                    "mean_correctness": _cell(_mean(group, "correctness_1_to_5")),
                    "mean_clarity": _cell(_mean(group, "clarity_1_to_5")),
                }
            )
    return path


def _cell(value: float) -> float | str:
    return "" if math.isnan(value) else round(value, 2)
