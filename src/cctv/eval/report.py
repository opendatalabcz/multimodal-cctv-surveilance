"""Grading sheet for the end-to-end evaluation.

Reads every ``result.json`` under the output folder and writes ``grading.csv``.
Columns that a person fills in (correctness, clarity, notes) are copied from an
existing sheet, so regenerating the sheet after another run keeps those scores.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from cctv.eval.questions import EvalQuestion, load_questions

MANUAL_COLUMNS = ["correctness_1_to_5", "clarity_1_to_5", "notes"]
COLUMNS = [
    "model",
    "verbosity",
    "question_id",
    "success",
    "duration_ms",
    "model_calls",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "requested_camera_ids",
    "fetched_camera_ids",
    "shown_camera_ids",
    "expected_camera_ids",
    "selection_precision",
    "selection_recall",
    *MANUAL_COLUMNS,
    "answer_path",
    "screenshot",
]
SHEET_NAME = "grading.csv"


def write_grading_sheet(
    root: Path,
    questions: list[EvalQuestion] | None = None,
) -> tuple[Path, int, int]:
    """Write ``root/grading.csv``. Returns (path, rows written, unreadable files skipped).

    Expected cameras come from the question file when that question lists them,
    so editing the list and regenerating the sheet updates precision and recall
    without another model run. A question with no list keeps the set stored in
    its result.
    """
    target = root / SHEET_NAME
    manual = _existing_manual_scores(target)
    expected_by_id = _expected_from_questions(questions if questions is not None else load_questions())
    rows: list[dict[str, Any]] = []
    skipped = 0
    for result_file in sorted(root.rglob("result.json")):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue
        if not isinstance(data, dict):
            skipped += 1
            continue
        folder = result_file.parent
        row = _row(data, folder.relative_to(root), expected_by_id)
        key = (row["model"], row["verbosity"], row["question_id"])
        row.update(manual.get(key, {column: "" for column in MANUAL_COLUMNS}))
        rows.append(row)
    rows.sort(key=lambda item: (item["model"], item["verbosity"], item["question_id"]))
    root.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target, len(rows), skipped


def _expected_from_questions(questions: list[EvalQuestion]) -> dict[str, list[str]]:
    return {
        question.id: list(question.expected_cameras)
        for question in questions
        if question.expected_cameras is not None
    }


def _row(
    data: dict[str, Any],
    relative_folder: Path,
    expected_by_id: dict[str, list[str]],
) -> dict[str, Any]:
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    shown = _ids(data.get("shown_camera_ids"))
    question_id = str(data.get("question_id") or "")
    expected = expected_by_id.get(question_id, data.get("expected_camera_ids"))
    precision: float | str = ""
    recall: float | str = ""
    if expected:
        expected_ids = _ids(expected)
        hits = len(set(shown) & set(expected_ids))
        precision = round(hits / len(shown), 2) if shown else 0.0
        recall = round(hits / len(expected_ids), 2)
    screenshot = data.get("screenshot")
    return {
        "model": data.get("model") or "",
        "verbosity": data.get("verbosity_folder") or "",
        "question_id": data.get("question_id") or "",
        "success": data.get("success"),
        "duration_ms": data.get("duration_ms", ""),
        "model_calls": data.get("model_calls", ""),
        "input_tokens": usage.get("input_tokens", ""),
        "output_tokens": usage.get("output_tokens", ""),
        "total_tokens": usage.get("total_tokens", ""),
        "requested_camera_ids": ";".join(_ids(data.get("requested_camera_ids"))),
        "fetched_camera_ids": ";".join(_ids(data.get("fetched_camera_ids"))),
        "shown_camera_ids": ";".join(shown),
        "expected_camera_ids": ";".join(_ids(expected)),
        "selection_precision": precision,
        "selection_recall": recall,
        "answer_path": relative_folder.as_posix(),
        "screenshot": f"{relative_folder.as_posix()}/{screenshot}" if screenshot else "",
    }


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _existing_manual_scores(target: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    if not target.is_file():
        return {}
    scores: dict[tuple[str, str, str], dict[str, str]] = {}
    with target.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("model", ""), row.get("verbosity", ""), row.get("question_id", ""))
            scores[key] = {column: row.get(column, "") for column in MANUAL_COLUMNS}
    return scores
