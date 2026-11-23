"""Grading sheet for the end-to-end evaluation.

Reads every ``result.json`` under the output folder and writes ``grading.csv``.
Columns that a person fills in (correctness, clarity, notes) are copied from an
existing sheet, so regenerating the sheet after another run keeps those scores.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cctv.eval.questions import EvalQuestion, load_questions
from cctv.observability.usage import normalize_usage

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
    "attempted_camera_ids",
    "shown_camera_ids",
    "expected_camera_ids",
    "retrieval_precision",
    "retrieval_recall",
    "selection_precision",
    "selection_recall",
    *MANUAL_COLUMNS,
    "answer_path",
    "screenshot",
]
SHEET_NAME = "grading.csv"


CameraResolver = Callable[[str], str | None]


def write_grading_sheet(
    root: Path,
    questions: list[EvalQuestion] | None = None,
    resolve: CameraResolver | None = None,
) -> tuple[Path, int, int]:
    """Write ``root/grading.csv``. Returns (path, rows written, unreadable files skipped).

    Expected cameras come from the question file when that question lists them,
    so editing the list and regenerating the sheet updates precision and recall
    without another model run. A question with no list keeps the set stored in
    its result.
    """
    target = root / SHEET_NAME
    rows, skipped = load_rows([root], questions, resolve=resolve)
    root.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return target, len(rows), skipped


def load_rows(
    roots: list[Path],
    questions: list[EvalQuestion] | None = None,
    *,
    resolve: CameraResolver | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Read every ``result.json`` under each run folder into one row.

    Rows carry the ``COLUMNS`` fields plus ``run`` (the folder name). Hand-entered
    scores come from that run's existing ``grading.csv``. Returns the rows and the
    number of unreadable files skipped. The grading sheet and the charts both use
    this, so they cannot disagree.
    """
    expected_by_id = _expected_from_questions(questions if questions is not None else load_questions())
    resolve = resolve or _catalog_resolver()
    rows: list[dict[str, Any]] = []
    skipped = 0
    for root in roots:
        manual = _existing_manual_scores(root / SHEET_NAME)
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
            row = _row(data, folder.relative_to(root), expected_by_id, resolve)
            row["run"] = root.name
            key = (row["model"], row["verbosity"], row["question_id"])
            row.update(manual.get(key, {column: "" for column in MANUAL_COLUMNS}))
            rows.append(row)
    rows.sort(
        key=lambda item: (item["run"], item["model"], item["verbosity"], item["question_id"])
    )
    return rows, skipped


def _catalog_resolver() -> CameraResolver:
    """Map a camera id or display name to its catalog id, remembering each answer."""
    from cctv.tools.get_camera import resolve_camera

    remembered: dict[str, str | None] = {}

    def resolve(query: str) -> str | None:
        if query not in remembered:
            camera = resolve_camera(query)
            remembered[query] = camera.id if camera is not None else None
        return remembered[query]

    return resolve


def _attempted_ids(data: dict[str, Any], resolve: CameraResolver) -> list[str]:
    """Cameras the model tried to use, whether or not the fetch worked.

    Requested ids are raw strings the model typed, so each is mapped to its
    catalog id. A string that matches no camera stays as typed and counts as a
    wrong pick. Fetched ids are added because they are always real cameras.
    """
    attempted: list[str] = [resolve(raw) or raw for raw in _ids(data.get("requested_camera_ids"))]
    attempted.extend(_ids(data.get("fetched_camera_ids")))
    return list(dict.fromkeys(attempted))


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
    resolve: CameraResolver,
) -> dict[str, Any]:
    # Azure reports input_tokens, chat completions report prompt_tokens.
    tokens = normalize_usage(data.get("usage")) or {}
    shown = _ids(data.get("shown_camera_ids"))
    attempted = _attempted_ids(data, resolve)
    question_id = str(data.get("question_id") or "")
    expected = expected_by_id.get(question_id, data.get("expected_camera_ids"))
    retrieval_precision, retrieval_recall = _precision_recall(attempted, expected)
    selection_precision, selection_recall = _precision_recall(shown, expected)
    screenshot = data.get("screenshot")
    return {
        "model": data.get("model") or "",
        "verbosity": data.get("verbosity_folder") or "",
        "question_id": data.get("question_id") or "",
        "success": data.get("success"),
        "duration_ms": data.get("duration_ms", ""),
        "model_calls": data.get("model_calls", ""),
        "input_tokens": tokens.get("input", ""),
        "output_tokens": tokens.get("output", ""),
        "total_tokens": tokens.get("total", ""),
        "requested_camera_ids": ";".join(_ids(data.get("requested_camera_ids"))),
        "fetched_camera_ids": ";".join(_ids(data.get("fetched_camera_ids"))),
        "attempted_camera_ids": ";".join(attempted),
        "shown_camera_ids": ";".join(shown),
        "expected_camera_ids": ";".join(_ids(expected)),
        "retrieval_precision": retrieval_precision,
        "retrieval_recall": retrieval_recall,
        "selection_precision": selection_precision,
        "selection_recall": selection_recall,
        "answer_path": relative_folder.as_posix(),
        "screenshot": f"{relative_folder.as_posix()}/{screenshot}" if screenshot else "",
    }


def _precision_recall(picked: list[str], expected: Any) -> tuple[float | str, float | str]:
    """Share of ``picked`` that is expected, and share of expected that was picked.

    Blank when the question has no expected set yet.
    """
    expected_ids = _ids(expected)
    if not expected_ids:
        return "", ""
    hits = len(set(picked) & set(expected_ids))
    precision = round(hits / len(set(picked)), 2) if picked else 0.0
    return precision, round(hits / len(set(expected_ids)), 2)


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
