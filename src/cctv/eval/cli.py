from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cctv.config.agent_yaml import load_agent_config
from cctv.eval.charts import ChartsUnavailable, write_charts
from cctv.eval.report import write_grading_sheet
from cctv.eval.runner import (
    default_output_dir,
    list_run_dirs,
    open_eval_run,
    resolve_run_dir,
    run_eval,
)
from cctv.utils.paths import project_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask each evaluation question once per model and verbosity.",
    )
    parser.add_argument("--model", help="Catalog model id. Default: every enabled model.")
    parser.add_argument("--verbosity", help="One verbosity level. Default: every level the model allows.")
    parser.add_argument("--question", help="Question id from configs/eval_questions.yaml.")
    parser.add_argument(
        "--run",
        help="Continue this run id (for example 2026-11-17T113445). Default: start a new run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace finished questions in the run given by --run.",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Also save a UI screenshot. Needs make up, and asks the question again in the browser.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Rewrite grading.csv for one run. Default: the latest run. No model calls.",
    )
    parser.add_argument(
        "--charts",
        action="store_true",
        help=(
            "Write PNG charts and summary.csv into charts/ in one run folder "
            "(default: the latest; see --run). No model calls."
        ),
    )
    parser.add_argument(
        "--all-runs",
        action="store_true",
        help="With --charts: pool every run and write to outputs/charts/ instead.",
    )
    args = parser.parse_args(argv)
    root = default_output_dir()
    if args.all_runs and not args.charts:
        print("--all-runs only applies together with --charts.", file=sys.stderr)
        return 2
    if args.charts and args.report:
        print("--charts and --report cannot be combined.", file=sys.stderr)
        return 2
    if args.charts:
        return _write_charts(root, run_id=args.run, all_runs=args.all_runs)
    if args.report:
        try:
            run_path = resolve_run_dir(root, args.run)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        path, rows, skipped = write_grading_sheet(run_path)
        skipped_note = f", {skipped} unreadable skipped" if skipped else ""
        print(f"{_display(path)}: {rows} rows{skipped_note}")
        return 0
    try:
        run_path = open_eval_run(
            root,
            run_id=args.run,
            model=args.model,
            verbosity=args.verbosity,
            question=args.question,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"run {_display(run_path)}", flush=True)
    try:
        summary = run_eval(
            output_dir=run_path,
            model=args.model,
            verbosity=args.verbosity,
            question=args.question,
            force=args.force,
            screenshot=args.screenshot,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        f"{_display(run_path)}: {summary.completed} completed, "
        f"{summary.skipped} skipped, {summary.failures} failed",
        flush=True,
    )
    return 1 if summary.failures else 0


def _write_charts(root: Path, *, run_id: str | None, all_runs: bool) -> int:
    if all_runs and run_id is not None:
        print("--all-runs pools every run, so it cannot be combined with --run.", file=sys.stderr)
        return 2
    try:
        if all_runs:
            run_paths = list_run_dirs(root)
            if not run_paths:
                raise ValueError(f"No eval runs in {root}")
            # Outside end_to_end_eval/: a folder there that is not a run id looks like old results.
            out_dir = root.parent / "charts"
        else:
            run_paths = [resolve_run_dir(root, run_id)]
            out_dir = run_paths[0] / "charts"
        written = write_charts(
            run_paths,
            out_dir,
            model_order=[model.id for model in load_agent_config().models],
        )
    except (ChartsUnavailable, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    scope = f"{len(run_paths)} runs" if all_runs else run_paths[0].name
    print(f"{_display(out_dir)}: {len(written)} files from {scope}")
    return 0


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
