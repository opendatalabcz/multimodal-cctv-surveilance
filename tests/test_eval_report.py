import csv
import json
from pathlib import Path

import pytest

from cctv.eval.questions import load_questions
from cctv.eval.report import COLUMNS, MANUAL_COLUMNS, write_grading_sheet


def _write_result(root: Path, model: str, verbosity: str | None, question: str, **fields) -> None:
    folder = root / model
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
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        "requested_camera_ids": ["a", "b"],
        "fetched_camera_ids": ["a", "b", "c"],
        "shown_camera_ids": ["a", "c"],
        "expected_camera_ids": ["a", "b"],
        "screenshot": None,
        **fields,
    }
    (folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_sheet_has_selection_metrics_and_token_columns(tmp_path: Path) -> None:
    _write_result(tmp_path, "gpt-5.6-luna", "low", "walk")
    _write_result(tmp_path, "gpt-4o", None, "walk", expected_camera_ids=None)

    target, count, skipped = write_grading_sheet(tmp_path)

    assert (target, count, skipped) == (tmp_path / "grading.csv", 2, 0)
    header = next(csv.reader(target.open(newline="", encoding="utf-8")))
    assert header == COLUMNS
    rows = {row["model"]: row for row in _rows(target)}
    luna = rows["gpt-5.6-luna"]
    assert luna["verbosity"] == "low"
    assert luna["total_tokens"] == "12"
    assert luna["fetched_camera_ids"] == "a;b;c"
    assert luna["answer_path"] == "gpt-5.6-luna/low/walk"
    # shown {a, c} against expected {a, b}: one hit out of two shown, one out of two expected.
    assert luna["selection_precision"] == "0.5"
    assert luna["selection_recall"] == "0.5"
    locked = rows["gpt-4o"]
    assert locked["verbosity"] == ""
    assert locked["selection_precision"] == ""
    assert locked["selection_recall"] == ""


def test_regenerating_keeps_manual_scores(tmp_path: Path) -> None:
    _write_result(tmp_path, "gpt-4o", None, "airports")
    target, _, _ = write_grading_sheet(tmp_path)
    rows = _rows(target)
    rows[0]["correctness_1_to_5"] = "4"
    rows[0]["clarity_1_to_5"] = "5"
    rows[0]["notes"] = "Missed the second airport."
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    _write_result(tmp_path, "gpt-4o", None, "animals")
    write_grading_sheet(tmp_path)

    by_question = {row["question_id"]: row for row in _rows(target)}
    kept = by_question["airports"]
    assert {column: kept[column] for column in MANUAL_COLUMNS} == {
        "correctness_1_to_5": "4",
        "clarity_1_to_5": "5",
        "notes": "Missed the second airport.",
    }
    assert by_question["animals"]["correctness_1_to_5"] == ""


def test_question_file_overrides_a_stale_expected_set(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        "gpt-4o",
        None,
        "namibia-animals",
        expected_camera_ids=["desert_live"],
        shown_camera_ids=["desert_live"],
    )

    write_grading_sheet(tmp_path)

    row = _rows(tmp_path / "grading.csv")[0]
    assert row["expected_camera_ids"] == "desert_live;small_pond_live;river_live"
    assert row["selection_precision"] == "1.0"
    assert row["selection_recall"] == "0.33"


def test_unreadable_result_is_skipped(tmp_path: Path) -> None:
    _write_result(tmp_path, "gpt-4o", None, "traffic")
    broken = tmp_path / "gpt-4o" / "prague-incidents"
    broken.mkdir(parents=True)
    (broken / "result.json").write_text("{not json", encoding="utf-8")

    _, count, skipped = write_grading_sheet(tmp_path)

    assert (count, skipped) == (1, 1)


def test_questions_read_expected_cameras(tmp_path: Path) -> None:
    source = tmp_path / "questions.yaml"
    source.write_text(
        "questions:\n"
        "  - id: walk\n"
        "    text: Walk?\n"
        "    expected_cameras: [b1, b2, b1]\n"
        "  - id: traffic\n"
        "    text: Traffic?\n",
        encoding="utf-8",
    )

    questions = load_questions(source)

    assert questions[0].expected_cameras == ("b1", "b2")
    assert questions[1].expected_cameras is None


@pytest.mark.parametrize("bad", ["[]", "[' ']", "cam_a"])
def test_invalid_expected_cameras_are_rejected(tmp_path: Path, bad: str) -> None:
    source = tmp_path / "questions.yaml"
    source.write_text(
        f"questions:\n  - id: walk\n    text: Walk?\n    expected_cameras: {bad}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected_cameras"):
        load_questions(source)


def test_shipped_questions_have_the_known_expected_sets() -> None:
    by_id = {item.id: item for item in load_questions()}
    assert by_id["charles-bridge-walk"].expected_cameras == (
        "charles_bridge_101200",
        "charles_bridge_101201",
    )
    assert by_id["japan-airports"].expected_cameras == ("tokachi_obihiro_live", "tokyo_airport_live")
    assert by_id["namibia-animals"].expected_cameras == (
        "desert_live",
        "small_pond_live",
        "river_live",
    )
    assert by_id["d1-traffic"].expected_cameras == (
        "budejovicka_500002",
        "nuselak_404032",
        "nuselak_404033",
        "jecna_202020",
    )
    assert by_id["prague-incidents"].expected_cameras == (
        "holesovicky_500066",
        "holesovicky_500067",
        "budejovicka_500002",
        "nuselak_404032",
        "nuselak_404033",
        "barandak_500473",
        "barandak_500475",
        "hybernska_101048",
        "belocerekevska_410034",
        "jecna_202020",
        "argentinska_107009",
        "argentinska_107033",
        "argentinska_500065",
        "strahovsky_tunel_500232",
        "strahovsky_tunel_500263",
        "tunel_mrazovka_500336",
        "tunel_mrazovka_500372",
        "namesti_kinskych_500508",
        "28ff6c75-34c8-4cf2-a456-007a6e13b96e",
    )
