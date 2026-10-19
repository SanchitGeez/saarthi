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
        assert call["model"] == "openrouter/minimax/minimax-m3.1-flash:free"
        assert call["api_key"] == "test-key"
        assert not call.get("tools") and not call.get("functions")
        assert call["response_format"]["type"] == "json_schema"
        assert call["response_format"]["json_schema"]["strict"] is True
        assert call["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert sum(message["role"] == "user" for message in call["messages"]) == 1
        assert not any(message["role"] == "assistant" for message in call["messages"])


def test_missing_key_is_explicit_failure():
    with pytest.raises(runner.AgentFailure):
        asyncio.run(saarthi.reply(Settings(_env_file=None, openrouter_api_key=""), {}))


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("RUN_LIVE_AGENT_TEST") != "1",
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
