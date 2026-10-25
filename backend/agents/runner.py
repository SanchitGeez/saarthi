import asyncio
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from uuid import uuid4

logger = logging.getLogger(__name__)
_call_hooks = ContextVar("agent_call_hooks", default=None)


def generation_temperature(settings, output_schema=None):
    # This exact model's OpenRouter capability list omits temperature (2026-10-20).
    if settings.agent_model == "openrouter/openai/gpt-6-luna":
        return None
    return 0.2 if output_schema else 0.7


@contextmanager
def observe_calls(before, after):
    """Optional local experiment policy; product callers retain their defaults."""
    token = _call_hooks.set((before, after))
    try:
        yield
    finally:
        _call_hooks.reset(token)


def reasoning_effort(settings, agent):
    # Apply the selected effort to both product agents and the eval simulator.
    return (
        settings.agent_reasoning_effort
        if agent in {"saarthi", "doval", "eval_user"}
        else "provider_default"
    )


MESSAGES = {
    "timeout": "The model request exceeded its time limit.",
    "rate_limit": "The provider rejected the request because of a rate limit.",
    "provider_error": "The model provider or transport raised an exception.",
    "missing_credentials": "The model API key is not configured.",
    "model_event_error": "The agent returned an error event.",
    "unexpected_tool_call": "The agent attempted an unsupported tool call.",
    "empty_output": "The agent returned no usable final response.",
    "output_too_long": "The final response exceeded the allowed character limit.",
    "output_truncated": "The model exhausted its output token budget.",
    "invalid_output": "The agent output failed validation.",
    "schema_validation": "The simulated-user response did not match its required JSON schema.",
}


def finish_name(value):
    name = getattr(value, "name", value)
    return (
        name
        if name
        in {
            "STOP",
            "MAX_TOKENS",
            "SAFETY",
            "RECITATION",
            "OTHER",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "MALFORMED_FUNCTION_CALL",
            "UNEXPECTED_TOOL_CALL",
        }
        else None
    )


class AgentFailure(Exception):
    def __init__(self, timeout=False, *, code=None):
        self.code = code or ("timeout" if timeout else "invalid_output")
        self.timeout = timeout or self.code == "timeout"
        self.retryable = self.timeout or self.code == "rate_limit"
        self.details = {
            "error_id": uuid4().hex,
            "code": self.code,
            "message": MESSAGES[self.code],
            "timeout": self.timeout,
        }
        super().__init__(MESSAGES[self.code])

    def record(
        self, *, settings, agent, stage, started, finish_reason=None, cause=None, usage=None
    ):
        chain = []
        seen = set()
        current = cause
        while current is not None and id(current) not in seen and len(chain) < 8:
            seen.add(id(current))
            chain.append(type(current).__name__)
            current = current.__cause__ or current.__context__
        status = getattr(cause, "status_code", None)
        self.details.update(
            agent=agent,
            model=settings.agent_model,
            stage=stage,
            elapsed_ms=round((monotonic() - started) * 1000),
            timeout_seconds=settings.agent_timeout_seconds,
            finish_reason=finish_reason,
            max_output_tokens=settings.agent_max_output_tokens,
            reasoning_effort=reasoning_effort(settings, agent),
            usage=usage or {},
            exception_chain=chain,
            http_status=status if isinstance(status, int) and 100 <= status <= 599 else None,
        )
        # Never log raw provider messages, headers, prompts, payloads or exception reprs.
        logger.warning("agent_failure %s", json.dumps(self.details))


async def invoke(settings, name, instruction, payload, output_schema=None):
    return "".join(
        [
            chunk
            async for chunk in invoke_stream(
                settings, name, instruction, payload, output_schema, streaming=False
            )
        ]
    ).strip()


async def invoke_stream(
    settings, name, instruction, payload, output_schema=None, *, streaming=True
):
    # Each invocation gets an ephemeral session: PostgreSQL is the only transcript store.
    started = monotonic()
    stage = "setup"
    finish_reason = None
    usage = {}
    hooks = _call_hooks.get()
    options = hooks[0](settings, name, instruction, payload, output_schema) if hooks else {}
    temperature = options.get("temperature", generation_temperature(settings, output_schema))
    provider = options.get("provider")
    if provider is None and settings.agent_provider:
        provider = {
            "only": [settings.agent_provider],
            "allow_fallbacks": False,
            "require_parameters": True,
        }
    model_version = None
    status = "failed"
    try:
        if not settings.openrouter_api_key:
            raise AgentFailure(code="missing_credentials")
        from google.adk.agents import LlmAgent
        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.adk.models.lite_llm import LiteLlm
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        async with asyncio.timeout(settings.agent_timeout_seconds):
            agent = LlmAgent(
                name=name,
                model=LiteLlm(
                    model=settings.agent_model,
                    api_key=settings.openrouter_api_key,
                    timeout=settings.agent_timeout_seconds,
                    num_retries=0,
                    **({"extra_body": {"provider": provider}} if provider is not None else {}),
                    **(
                        {"reasoning_effort": reasoning_effort(settings, name)}
                        if reasoning_effort(settings, name) != "provider_default"
                        else {}
                    ),
                ),
                instruction=instruction,
                output_schema=output_schema,
                tools=[],
                disallow_transfer_to_parent=True,
                disallow_transfer_to_peers=True,
                generate_content_config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=settings.agent_max_output_tokens,
                ),
            )
            sessions = InMemorySessionService()
            stage = "session"
            session = await sessions.create_session(app_name=name, user_id="invocation")
            runner = Runner(agent=agent, app_name=name, session_service=sessions)
            result = ""
            streamed = ""
            stage = "generation"
            async for event in runner.run_async(
                user_id="invocation",
                session_id=session.id,
                run_config=RunConfig(
                    streaming_mode=StreamingMode.SSE if streaming else StreamingMode.NONE
                ),
                new_message=types.Content(
                    role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))]
                ),
            ):
                model_version = event.model_version or model_version
                if event.usage_metadata:
                    for field, key in (
                        ("prompt_token_count", "prompt_tokens"),
                        ("candidates_token_count", "completion_tokens"),
                        ("thoughts_token_count", "reasoning_tokens"),
                    ):
                        value = getattr(event.usage_metadata, field, None)
                        if isinstance(value, int) and value >= 0:
                            usage[key] = value
                finish_reason = (
                    finish_name(event.finish_reason)
                    or finish_name(event.error_code)
                    or finish_reason
                )
                if event.error_code:
                    raise AgentFailure(
                        code="output_truncated"
                        if finish_reason == "MAX_TOKENS"
                        else "model_event_error"
                    )
                if event.get_function_calls():
                    raise AgentFailure(code="unexpected_tool_call")
                if streaming and event.partial and event.content:
                    chunk = "".join(
                        p.text or "" for p in event.content.parts or [] if not p.thought
                    )
                    streamed += chunk
                    if len(streamed) > (64000 if output_schema else 8000):
                        raise AgentFailure(code="output_too_long")
                    if chunk:
                        yield chunk
                if event.is_final_response() and event.content:
                    result = "".join(
                        p.text or "" for p in event.content.parts or [] if not p.thought
                    )
            stage = "validation"
            if finish_reason == "MAX_TOKENS":
                raise AgentFailure(code="output_truncated")
            if not result.strip():
                raise AgentFailure(code="empty_output")
            if len(result) > (64000 if output_schema else 8000):
                raise AgentFailure(code="output_too_long")
            if streamed and streamed.strip() != result.strip():
                raise AgentFailure(code="invalid_output")
            status = "completed"
            if not streamed:
                yield result.strip()
    except AgentFailure as exc:
        exc.record(
            settings=settings,
            agent=name,
            stage=stage,
            started=started,
            finish_reason=finish_reason,
            usage=usage,
        )
        raise
    except Exception as exc:
        http_status = getattr(exc, "status_code", None)
        timeout = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
        failure = AgentFailure(
            code="timeout" if timeout else "rate_limit" if http_status == 429 else "provider_error"
        )
        failure.retryable = (
            failure.retryable
            or http_status in {408, 500, 502, 503, 504}
            or isinstance(exc, (ConnectionError, OSError))
        )
        failure.record(
            settings=settings,
            agent=name,
            stage=stage,
            started=started,
            finish_reason=finish_reason,
            cause=exc,
            usage=usage,
        )
        raise failure from exc
    finally:
        if hooks:
            hooks[1](
                {
                    "agent": name,
                    "model": settings.agent_model,
                    "model_version": model_version,
                    "status": status,
                    "elapsed_ms": round((monotonic() - started) * 1000),
                    "usage": usage,
                    "finish_reason": finish_reason,
                    "temperature": temperature,
                    "reasoning_effort": reasoning_effort(settings, name),
                    "max_output_tokens": settings.agent_max_output_tokens,
                    "requested_provider_routing": provider,
                }
            )
