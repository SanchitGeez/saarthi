"""Exercise capture against real Pipecat queues and interruption handlers."""

import asyncio
from contextlib import suppress
from uuid import UUID, uuid4

import pytest

pytest.importorskip("pipecat")

from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    InterruptionFrame,
    StartFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from config import Settings
from core import service
from tests.conftest import sign_in, start
from voice import store
from voice.pipeline import AgentOutput, CaptureTurn
from voice.policy import Delivery
from voice.session import VoiceSession


class Probe(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.started = asyncio.Event()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        self.frames.append(frame)
        if isinstance(frame, StartFrame):
            self.started.set()
        await self.push_frame(frame, direction)


@pytest.mark.parametrize("interim_first", [False, True])
@pytest.mark.parametrize("playing", [False, True])
def test_interruption_preserves_final_speech_and_stops_old_task(interim_first, playing):
    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        replies, events = [], []

        async def respond(**kwargs):
            replies.append(kwargs["text"])

        session.start_response = respond
        session.event = lambda kind, **values: events.append((kind, values))
        capture, agent, output = CaptureTurn(session), AgentOutput(), Probe()
        session.agent = agent
        old = session.response_task = asyncio.create_task(asyncio.sleep(30))
        session.delivery = Delivery(sent_seconds=1 if playing else 0)
        task = PipelineTask(
            Pipeline([capture, agent, output]), enable_rtvi=False, idle_timeout_secs=0
        )
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        try:
            await asyncio.wait_for(output.started.wait(), 2)
            if interim_first:
                await task.queue_frame(InterimTranscriptionFrame("मेरी बात", "user", "now"))
            text = "मेरी बात पूरी सुनो"
            await task.queue_frame(TranscriptionFrame(text, "user", "now"))
            async with asyncio.timeout(2):
                while not any(isinstance(f, TranscriptionFrame) for f in output.frames):
                    await asyncio.sleep(0.01)
            assert old.cancelled()
            assert session.response_task is None
            assert capture.parts == [text]
            assert any(isinstance(f, InterruptionFrame) for f in output.frames)
            await agent.push_frame(UserStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
            async with asyncio.timeout(2):
                while not replies:
                    await asyncio.sleep(0.01)
            assert replies == [text]
            # Another segment in the same thought must not lose its prefix.
            await task.queue_frame(TranscriptionFrame("client meeting में", "user", "now"))
            await task.queue_frame(TranscriptionFrame("मुझे डांटा गया", "user", "now"))
            async with asyncio.timeout(2):
                while len(capture.parts) != 2:
                    await asyncio.sleep(0.01)
            await agent.push_frame(UserStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
            async with asyncio.timeout(2):
                while len(replies) != 2:
                    await asyncio.sleep(0.01)
            assert replies[-1] == "client meeting में मुझे डांटा गया"
        finally:
            await task.cancel()
            await runner
            old.cancel()
            with suppress(asyncio.CancelledError):
                await old

    asyncio.run(run())


def test_resumed_speech_cancels_generation_before_transcription():
    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        capture, agent, output = CaptureTurn(session), AgentOutput(), Probe()
        session.agent = agent
        old = session.response_task = asyncio.create_task(asyncio.sleep(30))
        session.delivery = Delivery()
        task = PipelineTask(
            Pipeline([capture, agent, output]), enable_rtvi=False, idle_timeout_secs=0
        )
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        try:
            await asyncio.wait_for(output.started.wait(), 2)
            await task.queue_frame(VADUserStartedSpeakingFrame())
            async with asyncio.timeout(0.5):
                while not old.done():
                    await asyncio.sleep(0.01)
            assert old.cancelled()
            assert not capture.overlap
            await task.queue_frame(VADUserStoppedSpeakingFrame())
        finally:
            await task.cancel()
            await runner
            old.cancel()
            with suppress(asyncio.CancelledError):
                await old

    asyncio.run(run())


def test_pause_resume_keeps_both_fragments_in_database_and_agent_context(
    client, factory, settings, monkeypatch
):
    sign_in(client)
    user_id = UUID(client.get("/me").json()["id"])
    conversation_id, token = UUID(start(client)), uuid4()
    store.acquire(factory, user_id, conversation_id, token)

    async def run():
        session = VoiceSession(factory, settings, user_id, conversation_id, "", token)
        capture, agent, output = CaptureTurn(session), AgentOutput(), Probe()
        session.agent = agent
        payloads = []
        accepted = []
        generated = asyncio.Event()

        def event(kind, **values):
            if kind == "user_turn":
                saved = service.get_conversation(factory, user_id, conversation_id)["messages"]
                assert any(
                    str(message["id"]) == values["message_id"]
                    and message["content"] == values["text"]
                    for message in saved
                )
                accepted.append(values)

        monkeypatch.setattr(session, "event", event)

        async def pending_reply(payload, fixed):
            payloads.append(payload)
            generated.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(session, "_respond", pending_reply)
        task = PipelineTask(
            Pipeline([capture, agent, output]), enable_rtvi=False, idle_timeout_secs=0
        )
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        first = "Basically मैं client meeting में था"
        second = "और manager ने salary कम करने को कहा"
        try:
            await asyncio.wait_for(output.started.wait(), 2)
            await session.start_response(text=first)
            await asyncio.wait_for(generated.wait(), 2)
            old = session.response_task
            await task.queue_frame(VADUserStartedSpeakingFrame())
            await task.queue_frame(TranscriptionFrame(second, "user", "now"))
            async with asyncio.timeout(2):
                while not any(isinstance(f, TranscriptionFrame) for f in output.frames):
                    await asyncio.sleep(0.01)
            generated.clear()
            await agent.push_frame(UserStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
            await asyncio.wait_for(generated.wait(), 2)
            assert old.cancelled()
            assert [m["content"] for m in payloads[-1]["transcript"] if m["role"] == "user"] == [
                first,
                second,
            ]
            saved = service.get_conversation(factory, user_id, conversation_id)["messages"]
            assert [m["content"] for m in saved if m["role"] == "user"] == [first, second]
            assert [event["text"] for event in accepted] == [first, second]
        finally:
            await session.interrupt()
            await task.cancel()
            await runner
            store.release(factory, user_id, conversation_id, token)

    asyncio.run(run())
