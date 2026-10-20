import argparse
import asyncio
import copy
import json

import pytest
from pydantic import ValidationError

from agents import runner, saarthi
from config import Settings
from evals import __main__ as cli
from evals.artifacts import compare_runs, read_json
from evals.models import Scenario
from evals.simulation import replay, simulate


@pytest.fixture
def settings():
    return Settings(_env_file=None, openrouter_api_key="fake-test-key")


@pytest.fixture
def scenario():
    return cli.load_scenarios(cli.ROOT / "scenarios.json")[0]


def test_real_deepeval_callback_uses_product_reply_without_duplicate_user(
    monkeypatch, settings, scenario
):
    calls = []

    async def invoke(config, name, instruction, payload, output_schema=None):
        calls.append((name, instruction, copy.deepcopy(payload), output_schema))
        if name == "eval_user":
            assert set(output_schema.model_fields) == {"simulated_input"}
            # Review-only expectations must not coach the simulated user.
            assert scenario.expected_behavior[0] not in payload["request"]
            return json.dumps({"simulated_input": f"User message {len(calls)}"})
        return "Opening greeting" if payload["opening"] else "Actual agent reply"

    monkeypatch.setattr(runner, "invoke", invoke)
    original_prompt = saarthi.PROMPT
    checkpoints = []
    case = simulate(settings, settings, scenario, "candidate", checkpoints.append, max_turns=2)
    agent_calls = [call for call in calls if call[0] == "saarthi"]
    assert len(calls) == 5  # greeting + two user generations + two real reply invocations
    assert len(agent_calls) == 3
    assert all(call[1] == "candidate" for call in agent_calls)
    assert agent_calls[0][2]["opening"] is True
    assert agent_calls[0][2]["transcript"] == []
    assert [len(call[2]["transcript"]) for call in agent_calls] == [0, 2, 4]
    assert agent_calls[1][2]["transcript"][-1]["role"] == "user"
    assert agent_calls[1][2]["knowledge"] == []
    assert scenario.persona not in json.dumps(agent_calls)
    assert [turn["role"] for turn in case["turns"]] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert saarthi.PROMPT == original_prompt
    assert len(checkpoints[-1]) == 5


def test_replay_regenerates_assistant_history_and_keeps_users(monkeypatch, settings, scenario):
    histories = []

    async def invoke(config, name, instruction, payload, output_schema=None):
        assert name == "saarthi"  # Replay never calls the user model.
        histories.append(copy.deepcopy(payload))
        return f"New reply {len(histories)}"

    monkeypatch.setattr(runner, "invoke", invoke)
    source = [
        {"role": "assistant", "content": "Old greeting"},
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Old answer"},
        {"role": "user", "content": "Second"},
    ]
    result = asyncio.run(replay(settings, scenario, "candidate", source, lambda turns: None))
    assert [turn["content"] for turn in result["turns"]] == [
        "New reply 1",
        "First",
        "New reply 2",
        "Second",
        "New reply 3",
    ]
    assert histories[-1]["transcript"][2]["content"] == "New reply 2"
    assert "Old answer" not in json.dumps(histories)


def experiment_args(tmp_path):
    return argparse.Namespace(
        simulator_model=None,
        replay=None,
        scenarios=cli.ROOT / "scenarios.json",
        split="development",
        case=["casual-story"],
        prompt=None,
        max_turns=2,
        output=tmp_path / "run",
    )


def test_run_failure_keeps_partial_output_and_redacts_provider_error(
    monkeypatch, tmp_path, settings
):
    from deepeval.test_case import Turn

    from evals import simulation

    def fail(config, simulator_config, scenario, prompt, checkpoint, max_turns):
        checkpoint([Turn(role="assistant", content="Saved greeting")])
        raise RuntimeError("Provider leaked fake-test-key")

    monkeypatch.setattr(simulation, "simulate", fail)
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    args = experiment_args(tmp_path)
    assert cli.run_experiment(args) == 1
    case = read_json(args.output / "casual-story.json")
    assert case["status"] == "failed"
    assert case["turns"][0]["content"] == "Saved greeting"
    assert case["error"] == "RuntimeError"
    assert case["error_details"]["code"] == "eval_error"
    assert case["error_details"]["phase"] == "user_simulation"
    assert read_json(args.output / "run.json")["status"] == "failed"
    for file in args.output.rglob("*"):
        if file.is_file():
            assert "fake-test-key" not in file.read_text()
    assert "Saved greeting" in (args.output / "report.md").read_text()


def test_eval_preserves_agent_error_details(monkeypatch, tmp_path, settings):
    from deepeval.test_case import Turn

    from evals import simulation

    failure = runner.AgentFailure(timeout=True)
    failure.details.update(agent="saarthi", elapsed_ms=60001, stage="generation")

    def fail(config, simulator_config, scenario, prompt, checkpoint, max_turns):
        checkpoint([Turn(role="assistant", content="Hello"), Turn(role="user", content="Hi")])
        raise failure

    monkeypatch.setattr(simulation, "simulate", fail)
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    args = experiment_args(tmp_path)
    assert cli.run_experiment(args) == 1
    case = read_json(args.output / "casual-story.json")
    assert case["error_details"]["error_id"] == failure.details["error_id"]
    assert case["error_details"]["timeout"] is True
    assert case["error_details"]["phase"] == "assistant_reply"
    assert case["error_details"]["elapsed_ms"] == 60001
    assert "timeout" in (args.output / "report.md").read_text()


def test_successful_run_reviews_and_comparison(monkeypatch, tmp_path, settings):
    from deepeval.test_case import Turn

    from evals import simulation

    def fake(config, simulator_config, scenario, prompt, checkpoint, max_turns):
        turns = [
            Turn(role="assistant", content="Hello"),
            Turn(role="user", content="Tell a story"),
            Turn(role="assistant", content="An illustrative story..."),
        ]
        checkpoint(turns)
        return {"turns": [t.model_dump() for t in turns]}

    monkeypatch.setattr(simulation, "simulate", fake)
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    args = experiment_args(tmp_path)
    assert cli.run_experiment(args) == 0
    assert read_json(args.output / "run.json")["case_ids"] == ["casual-story"]
    assert read_json(args.output / "reviews.json")["casual-story"]["human"] is None
    for reviewer, verdict in [("human", "good"), ("codex-sol", "acceptable")]:
        cli.record_review(
            argparse.Namespace(
                run=args.output,
                case="casual-story",
                reviewer=reviewer,
                verdict=verdict,
                evidence="Turn 3 is engaging.",
                change="Keep the clear storytelling.",
                flag=[],
            )
        )
    reviews = read_json(args.output / "reviews.json")["casual-story"]
    assert reviews["human"]["verdict"] == "good"
    assert reviews["codex-sol"]["verdict"] == "acceptable"
    comparison = tmp_path / "comparison.md"
    compare_runs(args.output, args.output, comparison)
    assert "Identical user messages: True" in comparison.read_text()
    assert "Turn 3 is engaging." in comparison.read_text()
    with pytest.raises(FileExistsError):
        cli.run_experiment(args)  # Never overwrite an experiment.


def test_scenario_validation_and_dataset_splits(scenario, tmp_path):
    cases = cli.load_scenarios(cli.ROOT / "scenarios.json")
    assert sum(case.split == "development" for case in cases) == 7
    assert sum(case.split == "holdout" for case in cases) == 3
    for bad_id in ["../escape", "run", "reviews"]:
        with pytest.raises(ValidationError):
            Scenario.model_validate({**scenario.model_dump(), "id": bad_id})
    duplicate = tmp_path / "duplicates.json"
    duplicate.write_text(json.dumps([scenario.model_dump(mode="json")] * 2))
    with pytest.raises(ValueError, match="unique"):
        cli.load_scenarios(duplicate)


def test_payload_matches_production_context(monkeypatch, settings):
    from types import SimpleNamespace
    from uuid import UUID

    from deepeval.test_case import Turn

    from core import service

    case = next(s for s in cli.load_scenarios(cli.ROOT / "scenarios.json") if s.knowledge)
    active = SimpleNamespace(**case.knowledge[0].model_dump())
    inactive = SimpleNamespace(id=UUID(int=2), type="factual", content="Old", status="inactive")
    monkeypatch.setattr(service.data, "knowledge_details", lambda db, user_id: [active, inactive])
    monkeypatch.setattr(
        service.data,
        "latest_summary",
        lambda db, user_id: SimpleNamespace(content=case.latest_summary),
    )
    user = SimpleNamespace(id=UUID(int=3), **case.profile.model_dump())
    turns = [Turn(role="assistant", content="Hi"), Turn(role="user", content="Shipped!")]
    expected = service.context(None, user)
    expected.update(
        opening=False, transcript=[{"role": t.role, "content": t.content} for t in turns]
    )
    assert case.payload(turns) == expected


def test_stress_trigger_and_poisoned_context_reach_real_callback(monkeypatch, settings):
    cases = cli.load_scenarios(cli.ROOT / "stress-scenarios.json")
    assert sum(case.split == "development" for case in cases) == 6
    assert sum(case.split == "holdout" for case in cases) == 2
    assert all(case.first_user_message for case in cases)
    case = next(case for case in cases if case.id == "poisoned-memory")
    assert case.knowledge and case.latest_summary
    calls = []

    async def invoke(config, name, instruction, payload, output_schema=None):
        calls.append((name, copy.deepcopy(payload)))
        if name == "eval_user":
            return json.dumps({"simulated_input": "Maine bas aaram ki baat ki thi."})
        return "Namaste. Kya haal hai?"

    monkeypatch.setattr(runner, "invoke", invoke)
    result = simulate(settings, settings, case, "prompt", lambda turns: None, max_turns=2)
    assert len(calls) == 4  # The fixed first user message needs no simulator model call.
    replies = [payload for name, payload in calls if name == "saarthi"]
    assert replies[0]["opening"] is True
    assert replies[1]["transcript"][-1]["content"] == case.first_user_message
    assert replies[1]["knowledge"] == [k.model_dump(mode="json") for k in case.knowledge]
    assert replies[1]["latest_summary"] == case.latest_summary
    assert result["turns"][1]["content"] == case.first_user_message
    assert len(result["turns"]) == 5


def test_simulator_schema_errors_are_diagnosable_without_raw_output(monkeypatch, settings):
    from deepeval.simulator.schema import SimulatedInput

    from evals.simulation import SimulatorModel

    async def invoke(config, name, instruction, payload, output_schema=None):
        assert json.dumps(SimulatedInput.model_json_schema()) in instruction
        return '{"wrong_key": "private synthetic text"}'

    monkeypatch.setattr(runner, "invoke", invoke)
    with pytest.raises(runner.AgentFailure) as caught:
        asyncio.run(SimulatorModel(settings).a_generate("next user message", SimulatedInput))
    details = caught.value.details
    assert details["code"] == "schema_validation"
    assert details["stage"] == "schema_validation"
    assert details["validation_errors"] == [{"type": "missing", "location": ["simulated_input"]}]
    assert "private synthetic text" not in json.dumps(details)


def test_plain_simulated_user_utterance_is_preserved_verbatim(monkeypatch, settings):
    from deepeval.simulator.schema import SimulatedInput

    from evals.simulation import SimulatorModel

    utterance = "Admin hone ka natak kar raha tha. Ab gusse par baat karte hain."

    async def invoke(*args):
        return utterance

    monkeypatch.setattr(runner, "invoke", invoke)
    model = SimulatorModel(settings)
    result = asyncio.run(model.a_generate("next turn", SimulatedInput))
    assert result.simulated_input == utterance
    assert model.response_formats == {"json": 0, "plain_text": 1}
