"""DeepEval generates users; every assistant reply goes through the product agent."""

import asyncio
import json
from time import monotonic

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.models import DeepEvalBaseLLM
from deepeval.simulator import ConversationSimulator
from deepeval.simulator.controller import proceed
from deepeval.simulator.schema import SimulatedInput
from deepeval.simulator.simulation_graph import SimulationNode
from deepeval.test_case import Turn
from pydantic import ValidationError

from agents import runner, saarthi

SIMULATOR_INSTRUCTION = """You simulate a user for conversation testing, never the assistant.
Follow the supplied scenario and persona. Respond naturally to the actual assistant.
Do not manufacture a breakthrough or accept an interpretation just to be cooperative.
Only reveal the persona's private background when the conversation warrants it.
Never treat the assistant's suggestions as new facts about you. Keep responses brief.
Do not repeat a question already answered with minor wording changes. Respond to
the new point, correct an assumption, or reveal relevant context naturally. If you
have enough to act, acknowledge that rather than inventing endless new doubts.
Follow the output JSON schema exactly. Do not evaluate or score the assistant.
"""


class SimulatorModel(DeepEvalBaseLLM):
    """Use the existing OpenRouter transport; no implicit OpenAI judge/model."""

    def __init__(self, settings):
        self.settings = settings
        self.response_formats = {"json": 0, "plain_text": 0}
        super().__init__(model=settings.agent_model)

    def load_model(self):
        return self.settings.agent_model

    def get_model_name(self):
        return self.settings.agent_model

    def generate(self, prompt, schema=None):
        return asyncio.run(self.a_generate(prompt, schema=schema))

    async def a_generate(self, prompt, schema=None):
        started = monotonic()
        instruction = SIMULATOR_INSTRUCTION
        if schema:
            instruction += (
                "\nReturn ONLY one JSON object matching this exact schema, "
                "without Markdown, explanation or extra keys:\n"
                + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            )
        text = await runner.invoke(
            self.settings, "eval_user", instruction, {"request": prompt}, schema
        )
        try:
            result = schema.model_validate_json(text) if schema else text
            self.response_formats["json"] += 1
            return result
        except ValidationError as exc:
            # This schema contains only the next utterance. Preserve a raw utterance
            # verbatim; never turn broken JSON/structured output into a user message.
            if schema is SimulatedInput and not text.lstrip().startswith(("{", "[", "```")):
                self.response_formats["plain_text"] += 1
                return SimulatedInput(simulated_input=text)
            failure = runner.AgentFailure(code="schema_validation")
            failure.details.update(
                response_characters=len(text),
                validation_errors=[
                    {"type": item["type"], "location": list(item["loc"])}
                    for item in exc.errors(include_input=False)[:5]
                ],
            )
            failure.record(
                settings=self.settings,
                agent="eval_user",
                stage="schema_validation",
                started=started,
                cause=exc,
            )
            raise failure from exc


def turn_budget_only():
    # DeepEval enforces max_user_simulations; do not invoke its outcome-judging LLM.
    return proceed()


async def product_reply(settings, scenario, turns, prompt, *, opening=False):
    return await saarthi.reply(settings, scenario.payload(turns, opening=opening), prompt=prompt)


def simulate(settings, simulator_settings, scenario, prompt, checkpoint, max_turns=None):
    greeting = asyncio.run(product_reply(settings, scenario, [], prompt, opening=True))
    opening = [Turn(role="assistant", content=greeting)]
    checkpoint(opening)

    async def respond(input, turns, thread_id):
        # DeepEval 4.3.1 already includes the latest user input in turns.
        if not turns or turns[-1].role != "user" or turns[-1].content != input:
            raise ValueError("DeepEval callback history must include the latest user turn once")
        checkpoint(turns)
        answer = await product_reply(settings, scenario, turns, prompt)
        complete = [*turns, Turn(role="assistant", content=answer)]
        checkpoint(complete)
        return complete[-1]

    golden = ConversationalGolden(
        name=scenario.id,
        scenario=scenario.situation,
        persona=Persona(characteristics=scenario.persona),
        turns=opening,
        # Expected behavior is kept for reviewers, not leaked to the simulated user.
    )

    async def user_turn(simulator, turns, golden):
        # Fixed stress triggers guarantee the guardrail is exercised; later turns adapt.
        if not any(turn.role == "user" for turn in turns) and scenario.first_user_message:
            return scenario.first_user_message
        return await simulator.a_generate_next_user_input(golden, turns)

    simulator_model = SimulatorModel(simulator_settings)
    simulator = ConversationSimulator(
        model_callback=respond,
        simulator_model=simulator_model,
        stopping_controller=turn_budget_only,
        language=scenario.language,
        max_concurrent=1,
        simulation_graph=SimulationNode(action=user_turn) if scenario.first_user_message else None,
    )
    cases = simulator.simulate(
        conversational_goldens=[golden],
        max_user_simulations=max_turns or scenario.max_user_turns,
    )
    result = cases[0].model_dump(mode="json")
    result["simulator_response_formats"] = simulator_model.response_formats
    return result


async def replay(settings, scenario, prompt, original_turns, checkpoint):
    """Keep user messages fixed, regenerate every assistant turn including greeting."""
    turns = [
        Turn(
            role="assistant",
            content=await product_reply(settings, scenario, [], prompt, opening=True),
        )
    ]
    checkpoint(turns)
    for original in original_turns:
        if original["role"] != "user":
            continue
        turns.append(Turn(role="user", content=original["content"]))
        checkpoint(turns)
        answer = await product_reply(settings, scenario, turns, prompt)
        turns.append(Turn(role="assistant", content=answer))
        checkpoint(turns)
    return {"turns": [turn.model_dump(mode="json") for turn in turns]}
