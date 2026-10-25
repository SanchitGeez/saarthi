import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("pipecat")

from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame
from pipecat.transcriptions.language import Language

from config import Settings
from voice.cartesia import TimedCartesia
from voice.policy import Delivery


def make_tts():
    session = SimpleNamespace(
        response_id="one",
        delivery=Delivery(text="Haan bolo"),
        closed=False,
        provider_failure=lambda retryable: None,
    )
    tts = TimedCartesia(
        session,
        api_key="test",
        sample_rate=24000,
        settings=TimedCartesia.Settings(
            voice=Settings(_env_file=None).cartesia_voice_id,
            model="sonic-3",
            language=Language.HI,
        ),
    )
    tts._sample_rate = tts._output_sample_rate = 24000
    tts._serialization_queue = asyncio.Queue()
    return session, tts


def test_cartesia_request_timing_audio_and_stale_generation():
    async def run():
        session, tts = make_tts()
        try:
            request = json.loads(tts._build_msg(text="Haan bolo", context_id="context"))
            assert request["voice"] == {
                "mode": "id",
                "id": "4877b818-c7fe-4c89-b1cf-eadf8e23da72",
            }
            assert request["model_id"] == "sonic-3"
            assert request["language"] == "hi"
            assert request["continue"] is True
            assert request["add_timestamps"] is True
            assert request["output_format"] == {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            }
            await tts.create_audio_context("context")
            timings = {
                "type": "timestamps",
                "context_id": "context",
                "word_timestamps": {"words": ["Haan", "bolo"], "end": [0.2, 0.7]},
            }
            await tts._process_json_message(timings)
            assert session.delivery.words == [(0.2, 4), (0.7, 9)]
            audio = {
                "type": "chunk",
                "context_id": "context",
                "data": base64.b64encode(bytes(48000)).decode(),
            }
            await tts._process_json_message(audio)
            queue = tts._audio_contexts["context"]
            frames = [queue.get_nowait(), queue.get_nowait()]
            assert all(isinstance(f, TTSAudioRawFrame) and f.sample_rate == 24000 for f in frames)
            assert sum(len(f.audio) for f in frames) == 48000
            await tts._process_json_message({"type": "done", "context_id": "context"})
            assert isinstance(queue.get_nowait(), TTSStoppedFrame)
            assert queue.get_nowait() is None
            assert "context" not in tts.audio_seconds
            session.response_id = "two"
            await tts._process_json_message(timings)
            await tts._process_json_message(audio)
            assert session.delivery.aligned
            assert queue.empty()
            session.response_id = None
            await tts._process_json_message(timings)
            assert session.delivery.aligned
        finally:
            await tts.cleanup()

    asyncio.run(run())


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False), (400, False)])
def test_cartesia_errors_use_turn_recovery(status, retryable):
    async def run():
        session, tts = make_tts()
        failures = []
        session.provider_failure = failures.append
        try:
            tts._build_msg(context_id="context")
            await tts.create_audio_context("context")
            error = {"type": "error", "status_code": status, "context_id": "context"}
            await tts._process_json_message(error)
            assert failures == [retryable]
            session.response_id = "two"
            await tts._process_json_message(error)
            assert failures == [retryable]
            await tts._process_json_message({"type": "error", "status_code": status})
            assert failures == [retryable, retryable]
        finally:
            await tts.cleanup()

    asyncio.run(run())


def test_cartesia_audio_limit_and_interruption_during_backpressure():
    async def run():
        session, tts = make_tts()
        failures = []
        session.provider_failure = failures.append
        try:
            tts._build_msg(context_id="context")
            await tts.create_audio_context("context")
            audio = {
                "type": "chunk",
                "context_id": "context",
                "data": base64.b64encode(bytes(24000)).decode(),
            }
            tts.audio_seconds["context"] = 120
            await tts._process_json_message(audio)
            assert failures == [False]
            tts.audio_seconds["context"] = 5
            blocked = asyncio.create_task(tts._process_json_message(audio))
            await asyncio.sleep(0.04)
            assert not blocked.done()
            session.response_id = "two"
            session.delivery = None
            await asyncio.wait_for(blocked, 1)
            assert tts._audio_contexts["context"].empty()
        finally:
            await tts.cleanup()

    asyncio.run(run())


def test_cartesia_send_failure_does_not_reconnect_outside_turn_recovery():
    async def run():
        session, tts = make_tts()
        failures = []
        session.provider_failure = failures.append
        tts._websocket = SimpleNamespace(state=None, send=AsyncMock(side_effect=OSError()))
        tts._connect = AsyncMock()
        try:
            assert [value async for value in tts.run_tts("Haan bolo", "context")] == [None]
            assert failures == [True]
            tts._connect.assert_not_awaited()
        finally:
            await tts.cleanup()

    asyncio.run(run())
