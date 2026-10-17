import asyncio
import json


class AgentFailure(Exception):
    def __init__(self, timeout=False):
        self.timeout = timeout


async def invoke(settings, name, instruction, payload, output_schema=None):
    # Each invocation gets an ephemeral session: PostgreSQL is the only transcript store.
    if not settings.groq_api_key:
        raise AgentFailure()
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    try:
        async with asyncio.timeout(settings.agent_timeout_seconds):
            agent = LlmAgent(
                name=name,
                model=LiteLlm(
                    model=settings.agent_model,
                    api_key=settings.groq_api_key,
                    timeout=settings.agent_timeout_seconds,
                    num_retries=0,
                ),
                instruction=instruction,
                output_schema=output_schema,
                tools=[],
                disallow_transfer_to_parent=True,
                disallow_transfer_to_peers=True,
                generate_content_config=types.GenerateContentConfig(
                    temperature=0.2 if output_schema else 0.7, max_output_tokens=4096
                ),
            )
            sessions = InMemorySessionService()
            session = await sessions.create_session(app_name=name, user_id="invocation")
            runner = Runner(agent=agent, app_name=name, session_service=sessions)
            result = ""
            async for event in runner.run_async(
                user_id="invocation",
                session_id=session.id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))]
                ),
            ):
                if event.error_code:
                    raise AgentFailure()
                if event.get_function_calls():
                    raise AgentFailure()  # Never silently fall back to tool-based JSON output.
                if event.is_final_response() and event.content:
                    result = "".join(
                        p.text or "" for p in event.content.parts or [] if not p.thought
                    )
            if not result.strip() or len(result) > (64000 if output_schema else 8000):
                raise AgentFailure()
            return result.strip()
    except TimeoutError as exc:
        raise AgentFailure(timeout=True) from exc
    except AgentFailure:
        raise
    except Exception as exc:
        # Provider errors can contain prompts or credentials; callers expose a stable error only.
        raise AgentFailure() from exc
