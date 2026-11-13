from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cctv.utils.paths import project_root

_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    text: str
    # Camera ids a good answer should draw on. None means not decided yet.
    expected_cameras: tuple[str, ...] | None = None


def questions_path() -> Path:
    return project_root() / "configs" / "eval_questions.yaml"


def load_questions(path: Path | None = None) -> list[EvalQuestion]:
    source = path or questions_path()
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    raw = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"No questions in {source}")
    questions: list[EvalQuestion] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid question entry in {source}")
        question_id = str(item.get("id") or "").strip()
        text = str(item.get("text") or "").strip()
        if not question_id or not text or question_id in seen or not _safe_id(question_id):
            raise ValueError(f"Invalid question id {question_id!r} in {source}")
        seen.add(question_id)
        questions.append(
            EvalQuestion(
                id=question_id,
                text=text,
                expected_cameras=_expected_cameras(item.get("expected_cameras"), question_id, source),
            )
        )
    return questions


def _expected_cameras(raw: Any, question_id: str, source: Path) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"expected_cameras for {question_id!r} must be a non-empty list in {source}")
    ids = [str(item).strip() for item in raw]
    if not all(ids):
        raise ValueError(f"expected_cameras for {question_id!r} has an empty id in {source}")
    return tuple(dict.fromkeys(ids))


def _safe_id(question_id: str) -> bool:
    return question_id[0].isalnum() and set(question_id) <= _ID_CHARS
