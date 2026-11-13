import json
from pathlib import Path

import pytest

from cctv.config.agent_yaml import agent_config_path
from cctv.config.models import AgentConfig
from cctv.eval.cli import main
from cctv.eval.questions import load_questions
from cctv.eval.runner import EvalSummary, build_cases, case_dir, run_eval
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


def test_cli_forwards_filters(monkeypatch) -> None:
    seen: dict = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return EvalSummary(failures=0, completed=0, skipped=0)

    monkeypatch.setattr("cctv.eval.cli.run_eval", fake_run)
    assert main(
        [
            "--model",
            "gpt-4o",
            "--verbosity",
            "low",
            "--question",
            "d1-traffic",
            "--force",
            "--screenshot",
        ]
    ) == 0
    assert seen["model"] == "gpt-4o"
    assert seen["verbosity"] == "low"
    assert seen["question"] == "d1-traffic"
    assert seen["force"] is True
    assert seen["screenshot"] is True
