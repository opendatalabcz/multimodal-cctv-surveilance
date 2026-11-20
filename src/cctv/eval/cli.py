from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cctv.eval.report import write_grading_sheet
from cctv.eval.runner import default_output_dir, open_eval_run, resolve_run_dir, run_eval
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
    args = parser.parse_args(argv)
    root = default_output_dir()
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


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
