from __future__ import annotations

import json
import shutil
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
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
from cctv.eval.screenshot import UI_URL, capture_chat_screenshot
from cctv.utils.paths import data_root, project_root


@dataclass(frozen=True)
class EvalCase:
    model_id: str
    model_label: str
    verbosity: str | None
    question_id: str
    question: str


@dataclass(frozen=True)
class EvalSummary:
    failures: int
    completed: int
    skipped: int


def default_output_dir() -> Path:
    return project_root() / "outputs" / "end_to_end_eval"


def build_cases(
    config: AgentConfig,
    questions: list[EvalQuestion],
    *,
    model: str | None = None,
    verbosity: str | None = None,
    question: str | None = None,
) -> list[EvalCase]:
    models = list(config.models)
    if model is not None:
        selected = model_by_id(models, model)
        if selected is None:
            raise ValueError(f"Unknown model: {model}")
        models = [selected]
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
                cases.append(
                    EvalCase(
                        model_id=option.id,
                        model_label=option.label,
                        verbosity=level,
                        question_id=item.id,
                        question=item.text,
                    )
                )
    return cases


def case_dir(output_dir: Path, case: EvalCase) -> Path:
    path = output_dir / case.model_id
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
    applied_reasoning = clamp_reasoning(option, config.reasoning.get(case.model_id))
    started = time.perf_counter()
    try:
        conversation = Conversation(id=uuid.uuid4().hex)
        kwargs: dict[str, Any] = {"model": case.model_id}
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
        "usage": result.get("usage") or {},
        "tool_rounds": result.get("tool_rounds"),
        "tool_names": tool_names_from_messages(result.get("messages") or []),
        "followups": list(result.get("followups") or []),
        "images": _copy_presented_images(result.get("images") or [], destination),
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
    return list(control.choices)


def _case_label(case: EvalCase) -> str:
    if case.verbosity is None:
        return f"{case.model_id}/{case.question_id}"
    return f"{case.model_id}/{case.verbosity}/{case.question_id}"


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
