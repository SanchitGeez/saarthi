import asyncio
import json
import os

import pytest
from pydantic import ValidationError

from agents import doval, runner, saarthi
from config import Settings


def test_doval_schema_rejects_untrusted_fields():
    good = {
        "additions": [],
        "updates": [],
        "deactivate_ids": [],
        "summary": ["No substantive concern discussed."],
    }
    for bad in [
        {**good, "user_id": "spoof"},
        {**good, "summary": []},
        {**good, "additions": [{"type": "summary", "content": "bad"}]},
        {
            "additions": [{"id": "fact_1", "category": "occupation", "text": "Engineer."}],
            "updates": [],
            "deactivations": [],
            "summary": ["Discussed work."],
        },
        {
            **good,
            "updates": [
                {"id": "not-a-uuid", "type": "factual", "content": "x", "status": "active"}
            ],
        },
    ]:
        with pytest.raises(ValidationError):
            doval.ChangeSet.model_validate(bad)


def test_pinned_adk_litellm_uses_native_schema_without_tools(monkeypatch):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    calls = []
    result = {"additions": [], "updates": [], "deactivate_ids": [], "summary": ["Discussed work."]}

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return ModelResponse(
            choices=[
                {
                    "message": {"role": "assistant", "content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            ]
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(_env_file=None, openrouter_api_key="test-key")
    for _ in range(2):
        changes = asyncio.run(doval.extract(settings, {"transcript": [], "previous_knowledge": []}))
        assert changes.summary == ["Discussed work."]
    assert len(calls) == 2
    for call in calls:
        assert call["model"] == "openrouter/openai/gpt-6-luna"
        assert call["api_key"] == "test-key"
        assert not call.get("tools") and not call.get("functions")
        assert call["reasoning_effort"] == "low"
        assert call["response_format"]["type"] == "json_schema"
        assert call["response_format"]["json_schema"]["strict"] is True
        assert call["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        system_prompt = next(m["content"] for m in call["messages"] if m["role"] == "system")
        assert json.dumps(doval.ChangeSet.model_json_schema(), ensure_ascii=False) in system_prompt
        assert sum(message["role"] == "user" for message in call["messages"]) == 1
        assert not any(message["role"] == "assistant" for message in call["messages"])


def test_missing_key_is_explicit_failure():
    with pytest.raises(runner.AgentFailure):
        asyncio.run(saarthi.reply(Settings(_env_file=None, openrouter_api_key=""), {}))


@pytest.mark.parametrize(
    ("mode", "code", "status", "finish"),
    [
        ("timeout", "timeout", None, None),
        ("rate_limit", "rate_limit", 429, None),
        ("provider", "provider_error", None, None),
        ("empty", "empty_output", None, "STOP"),
        ("long", "output_too_long", None, "STOP"),
        ("truncated", "output_truncated", None, "MAX_TOKENS"),
    ],
)
def test_agent_failure_records_safe_diagnostics(monkeypatch, caplog, mode, code, status, finish):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    class ProviderLimit(Exception):
        status_code = 429

    secret = "sensitive-provider-message-and-key"

    async def completion(self, **kwargs):
        if mode == "timeout":
            raise TimeoutError(secret)
        if mode == "rate_limit":
            raise ProviderLimit(secret)
        if mode == "provider":
            raise RuntimeError(secret)
        return ModelResponse(
            choices=[
                {
                    "message": {
                        "role": "assistant",
                        "content": ""
                        if mode == "empty"
                        else "x" * 8001
                        if mode == "long"
                        else "partial",
                    },
                    "finish_reason": "length" if mode == "truncated" else "stop",
                }
            ],
            **(
                {
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 4096,
                        "total_tokens": 4106,
                        "completion_tokens_details": {"reasoning_tokens": 4000},
                    }
                }
                if mode == "truncated"
                else {}
            ),
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(_env_file=None, openrouter_api_key=secret, agent_reasoning_effort="low")
    observed = []
    with runner.observe_calls(lambda *args: {}, observed.append):
        with pytest.raises(runner.AgentFailure) as caught:
            asyncio.run(saarthi.reply(settings, {"transcript": [], "private": secret}))
    assert len(observed) == 1
    assert observed[0]["status"] == "failed"
    details = caught.value.details
    assert details["code"] == code
    assert details["http_status"] == status
    assert details["finish_reason"] == finish
    assert details["agent"] == "saarthi"
    assert details["stage"] in {"generation", "validation"}
    assert details["elapsed_ms"] >= 0
    assert caught.value.timeout is (mode == "timeout")
    logs = [record.message for record in caplog.records if record.name == "agents.runner"]
    assert len(logs) == 1
    assert details["error_id"] in logs[0]
    assert secret not in logs[0]
    assert secret not in json.dumps(details)
    if mode == "truncated":
        assert details["usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 4096,
            "reasoning_tokens": 4000,
        }
        assert details["max_output_tokens"] == 4096
        assert details["reasoning_effort"] == "low"


@pytest.mark.parametrize("effort", ["none", "low", "medium", "provider_default"])
def test_saarthi_reasoning_and_output_budget_reach_transport(monkeypatch, effort):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return ModelResponse(
            choices=[
                {
                    "message": {"role": "assistant", "content": "Aaj kya hua?"},
                    "finish_reason": "stop",
                }
            ]
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        agent_reasoning_effort=effort,
        agent_max_output_tokens=7777,
    )
    asyncio.run(saarthi.reply(settings, {"transcript": []}))
    assert calls[0]["max_completion_tokens"] == 7777
    if effort != "provider_default":
        assert calls[0]["reasoning_effort"] == effort
    else:
        assert "reasoning_effort" not in calls[0]


def test_saarthi_prompt_override_is_per_call(monkeypatch):
    calls = []

    async def invoke(settings, name, prompt, payload):
        calls.append((name, prompt, payload))
        return "reply"

    monkeypatch.setattr(runner, "invoke", invoke)
    payload = {"opening": True, "transcript": []}
    asyncio.run(saarthi.reply(None, payload, prompt="candidate"))
    asyncio.run(saarthi.reply(None, payload))
    assert calls == [("saarthi", "candidate", payload), ("saarthi", saarthi.PROMPT, payload)]


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_AGENT_TEST") != "1" or not Settings().openrouter_api_key,
    reason="Live OpenRouter credentials/opt-in absent",
)
def test_live_openrouter_both_agents():
    settings = Settings()
    reply = asyncio.run(
        saarthi.reply(
            settings,
            {
                "opening": True,
                "profile": {"name": "Test"},
                "knowledge": [],
                "latest_summary": None,
                "transcript": [],
            },
        )
    )
    assert reply.strip()
    changes = asyncio.run(
        doval.extract(
            settings,
            {
                "transcript": [
                    {"role": "user", "content": "I work as a software engineer."},
                    {"role": "assistant", "content": reply},
                ],
                "previous_knowledge": [],
            },
        )
    )
    assert changes.summary


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("mode", ["truncated", "mismatch", "rate_limit", "timeout", "empty"])
def test_shared_runner_stream_failures_keep_diagnostics_and_retry_policy(
    monkeypatch, streaming, mode
):
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.genai import types

    class ProviderLimit(Exception):
        status_code = 429

    async def events(self, **kwargs):
        if mode == "rate_limit":
            raise ProviderLimit("private provider error")
        if mode == "timeout":
            raise TimeoutError("private provider error")
        if mode == "empty":
            return
        if streaming:
            yield Event(
                author="saarthi",
                partial=True,
                content=types.Content(role="model", parts=[types.Part(text="Partial")]),
            )
        yield Event(
            author="saarthi",
            finish_reason="MAX_TOKENS" if mode == "truncated" else "STOP",
            content=types.Content(role="model", parts=[types.Part(text="Different")]),
        )

    monkeypatch.setattr(Runner, "run_async", events)
    settings = Settings(_env_file=None, openrouter_api_key="test")
    observed = []

    async def run():
        if streaming:
            return [chunk async for chunk in saarthi.stream(settings, {})]
        return await saarthi.reply(settings, {})

    with runner.observe_calls(lambda *args: {}, observed.append):
        if mode == "mismatch" and not streaming:
            assert asyncio.run(run()) == "Different"
            assert observed[0]["status"] == "completed"
            return
        with pytest.raises(runner.AgentFailure) as caught:
            asyncio.run(run())
    assert (
        caught.value.code
        == {
            "truncated": "output_truncated",
            "mismatch": "invalid_output",
            "rate_limit": "rate_limit",
            "timeout": "timeout",
            "empty": "empty_output",
        }[mode]
    )
    assert caught.value.retryable is (mode in {"rate_limit", "timeout"})
    assert len(observed) == 1 and observed[0]["status"] == "failed"
    assert "private provider error" not in json.dumps(caught.value.details)


def test_voice_stream_model_preset_and_usage_reach_native_transport(monkeypatch):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm.types.utils import ModelResponseStream

    calls = []

    async def chunks():
        for text, finish in [("Haan, ", None), ("bolo.", None), (None, "stop")]:
            yield ModelResponseStream(
                model="gpt-6-luna",
                choices=[
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": text},
                        "finish_reason": finish,
                    }
                ],
                **(
                    {"usage": {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24}}
                    if finish
                    else {}
                ),
            )

    async def completion(self, **kwargs):
        calls.append(kwargs)
        return chunks()

    monkeypatch.setattr(LiteLLMClient, "acompletion", completion)
    settings = Settings(
        _env_file=None,
        openrouter_api_key="test",
        agent_model="openrouter/openai/gpt-6-luna",
        agent_provider="openai",
        agent_reasoning_effort="medium",
        agent_max_output_tokens=7777,
    )
    observed = []

    async def run():
        return [chunk async for chunk in saarthi.stream(settings, {}, prompt="Voice candidate")]

    with runner.observe_calls(lambda *args: {}, observed.append):
        assert asyncio.run(run()) == ["Haan, ", "bolo."]
    assert len(calls) == 1
    assert calls[0]["stream"] is True
    assert "temperature" not in calls[0]
    assert calls[0]["max_completion_tokens"] == 7777
    assert calls[0]["reasoning_effort"] == "medium"
    assert calls[0]["extra_body"]["provider"]["only"] == ["openai"]
    assert observed[0]["status"] == "completed"
    assert observed[0]["usage"] == {
        "prompt_tokens": 20,
        "completion_tokens": 4,
    }
