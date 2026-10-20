"""Local WebRTC integration with synthetic audio and fake provider boundaries."""

import asyncio
import json
from uuid import uuid4

import pytest

pytest.importorskip("pipecat")

from aiortc import AudioStreamTrack, RTCPeerConnection
from pipecat.frames.frames import LLMFullResponseStartFrame, TextFrame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameProcessor

from agents import saarthi
from config import Settings
from core import service
from voice import pipeline, store
from voice.session import VoiceSession


class FakeSTT(FrameProcessor):
    Settings = pipeline.DeepgramSTTService.Settings

    def __init__(self, session, **kwargs):
        super().__init__()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class FakeTTS(FrameProcessor):
    InputParams = pipeline.TimedMurf.InputParams

    def __init__(self, session, **kwargs):
        super().__init__()
        self.session = session
        self.contexts = {}

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseStartFrame):
            self.contexts["test"] = self.session.response_id
        if type(frame) is TextFrame:
            audio = TTSAudioRawFrame(
                audio=bytes(24000), sample_rate=24000, num_channels=1, context_id="test"
            )
            await self.push_frame(audio)
        else:
            await self.push_frame(frame, direction)


def test_browser_peer_receives_audio_and_final_caption(monkeypatch):
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

    monkeypatch.setattr(pipeline, "DeepgramSTTService", FakeSTT)
    monkeypatch.setattr(pipeline, "TimedMurf", FakeTTS)
    monkeypatch.setattr(
        service,
        "get_conversation",
        lambda *args: {"messages": [{"content": "Haan bolo"}]},
    )
    saved = []
    monkeypatch.setattr(store, "prepare", lambda *args: {"transcript": []})
    monkeypatch.setattr(store, "commit", lambda *args, **kwargs: saved.append(args[-2:]))

    async def reply(*args):
        yield "Batao kya hua."

    monkeypatch.setattr(saarthi, "stream", reply)
    monkeypatch.setattr(store, "renew", lambda *args: None)
    monkeypatch.setattr(store, "release", lambda *args: None)

    async def run():
        peer = RTCPeerConnection()
        peer.addTrack(AudioStreamTrack())
        channel = peer.createDataChannel("saarthi")
        final = asyncio.Event()
        events = []
        remote = None

        @channel.on("open")
        def opened():
            channel.send(json.dumps({"type": "ready"}))

        @channel.on("message")
        def message(raw):
            value = json.loads(raw)
            events.append(value)
            if value.get("event") == "final":
                final.set()

        @peer.on("track")
        def track(value):
            nonlocal remote
            remote = value

        connection = SmallWebRTCConnection(ice_servers=[])
        session = VoiceSession(
            None,
            Settings(
                _env_file=None, deepgram_api_key="test", murf_api_key="test", murf_voice_id="test"
            ),
            uuid4(),
            uuid4(),
            "",
            uuid4(),
        )
        try:
            await peer.setLocalDescription(await peer.createOffer())
            await connection.initialize(peer.localDescription.sdp, "offer")
            await pipeline.build(session, connection)
            answer = connection.get_answer()
            from aiortc import RTCSessionDescription

            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            await asyncio.wait_for(final.wait(), 15)
            assert remote is not None
            frame = await asyncio.wait_for(remote.recv(), 2)
            assert frame.sample_rate == 48000
            assert any(e.get("event") == "final" and e["text"] == "Haan bolo" for e in events)
            # Exercise accepted STT -> turn completion -> agent -> TTS -> persistence.
            from pipecat.frames.frames import (
                TranscriptionFrame,
                VADUserStartedSpeakingFrame,
                VADUserStoppedSpeakingFrame,
            )

            final.clear()
            await session.pipeline_task.queue_frame(VADUserStartedSpeakingFrame())
            await asyncio.sleep(0.1)
            await session.pipeline_task.queue_frame(
                TranscriptionFrame("office mein dikkat hui", "user", "now")
            )
            await asyncio.sleep(0.1)
            await session.pipeline_task.queue_frame(VADUserStoppedSpeakingFrame())
            await asyncio.wait_for(final.wait(), 12)
            assert any(e.get("event") == "final" and e["text"] == "Batao kya hua." for e in events)
            assert ("Batao kya hua.", False) in saved
        finally:
            await session.close()
            await peer.close()
            if session.runner_task:
                await asyncio.wait_for(session.runner_task, 5)

    asyncio.run(run())
