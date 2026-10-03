"""Bounded OpenAI-compatible turns using the same trusted tools as ADK."""
import asyncio
import json
from types import SimpleNamespace
from openai import AsyncOpenAI
from app.config import settings


def tool(name, description, fields):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": {key: {"type": "string", "description": value} for key, value in fields.items()},
            "required": list(fields), "additionalProperties": False}}}

TOOLS = [
    tool("find_memories", "Read previously shared useful context", {"query": "Relevant topic"}),
    tool("remember_detail", "Remember one explicitly stated lasting fact. Exact evidence from current user message required", {"content": "Brief fact", "kind": "context, preference, goal, or pattern", "evidence": "Exact quote from current user message"}),
    tool("update_remembered_detail", "Correct a previously saved fact with explicitly supplied correction", {"memory_id": "Existing memory UUID", "content": "Corrected fact", "evidence": "Exact quote from current user message"}),
    tool("get_gita_verse", "Retrieve a verified Gita verse", {"reference": "2.14, 2.47, 2.48, 6.5, 6.26, or 12.13"}),
]


async def run_openrouter_turn(user_id, session_id, message, history, language, messages):
    from app.agent import (text_instructions, load_memories, _turn_context,
        find_memories, remember_detail, update_remembered_detail, get_gita_verse)
    if not settings.openrouter_api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY before starting conversations.")
    remembered = await load_memories(_turn_context.get(), message)
    prompt = [{"role": "system", "content": text_instructions(language, remembered)}]
    if messages is not None:
        prompt += [{"role": m["role"], "content": m["text"] + (" [This reply was interrupted.]" if m.get("interrupted") else "")} for m in messages[-48:]]
    else:
        for turn in history[-24:]:
            prompt.extend({"role": role, "content": value} for role, value in [("user", turn.text), ("assistant", turn.answer)] if value)
    prompt.append({"role": "user", "content": message})
    trusted = SimpleNamespace(user_id=str(user_id))
    functions = {f.__name__: f for f in [find_memories, remember_detail, update_remembered_detail, get_gita_verse]}
    async with AsyncOpenAI(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1", timeout=25, max_retries=0) as client:
        async with asyncio.timeout(90):
            for _ in range(5):
                response = await client.chat.completions.create(model=settings.openrouter_model,
                    messages=prompt, tools=TOOLS, parallel_tool_calls=False, max_tokens=650)
                reply = response.choices[0].message
                if not reply.tool_calls:
                    return (reply.content or "").strip()
                prompt.append(reply.model_dump(exclude_none=True))
                for call in reply.tool_calls:
                    try:
                        args = json.loads(call.function.arguments)
                        # Identity is supplied by the server, never by model arguments.
                        args.pop("tool_context", None)
                        fn = functions[call.function.name]
                        result = fn(**args, tool_context=trusted)
                        if asyncio.iscoroutine(result): result = await result
                    except (KeyError, ValueError, TypeError):
                        result = {"error": "Invalid tool arguments"}
                    prompt.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
    raise RuntimeError("Model exceeded the tool call limit.")
