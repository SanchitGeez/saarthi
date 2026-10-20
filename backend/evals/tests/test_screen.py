import asyncio
import json
from decimal import Decimal

import pytest

from agents import runner
from config import Settings
from evals.artifacts import read_json
from evals.screen import checkpoint
from evals.spending import Spending, SpendingLimit


def candidate():
    return {
        "model": "openrouter/openai/gpt-6-luna",
        "provider": "openai",
        "input_per_m": 0.1,
        "output_per_m": 0.5,
        "temperature": False,
    }


def test_frozen_payload_and_native_transport(monkeypatch, tmp_path):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return ModelResponse(
            model="gpt-6-luna",
            choices=[
                {"message": {"role": "assistant", "content": "Theek."}, "finish_reason": "stop"}
            ],
            usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    fixture = {
        "payload": {
            "profile": {"name": "Test"},
            "knowledge": [],
            "latest_summary": "Known fact",
            "opening": False,
            "transcript": [
                {"role": "assistant", "content": "Old response unchanged"},
                {"role": "user", "content": "Latest once"},
            ],
        },
        "persona": "Hidden private facts",
    }
    settings = Settings(_env_file=None, openrouter_api_key="test", agent_model=candidate()["model"])
    ledger = Spending(tmp_path / "cost.json", 0.1, [candidate()])
    with runner.observe_calls(ledger.before, ledger.after):
        assert asyncio.run(checkpoint(settings, "Frozen prompt", fixture)) == "Theek."
    assert len(calls) == 1
    call = calls[0]
    assert "temperature" not in call
    assert call["extra_body"]["provider"]["only"] == ["openai"]
    assert call["extra_body"]["provider"]["allow_fallbacks"] is False
    assert call["max_completion_tokens"] == 4096
    user = next(m["content"] for m in call["messages"] if m["role"] == "user")
    assert json.loads(user) == fixture["payload"]
    assert "Hidden private" not in str(call)
    saved = read_json(tmp_path / "cost.json")
    assert saved["calls"][0]["usage"]["prompt_tokens"] == 100
    assert saved["calls"][0]["temperature"] is None
    assert saved["calls"][0]["model_version"] == "gpt-6-luna"
    assert saved["calls"][0]["estimated_token_cost_usd"] is not None


def test_reservations_persist_unknown_usage_and_stop(tmp_path):
    ledger = Spending(tmp_path / "cost.json", 0.003, [candidate()])
    settings = Settings(_env_file=None, agent_model=candidate()["model"])
    ledger.before(settings, "saarthi", "prompt", {}, None)
    reserved = read_json(tmp_path / "cost.json")["reserved_usd"]
    assert Decimal(reserved) > 0
    ledger.after({"model": candidate()["model"], "usage": {}, "status": "failed"})
    assert read_json(tmp_path / "cost.json")["calls"][0]["estimated_token_cost_usd"] is None
    with pytest.raises(SpendingLimit):
        ledger.before(settings, "saarthi", "prompt", {}, None)
    assert len(ledger.records) == 1
    assert read_json(tmp_path / "cost.json")["reserved_usd"] == reserved


def test_reservation_rejects_long_context(tmp_path):
    ledger = Spending(tmp_path / "cost.json", 1, [candidate()])
    settings = Settings(_env_file=None, agent_model=candidate()["model"])
    with pytest.raises(SpendingLimit):
        ledger.before(settings, "saarthi", "x" * 32000, {}, None)
    assert not ledger.records


def test_conversations_keep_simulator_independent(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from evals import conversations
    from evals.artifacts import write_json

    cs = [
        dict(candidate(), id="assistant", effort="high"),
        dict(
            candidate(),
            id="simulator",
            model="openrouter/qwen/qwen3.7-flash",
            provider="alibaba",
            effort="provider_default",
            temperature=True,
        ),
    ]
    plan = tmp_path / "plan.json"
    write_json(plan, {"candidates": cs})
    monkeypatch.setattr(conversations, "account", lambda s: {"total_credits": 10, "total_usage": 0})

    def capture(args, *, settings, simulator_settings, transport_metadata):
        assert settings.agent_reasoning_effort == "high"
        assert settings.agent_max_output_tokens == 4096
        assert simulator_settings.agent_max_output_tokens == 2048
        assert simulator_settings.agent_reasoning_effort == "provider_default"
        assert simulator_settings.agent_model == "openrouter/qwen/qwen3.7-flash"
        assert transport_metadata["agent_temperature"] is None
        assert transport_metadata["simulator_temperature"] == 0.2
        assert args.max_turns == 6
        return 0

    monkeypatch.setattr(conversations, "run_experiment", capture)
    args = SimpleNamespace(
        plan=plan,
        budget=0.5,
        model="assistant",
        simulator="simulator",
        output=tmp_path / "run",
        scenarios=tmp_path / "cases.json",
        split="development",
        case=["one"],
        prompt=tmp_path / "prompt.txt",
    )
    assert conversations.run(args) == 0


def test_screen_refuses_unfunded_run(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from evals import screen

    monkeypatch.setattr(screen, "account", lambda s: {"total_credits": 0, "total_usage": 0})
    with pytest.raises(ValueError, match="balance"):
        screen.run(SimpleNamespace(budget=1, output=tmp_path / "unfunded"))
    assert not (tmp_path / "unfunded").exists()


def test_screen_saves_interrupted_call(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from evals import screen
    from evals.artifacts import write_json

    monkeypatch.setattr(screen, "account", lambda s: {"total_credits": 10, "total_usage": 0})
    plan, fixtures, prompt = (tmp_path / x for x in ("plan.json", "fixtures.json", "prompt.txt"))
    write_json(plan, {"candidates": [dict(candidate(), id="test", effort="medium")]})
    write_json(fixtures, [{"id": "test", "payload": {}}])
    prompt.write_text("test")

    async def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(screen, "checkpoint", interrupt)
    args = SimpleNamespace(
        plan=plan,
        fixtures=fixtures,
        prompt=prompt,
        output=tmp_path / "run",
        budget=1,
        model=None,
        case=None,
        cap=4096,
        repeats=1,
    )
    with pytest.raises(KeyboardInterrupt):
        screen.run(args)
    assert read_json(args.output / "run.json")["status"] == "stopped"
    assert read_json(args.output / "responses.json")[0]["status"] == "interrupted"


def test_round_limit_includes_other_stage_reservations(tmp_path):
    from evals.artifacts import write_json

    prior = tmp_path / "earlier"
    prior.mkdir()
    write_json(prior / "spending.json", {"reserved_usd": "3.999"})
    current = tmp_path / "next"
    current.mkdir()
    ledger = Spending(current / "spending.json", 1, [candidate()], round_directory=tmp_path)
    settings = Settings(_env_file=None, agent_model=candidate()["model"])
    with pytest.raises(SpendingLimit, match="round budget"):
        ledger.before(settings, "saarthi", "test", {}, None)
    assert not ledger.records


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf")])
def test_invalid_prices_cannot_create_a_reservation(tmp_path, rate):
    with pytest.raises(ValueError, match="Prices"):
        Spending(tmp_path / "spending.json", 1, [dict(candidate(), input_per_m=rate)])
    assert not (tmp_path / "spending.json").exists()


def test_luna_omits_temperature_without_eval_hooks(monkeypatch):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return ModelResponse(
            choices=[
                {"message": {"role": "assistant", "content": "Theek."}, "finish_reason": "stop"}
            ]
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(_env_file=None, openrouter_api_key="test", agent_model=candidate()["model"])
    assert asyncio.run(runner.invoke(settings, "saarthi", "prompt", {})) == "Theek."
    assert "temperature" not in calls[0]
    assert "extra_body" not in calls[0]


def test_deepeval_callbacks_all_share_spending_scope(monkeypatch, tmp_path):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from evals.__main__ import ROOT, load_scenarios
    from evals.simulation import simulate

    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs)
        content = (
            json.dumps({"simulated_input": "Mera agla sawaal"})
            if kwargs.get("response_format")
            else "Saarthi ka jawab"
        )
        return ModelResponse(
            choices=[
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(_env_file=None, openrouter_api_key="test", agent_model=candidate()["model"])
    ledger = Spending(tmp_path / "cost.json", 0.1, [candidate()])
    scenario = load_scenarios(ROOT / "scenarios.json")[0]
    with runner.observe_calls(ledger.before, ledger.after):
        case = simulate(settings, settings, scenario, "prompt", lambda t: None, max_turns=2)
    assert len(case["turns"]) == 5
    assert len(calls) == len(ledger.records) == 5
    assert [r["agent"] for r in ledger.records] == [
        "saarthi",
        "eval_user",
        "saarthi",
        "eval_user",
        "saarthi",
    ]
    assert all(r["status"] == "completed" for r in ledger.records)
    assert all(c["extra_body"]["provider"]["only"] == ["openai"] for c in calls)


def test_product_provider_pin_works_without_eval_policy(monkeypatch):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return ModelResponse(
            choices=[
                {"message": {"role": "assistant", "content": "Theek."}, "finish_reason": "stop"}
            ]
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(
        _env_file=None,
        openrouter_api_key="test",
        agent_model=candidate()["model"],
        agent_provider="openai",
    )
    asyncio.run(runner.invoke(settings, "saarthi", "prompt", {}))
    assert calls[0]["extra_body"]["provider"] == {
        "only": ["openai"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert "temperature" not in calls[0]


@pytest.mark.parametrize("recovery", [False, True])
def test_voice_checkpoint_streams_exact_delivered_history(monkeypatch, recovery):
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.genai import types

    from agents import saarthi

    transcript = [
        {"role": "assistant", "content": "Haan, bolo."},
        {"role": "user", "content": "Office mein dikkat hai."},
        {"role": "assistant", "content": "Kaam ke", "interrupted": True},
        {"role": "user", "content": "Ruko, kaam nahi, manager se."},
    ]
    payload = {
        "profile": {"name": "Test"},
        "knowledge": [],
        "latest_summary": None,
        "opening": False,
        "transcript": transcript,
    }
    if recovery:
        transcript.append({"role": "assistant", "content": "Manager se", "interrupted": True})
        payload["voice_recovery"] = (
            "Continue the interrupted reply without repeating the delivered prefix."
        )
    captured = []

    async def events(self, **kwargs):
        assert kwargs["run_config"].streaming_mode.value == "sse"
        assert self.agent.instruction == "Voice candidate"
        captured.append(json.loads(kwargs["new_message"].parts[0].text))
        for text, partial in [("Kya ", True), ("hua?", True), ("Kya hua?", False)]:
            yield Event(
                author="saarthi",
                partial=partial,
                content=types.Content(role="model", parts=[types.Part(text=text)]),
            )

    monkeypatch.setattr(Runner, "run_async", events)
    settings = Settings(_env_file=None, openrouter_api_key="test")
    observed = []
    baseline = saarthi.PROMPT
    with runner.observe_calls(lambda *args: {}, observed.append):
        assert (
            asyncio.run(
                checkpoint(settings, "Voice candidate", {"transport": "voice", "payload": payload})
            )
            == "Kya hua?"
        )
    assert captured == [payload]
    assert len(observed) == 1 and observed[0]["status"] == "completed"
    assert saarthi.PROMPT == baseline
