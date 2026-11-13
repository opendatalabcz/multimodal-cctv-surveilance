from __future__ import annotations

import argparse
import sys

from cctv.eval.report import write_grading_sheet
from cctv.eval.runner import default_output_dir, run_eval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask each evaluation question once per model and verbosity.",
    )
    parser.add_argument("--model", help="Catalog model id. Default: every model.")
    parser.add_argument("--verbosity", help="One verbosity level. Default: every level the model allows.")
    parser.add_argument("--question", help="Question id from configs/eval_questions.yaml.")
    parser.add_argument("--force", action="store_true", help="Replace folders that already have result.json.")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Also save a UI screenshot. Needs make up, and asks the question again in the browser.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Only rewrite outputs/end_to_end_eval/grading.csv from existing results. No model calls.",
    )
    args = parser.parse_args(argv)
    if args.report:
        path, rows, skipped = write_grading_sheet(default_output_dir())
        print(f"{path}: {rows} rows" + (f", {skipped} unreadable skipped" if skipped else ""))
        return 0
    try:
        summary = run_eval(
            model=args.model,
            verbosity=args.verbosity,
            question=args.question,
            force=args.force,
            screenshot=args.screenshot,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 1 if summary.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
