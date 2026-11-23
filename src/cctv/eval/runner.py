from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from cctv.api.chat import run_chat_turn
from cctv.api.store import Conversation
from cctv.api.turn_log import tool_names_from_messages
from cctv.config.agent_yaml import agent_config_path, load_agent_config
from cctv.config.models import (
    AgentConfig,
    ModelOption,
    clamp_reasoning,
    clamp_verbosity,
    model_by_id,
)
from cctv.eval.questions import EvalQuestion, load_questions
from cctv.eval.report import SHEET_NAME
from cctv.eval.screenshot import UI_URL, capture_chat_screenshot
from cctv.utils.paths import data_root, project_root


# Every model runs once, at medium verbosity and its catalog reasoning default.
# GPT-6.1 Terra also runs low and high reasoning at that same verbosity. It is the
# visual-reasoning model, so the effort check sits there. An explicit --verbosity
# still applies to every model that allows that level.
EVAL_FOCUS_MODEL_ID = "gpt-6.1-terra"
REASONING_SLICE = ("low", "high")


@dataclass(frozen=True)
class EvalCase:
    model_id: str
    model_label: str
    verbosity: str | None
    question_id: str
    question: str
    reasoning: str | None = None
    expected_cameras: tuple[str, ...] | None = None


@dataclass(frozen=True)
class EvalSummary:
    failures: int
    completed: int
    skipped: int


def default_output_dir() -> Path:
    return project_root() / "outputs" / "end_to_end_eval"


# 2026-11-17T113445 or 2026-11-17T113445-2 when that second already has a folder.
_RUN_ID = re.compile(r"\d{4}-\d{2}-\d{2}T\d{6}(?:-\d+)?")


def new_run_id(moment: datetime | None = None) -> str:
    current = moment.astimezone() if moment is not None else datetime.now().astimezone()
    return current.strftime("%Y-%m-%dT%H%M%S")


def allocate_run_dir(root: Path, moment: datetime | None = None) -> Path:
    """Create a new run folder named with the local time. Adopts a pre-run layout first."""
    root.mkdir(parents=True, exist_ok=True)
    adopt_legacy_run(root)
    current = moment.astimezone() if moment is not None else datetime.now().astimezone()
    destination = _unique_run_dir(root, new_run_id(current))
    destination.mkdir()
    _write_run_meta(destination, current.isoformat(timespec="seconds"))
    return destination


def resolve_run_dir(root: Path, run_id: str | None) -> Path:
    """Return one run folder. ``None`` is the latest. A missing id is an error."""
    adopt_legacy_run(root)
    if run_id is None:
        runs = list_run_dirs(root)
        if not runs:
            raise ValueError(f"No eval runs in {root}")
        return runs[-1]
    if _RUN_ID.fullmatch(run_id) is None or not (root / run_id).is_dir():
        raise ValueError(f"Unknown eval run: {run_id}")
    return root / run_id


def list_run_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and _RUN_ID.fullmatch(path.name)),
        key=lambda path: path.name,
    )


def open_eval_run(
    root: Path,
    *,
    run_id: str | None = None,
    model: str | None = None,
    verbosity: str | None = None,
    question: str | None = None,
    config: AgentConfig | None = None,
    questions: list[EvalQuestion] | None = None,
) -> Path:
    """Validate the matrix, then open a new run or an existing one.

    Validation happens before any folder is created, so a bad model or question
    does not leave an empty run behind.
    """
    agent = config if config is not None else load_agent_config()
    loaded_questions = questions if questions is not None else load_questions()
    build_cases(agent, loaded_questions, model=model, verbosity=verbosity, question=question)
    if run_id is not None:
        return resolve_run_dir(root, run_id)
    return allocate_run_dir(root)


def adopt_legacy_run(root: Path) -> Path | None:
    """Move a flat ``model/question`` tree into the dated folder it belongs to.

    Earlier evals wrote model folders and ``grading.csv`` directly under
    ``outputs/end_to_end_eval/``. The folder name comes from the earliest
    result timestamp, so that run stays identifiable next to later ones.
    """
    if not root.is_dir():
        return None
    legacy_dirs = [
        path for path in root.iterdir() if path.is_dir() and _RUN_ID.fullmatch(path.name) is None
    ]
    has_results = any(any(folder.rglob("result.json")) for folder in legacy_dirs)
    if not legacy_dirs or not has_results:
        return None
    started_at = _legacy_started_at(legacy_dirs)
    destination = _unique_run_dir(root, _run_id_from_timestamp(started_at))
    destination.mkdir()
    for folder in legacy_dirs:
        shutil.move(str(folder), str(destination / folder.name))
    sheet = root / SHEET_NAME
    if sheet.is_file():
        shutil.move(str(sheet), str(destination / sheet.name))
    _write_run_meta(destination, started_at)
    return destination


def _unique_run_dir(root: Path, run_id: str) -> Path:
    candidate = root / run_id
    suffix = 2
    while candidate.exists():
        candidate = root / f"{run_id}-{suffix}"
        suffix += 1
    return candidate


def _run_id_from_timestamp(stamp: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})", stamp)
    if match is None:
        return new_run_id()
    return f"{match.group(1)}T{match.group(2)}{match.group(3)}{match.group(4)}"


def _legacy_started_at(folders: list[Path]) -> str:
    earliest: str | None = None
    for folder in folders:
        for result_file in folder.rglob("result.json"):
            try:
                data = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stamp = data.get("timestamp") if isinstance(data, dict) else None
            if isinstance(stamp, str) and stamp and (earliest is None or stamp < earliest):
                earliest = stamp
    if earliest is not None:
        return earliest
    oldest = min(folder.stat().st_mtime for folder in folders)
    return datetime.fromtimestamp(oldest).astimezone().isoformat(timespec="seconds")


def _write_run_meta(destination: Path, started_at: str) -> None:
    payload = {"id": destination.name, "started_at": started_at}
    (destination / "run.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def build_cases(
    config: AgentConfig,
    questions: list[EvalQuestion],
    *,
    model: str | None = None,
    verbosity: str | None = None,
    question: str | None = None,
) -> list[EvalCase]:
    if model is not None:
        selected = model_by_id(config.models, model)
        if selected is None:
            raise ValueError(f"Unknown model: {model}")
        if not selected.enabled:
            raise ValueError(f"Model is disabled: {model}")
        models = [selected]
    else:
        models = [item for item in config.models if item.enabled]
    selected_questions = list(questions)
    if question is not None:
        selected_questions = [item for item in questions if item.id == question]
        if not selected_questions:
            raise ValueError(f"Unknown question: {question}")
    if verbosity is not None and not any(_accepts_verbosity(option, verbosity) for option in models):
        raise ValueError(f"Verbosity {verbosity!r} is not available for the selected models")

    cases: list[EvalCase] = []
    for option in models:
        for level in _verbosity_levels(option, verbosity):
            for item in selected_questions:
                cases.append(_case(option, item, verbosity=level, reasoning=None))
        for effort in _reasoning_slice(option, verbosity):
            for item in selected_questions:
                cases.append(_case(option, item, verbosity="medium", reasoning=effort))
    return cases


def _case(
    option: ModelOption,
    item: EvalQuestion,
    *,
    verbosity: str | None,
    reasoning: str | None,
) -> EvalCase:
    return EvalCase(
        model_id=option.id,
        model_label=option.label,
        verbosity=verbosity,
        reasoning=reasoning,
        question_id=item.id,
        question=item.text,
        expected_cameras=item.expected_cameras,
    )


def case_dir(output_dir: Path, case: EvalCase) -> Path:
    path = output_dir / case.model_id
    if case.reasoning is not None:
        path = path / f"reasoning-{case.reasoning}"
    if case.verbosity is not None:
        path = path / case.verbosity
    return path / case.question_id


def run_eval(
    *,
    output_dir: Path | None = None,
    model: str | None = None,
    verbosity: str | None = None,
    question: str | None = None,
    force: bool = False,
    screenshot: bool = False,
    ui_url: str = UI_URL,
    config: AgentConfig | None = None,
    questions: list[EvalQuestion] | None = None,
) -> EvalSummary:
    agent = config if config is not None else load_agent_config()
    loaded_questions = questions if questions is not None else load_questions()
    cases = build_cases(agent, loaded_questions, model=model, verbosity=verbosity, question=question)
    root = output_dir or default_output_dir()
    failures = 0
    completed = 0
    skipped = 0
    for case in cases:
        destination = case_dir(root, case)
        if not force and (destination / "result.json").is_file():
            skipped += 1
            print(f"{_case_label(case)} skipped", flush=True)
            continue
        failed = _run_case(
            agent,
            case,
            destination,
            force=force,
            screenshot=screenshot,
            ui_url=ui_url,
        )
        completed += 1
        if failed:
            failures += 1
    return EvalSummary(failures=failures, completed=completed, skipped=skipped)


def _run_case(
    config: AgentConfig,
    case: EvalCase,
    destination: Path,
    *,
    force: bool,
    screenshot: bool,
    ui_url: str,
) -> bool:
    if force and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    option = model_by_id(config.models, case.model_id)
    requested = case.verbosity if case.verbosity is not None else config.verbosity.get(case.model_id)
    applied_verbosity = clamp_verbosity(option, requested)
    baseline = option.reasoning.default if option is not None else None
    applied_reasoning = case.reasoning if case.reasoning is not None else clamp_reasoning(option, baseline)
    started = time.perf_counter()
    try:
        conversation = Conversation(id=uuid.uuid4().hex)
        kwargs: dict[str, Any] = {"model": case.model_id, "reasoning": applied_reasoning}
        if case.verbosity is not None:
            kwargs["verbosity"] = case.verbosity
        _, result = run_chat_turn(conversation, case.question, **kwargs)
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    duration_ms = int((time.perf_counter() - started) * 1000)
    answer = result.get("analysis") if isinstance(result.get("analysis"), str) else ""
    if answer:
        (destination / "answer.md").write_text(answer.rstrip() + "\n", encoding="utf-8")
    payload: dict[str, Any] = {
        "question_id": case.question_id,
        "question": case.question,
        "model": case.model_id,
        "verbosity": applied_verbosity,
        "verbosity_folder": case.verbosity,
        "reasoning": applied_reasoning,
        "success": bool(result.get("success")),
        "error": result.get("error"),
        "duration_ms": duration_ms,
        # usage and model_calls cover every model call in the turn, not only the last one.
        "usage": result.get("usage") or {},
        "model_calls": result.get("model_calls"),
        "tool_rounds": result.get("tool_rounds"),
        "tool_names": tool_names_from_messages(result.get("messages") or []),
        "requested_camera_ids": list(result.get("requested_camera_ids") or []),
        "fetched_camera_ids": list(result.get("fetched_camera_ids") or []),
        "followups": list(result.get("followups") or []),
        "images": _copy_presented_images(result.get("images") or [], destination),
        "shown_camera_ids": list(
            dict.fromkeys(
                str(item["camera_id"])
                for item in result.get("images") or []
                if isinstance(item, dict) and item.get("camera_id")
            )
        ),
        "expected_camera_ids": (
            list(case.expected_cameras) if case.expected_cameras is not None else None
        ),
        "timestamp": result.get("timestamp"),
        "screenshot": None,
        "screenshot_error": None,
    }
    _write_result(destination, payload)
    if screenshot:
        try:
            with _preserved_agent_yaml():
                capture_chat_screenshot(
                    question=case.question,
                    model_label=case.model_label,
                    verbosity=case.verbosity,
                    reasoning=(
                        applied_reasoning
                        if option is not None and option.reasoning.choices and not option.reasoning.locked
                        else None
                    ),
                    path=destination / "screenshot.png",
                    ui_url=ui_url,
                )
            payload["screenshot"] = "screenshot.png"
        except Exception as exc:
            payload["screenshot_error"] = str(exc)
        _write_result(destination, payload)
    label = _case_label(case)
    if payload["success"] and not payload["screenshot_error"]:
        print(f"{label} ok {duration_ms}ms", flush=True)
        return False
    error = payload["screenshot_error"] or payload["error"] or "Chat turn failed"
    print(f"{label} failed: {error}", flush=True)
    return True


def _accepts_verbosity(option: ModelOption, verbosity: str) -> bool:
    control = option.verbosity
    return not control.locked and verbosity in control.choices


def _verbosity_levels(option: ModelOption, requested: str | None) -> list[str | None]:
    control = option.verbosity
    if control.locked or not control.choices:
        if requested is not None:
            return []
        return [None]
    if requested is not None:
        return [requested]
    if control.default in control.choices:
        return [control.default]
    return [control.choices[0]]


def _reasoning_slice(option: ModelOption, verbosity: str | None) -> list[str]:
    """Low and high effort at verbosity medium, for the focus model only."""
    if option.id != EVAL_FOCUS_MODEL_ID:
        return []
    control = option.reasoning
    if control.locked or not control.choices:
        return []
    if verbosity is not None and verbosity != "medium":
        return []
    verbosity_control = option.verbosity
    if verbosity_control.locked or "medium" not in verbosity_control.choices:
        return []
    return [
        effort
        for effort in REASONING_SLICE
        if effort in control.choices and effort != control.default
    ]


def _case_label(case: EvalCase) -> str:
    parts = [case.model_id]
    if case.reasoning is not None:
        parts.append(f"reasoning-{case.reasoning}")
    if case.verbosity is not None:
        parts.append(case.verbosity)
    parts.append(case.question_id)
    return "/".join(parts)


def _copy_presented_images(images: Any, destination: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    if not isinstance(images, list):
        return copied
    root = data_root().resolve()
    folder = destination / "images"
    for index, item in enumerate(images, start=1):
        if not isinstance(item, dict):
            continue
        relative = item.get("path")
        record: dict[str, Any] = {
            "camera_id": item.get("camera_id"),
            "source_path": relative if isinstance(relative, str) else None,
            "annotations": item.get("annotations") or [],
        }
        if isinstance(relative, str) and relative:
            source = (root / relative).resolve()
            if (source == root or root in source.parents) and source.is_file():
                folder.mkdir(parents=True, exist_ok=True)
                name = f"{index}-{source.name}"
                shutil.copy2(source, folder / name)
                record["file"] = f"images/{name}"
        copied.append(record)
    return copied


def _write_result(destination: Path, payload: dict[str, Any]) -> None:
    (destination / "result.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _preserved_agent_yaml() -> Iterator[None]:
    """Put the agent file back if the UI saved a model or verbosity change."""
    path = agent_config_path()
    original = path.read_text(encoding="utf-8") if path.is_file() else None
    try:
        yield
    finally:
        if original is None:
            return
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != original:
            path.write_text(original, encoding="utf-8")
