import json
from datetime import datetime
from pathlib import Path

import pytest

from cctv.config.agent_yaml import agent_config_path
from cctv.config.models import AgentConfig
from cctv.eval.cli import main
from cctv.eval.questions import load_questions
from cctv.eval.runner import (
    EvalSummary,
    adopt_legacy_run,
    allocate_run_dir,
    default_output_dir,
    build_cases,
    case_dir,
    open_eval_run,
    resolve_run_dir,
    run_eval,
)
from cctv.api.store import Conversation


def _question():
    return next(item for item in load_questions() if item.id == "charles-bridge-walk")


def _ok_turn(conversation: Conversation, content: str, **kwargs):
    return conversation, {
        "success": True,
        "analysis": "The bridge looks quiet.",
        "usage": {"total_tokens": 12},
        "tool_rounds": 2,
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "list_cameras", "arguments": "{}"}}],
            }
        ],
        "images": [
            {
                "path": "camera_images/shot.jpg",
                "camera_id": "charles_bridge_101200",
                "annotations": [{"type": "box"}],
            }
        ],
        "followups": ["Is it crowded?"],
        "timestamp": "2026-11-13T00:00:00",
    }


def test_questions_match_the_application_evaluation() -> None:
    questions = load_questions()
    assert [item.id for item in questions] == [
        "charles-bridge-walk",
        "d1-traffic",
        "prague-incidents",
        "japan-airports",
        "namibia-animals",
    ]
    assert questions[0].text == "Would you recommend a walk on the Charles Bridge right now?"


def test_matrix_skips_verbosity_folder_when_locked() -> None:
    questions = load_questions()
    cases = build_cases(AgentConfig(), questions)
    gpt4o = [case for case in cases if case.model_id == "gpt-4o"]
    luna = [case for case in cases if case.model_id == "gpt-5.6-luna"]
    assert len(cases) == 35
    assert len(gpt4o) == 5
    assert {case.verbosity for case in gpt4o} == {None}
    assert {case.verbosity for case in luna} == {"low", "medium", "high"}
    root = Path("/tmp/eval-layout")
    assert case_dir(root, gpt4o[0]) == root / "gpt-4o" / gpt4o[0].question_id
    low = next(case for case in luna if case.verbosity == "low" and case.question_id == "charles-bridge-walk")
    assert case_dir(root, low) == root / "gpt-5.6-luna" / "low" / "charles-bridge-walk"


def test_verbosity_filter_skips_models_that_cannot_set_it() -> None:
    cases = build_cases(AgentConfig(), load_questions(), verbosity="low")
    assert {case.model_id for case in cases} == {"gpt-5.6-luna", "gpt-6-astra"}
    assert {case.verbosity for case in cases} == {"low"}


def test_matrix_skips_disabled_models() -> None:
    config = AgentConfig()
    config.models[0] = config.models[0].model_copy(update={"enabled": False})
    cases = build_cases(config, load_questions())
    assert "gpt-5.6-luna" not in {case.model_id for case in cases}
    assert len(cases) == 20


def test_explicit_disabled_model_is_an_error() -> None:
    config = AgentConfig()
    config.models[1] = config.models[1].model_copy(update={"enabled": False})
    with pytest.raises(ValueError, match="disabled"):
        build_cases(config, load_questions(), model="gpt-4o")


def test_unknown_verbosity_for_the_selected_model_is_an_error() -> None:
    with pytest.raises(ValueError, match="Verbosity"):
        build_cases(AgentConfig(), load_questions(), model="gpt-4o", verbosity="low")


def test_run_writes_answer_images_and_skips_existing(tmp_path, monkeypatch) -> None:
    image = tmp_path / "camera_images" / "shot.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"jpeg")
    calls = {"n": 0}

    def counting(conversation, content, **kwargs):
        calls["n"] += 1
        assert kwargs["model"] == "gpt-4o"
        assert "verbosity" not in kwargs
        return _ok_turn(conversation, content)

    monkeypatch.setattr("cctv.eval.runner.data_root", lambda: tmp_path)
    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", counting)
    output = tmp_path / "out"
    question = _question()
    summary = run_eval(
        output_dir=output,
        model="gpt-4o",
        question=question.id,
        config=AgentConfig(),
        questions=[question],
    )
    folder = output / "gpt-4o" / "charles-bridge-walk"
    assert summary == EvalSummary(failures=0, completed=1, skipped=0)
    assert (folder / "answer.md").read_text(encoding="utf-8") == "The bridge looks quiet.\n"
    assert (folder / "images" / "1-shot.jpg").read_bytes() == b"jpeg"
    payload = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["verbosity"] == "medium"
    assert payload["verbosity_folder"] is None
    assert payload["tool_names"] == ["list_cameras"]
    assert payload["images"][0]["camera_id"] == "charles_bridge_101200"
    assert payload["images"][0]["file"] == "images/1-shot.jpg"
    assert payload["followups"] == ["Is it crowded?"]
    assert not (output / "gpt-4o" / "medium").exists()

    again = run_eval(
        output_dir=output,
        model="gpt-4o",
        question=question.id,
        config=AgentConfig(),
        questions=[question],
    )
    assert again.skipped == 1
    assert calls["n"] == 1


def test_result_records_turn_totals_and_camera_sets(tmp_path, monkeypatch) -> None:
    def whole_turn(conversation, content, **kwargs):
        updated, result = _ok_turn(conversation, content)
        result["model_calls"] = 3
        result["fetched_camera_ids"] = ["charles_bridge_101200", "charles_bridge_101201"]
        result["requested_camera_ids"] = ["charles_bridge_101200", "charles_bridge_101201"]
        return updated, result

    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", whole_turn)
    output = tmp_path / "out"
    question = _question()
    run_eval(
        output_dir=output,
        model="gpt-4o",
        question=question.id,
        config=AgentConfig(),
        questions=[question],
    )
    payload = json.loads((output / "gpt-4o" / "charles-bridge-walk" / "result.json").read_text())
    assert payload["model_calls"] == 3
    assert payload["fetched_camera_ids"] == ["charles_bridge_101200", "charles_bridge_101201"]
    assert payload["requested_camera_ids"] == ["charles_bridge_101200", "charles_bridge_101201"]
    assert payload["shown_camera_ids"] == ["charles_bridge_101200"]
    assert payload["expected_camera_ids"] == ["charles_bridge_101200", "charles_bridge_101201"]


def test_force_replaces_an_existing_answer(tmp_path, monkeypatch) -> None:
    def changed(conversation, content, **kwargs):
        updated, result = _ok_turn(conversation, content)
        result["analysis"] = "Replaced."
        return updated, result

    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", changed)
    output = tmp_path / "out"
    question = _question()
    folder = output / "gpt-4o" / "charles-bridge-walk"
    folder.mkdir(parents=True)
    (folder / "result.json").write_text("{}\n", encoding="utf-8")
    (folder / "answer.md").write_text("old\n", encoding="utf-8")
    run_eval(
        output_dir=output,
        model="gpt-4o",
        question=question.id,
        force=True,
        config=AgentConfig(),
        questions=[question],
    )
    assert (folder / "answer.md").read_text(encoding="utf-8") == "Replaced.\n"


def test_run_does_not_change_agent_yaml(tmp_path, monkeypatch) -> None:
    before = agent_config_path().read_bytes()
    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", _ok_turn)
    run_eval(
        output_dir=tmp_path / "out",
        model="gpt-4o",
        question="charles-bridge-walk",
    )
    assert agent_config_path().read_bytes() == before


def test_screenshot_failure_keeps_the_answer(tmp_path, monkeypatch) -> None:
    def boom(**kwargs):
        raise RuntimeError("browser down")

    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", _ok_turn)
    monkeypatch.setattr("cctv.eval.runner.capture_chat_screenshot", boom)
    output = tmp_path / "out"
    question = _question()
    summary = run_eval(
        output_dir=output,
        model="gpt-4o",
        question=question.id,
        screenshot=True,
        config=AgentConfig(),
        questions=[question],
    )
    folder = output / "gpt-4o" / "charles-bridge-walk"
    payload = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert summary.failures == 1
    assert (folder / "answer.md").is_file()
    assert payload["success"] is True
    assert "browser down" in payload["screenshot_error"]
    assert payload["screenshot"] is None


def test_screenshot_restores_agent_yaml(tmp_path, monkeypatch) -> None:
    path = tmp_path / "agent.yaml"
    original = "model: gpt-4o\n"
    path.write_text(original, encoding="utf-8")

    def mutate(**kwargs):
        path.write_text("model: gpt-5.6-luna\n", encoding="utf-8")

    monkeypatch.setattr("cctv.eval.runner.agent_config_path", lambda: path)
    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", _ok_turn)
    monkeypatch.setattr("cctv.eval.runner.capture_chat_screenshot", mutate)
    question = _question()
    run_eval(
        output_dir=tmp_path / "out",
        model="gpt-4o",
        question=question.id,
        screenshot=True,
        config=AgentConfig(),
        questions=[question],
    )
    assert path.read_text(encoding="utf-8") == original


def test_cli_rejects_an_unknown_model() -> None:
    assert main(["--model", "missing-model"]) == 2


def test_cli_forwards_filters(monkeypatch, tmp_path: Path) -> None:
    seen: dict = {}
    run_path = tmp_path / "2026-11-17T113445"

    def fake_open(root, **kwargs):
        seen["open"] = {"root": root, **kwargs}
        return run_path

    def fake_run(**kwargs):
        seen["run"] = kwargs
        return EvalSummary(failures=0, completed=0, skipped=0)

    monkeypatch.setattr("cctv.eval.cli.open_eval_run", fake_open)
    monkeypatch.setattr("cctv.eval.cli.run_eval", fake_run)
    assert main(
        [
            "--model",
            "gpt-4o",
            "--verbosity",
            "low",
            "--question",
            "d1-traffic",
            "--run",
            "2026-11-17T113445",
            "--force",
            "--screenshot",
        ]
    ) == 0
    assert seen["open"]["root"] == default_output_dir()
    assert seen["open"]["run_id"] == "2026-11-17T113445"
    assert seen["open"]["model"] == "gpt-4o"
    assert seen["run"]["output_dir"] == run_path
    assert seen["run"]["verbosity"] == "low"
    assert seen["run"]["question"] == "d1-traffic"
    assert seen["run"]["force"] is True
    assert seen["run"]["screenshot"] is True


def test_run_directory_name_uses_local_time(tmp_path: Path) -> None:
    moment = datetime(2026, 11, 17, 11, 34, 45, tzinfo=datetime.now().astimezone().tzinfo)
    path = allocate_run_dir(tmp_path, moment=moment)
    again = allocate_run_dir(tmp_path, moment=moment)
    assert path.name == "2026-11-17T113445"
    assert again.name == "2026-11-17T113445-2"
    meta = json.loads((path / "run.json").read_text(encoding="utf-8"))
    assert meta["id"] == "2026-11-17T113445"
    assert meta["started_at"].startswith("2026-11-17T11:34:45")


def test_each_invocation_gets_its_own_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cctv.eval.runner.run_chat_turn", _ok_turn)
    question = _question()
    config = AgentConfig()
    first = open_eval_run(
        tmp_path,
        model="gpt-4o",
        question=question.id,
        config=config,
        questions=[question],
    )
    second = open_eval_run(
        tmp_path,
        model="gpt-4o",
        question=question.id,
        config=config,
        questions=[question],
    )
    assert first != second
    assert (first / "run.json").is_file()
    run_eval(
        output_dir=first,
        model="gpt-4o",
        question=question.id,
        config=config,
        questions=[question],
    )
    summary = run_eval(
        output_dir=second,
        model="gpt-4o",
        question=question.id,
        config=config,
        questions=[question],
    )
    assert summary == EvalSummary(failures=0, completed=1, skipped=0)
    assert (first / "gpt-4o" / "charles-bridge-walk" / "result.json").is_file()
    assert (second / "gpt-4o" / "charles-bridge-walk" / "result.json").is_file()


def test_resume_uses_the_named_run(tmp_path: Path) -> None:
    question = _question()
    config = AgentConfig()
    created = allocate_run_dir(
        tmp_path,
        moment=datetime(2026, 11, 17, 11, 34, 45, tzinfo=datetime.now().astimezone().tzinfo),
    )
    opened = open_eval_run(
        tmp_path,
        run_id=created.name,
        model="gpt-4o",
        question=question.id,
        config=config,
        questions=[question],
    )
    assert opened == created
    with pytest.raises(ValueError, match="Unknown eval run"):
        resolve_run_dir(tmp_path, "2026-11-17T000000")


def test_invalid_model_does_not_create_a_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown model"):
        open_eval_run(
            tmp_path,
            model="missing-model",
            config=AgentConfig(),
            questions=[_question()],
        )
    assert list(tmp_path.iterdir()) == []


def test_legacy_results_become_a_dated_run(tmp_path: Path) -> None:
    folder = tmp_path / "gpt-4o" / "charles-bridge-walk"
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(
        json.dumps({"timestamp": "2026-11-13T10:30:00.128946"}),
        encoding="utf-8",
    )
    (tmp_path / "grading.csv").write_text("model\n", encoding="utf-8")

    adopted = adopt_legacy_run(tmp_path)

    assert adopted == tmp_path / "2026-11-13T103000"
    assert (adopted / "gpt-4o" / "charles-bridge-walk" / "result.json").is_file()
    assert (adopted / "grading.csv").is_file()
    meta = json.loads((adopted / "run.json").read_text(encoding="utf-8"))
    assert meta["started_at"] == "2026-11-13T10:30:00.128946"
    assert adopt_legacy_run(tmp_path) is None
    assert resolve_run_dir(tmp_path, None) == adopted


def test_directory_without_results_stays_put(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    assert adopt_legacy_run(tmp_path) is None
    assert (tmp_path / "notes").is_dir()


def test_cli_report_targets_the_requested_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cctv.eval.cli.default_output_dir", lambda: tmp_path)
    older = tmp_path / "2026-11-13T103000" / "gpt-4o" / "q"
    newer = tmp_path / "2026-11-17T113445" / "gpt-4o" / "q"
    for folder, question in ((older, "old-question"), (newer, "new-question")):
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps(
                {
                    "question_id": question,
                    "model": "gpt-4o",
                    "verbosity_folder": None,
                    "success": True,
                }
            ),
            encoding="utf-8",
        )

    assert main(["--report"]) == 0
    assert (newer.parent.parent / "grading.csv").is_file()
    assert not (older.parent.parent / "grading.csv").is_file()

    assert main(["--report", "--run", "2026-11-13T103000"]) == 0
    assert (older.parent.parent / "grading.csv").is_file()
    assert main(["--report", "--run", "missing"]) == 2
