"""Pipecat wiring. No independent LLM history or audio recording processors."""

import asyncio
from contextlib import suppress
from time import monotonic

from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.env import env_truthy

from voice.deepgram import BoundedDeepgram as DeepgramSTTService
from voice.murf import TimedMurf
from voice.policy import acknowledgment


class AgentOutput(FrameProcessor):
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class CaptureTurn(FrameProcessor):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.parts = []
        self.overlap = False
        self.fallback = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.UPSTREAM and isinstance(frame, UserStoppedSpeakingFrame):
            await self.finish()
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, VADUserStartedSpeakingFrame):
                self.session.activity = monotonic()
                self.overlap = self.overlap or bool(
                    self.session.response_task and not self.session.response_task.done()
                )
                if self.fallback:
                    self.fallback.cancel()
                self.fallback = asyncio.create_task(self._fallback())
            elif isinstance(frame, (VADUserStoppedSpeakingFrame, EndFrame, CancelFrame)):
                if self.fallback:
                    self.fallback.cancel()
                    self.fallback = None
            elif isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
                self.session.activity = monotonic()
                self.overlap = self.overlap or bool(
                    self.session.response_task and not self.session.response_task.done()
                )
                self.session.event(
                    "transcript",
                    text=" ".join([*self.parts, frame.text]),
                    final=isinstance(frame, TranscriptionFrame),
                )
                if (
                    self.session.response_task
                    and not self.session.response_task.done()
                    and not acknowledgment(" ".join([*self.parts, frame.text]))
                ):
                    await self.session.interrupt()
                if isinstance(frame, TranscriptionFrame):
                    self.parts.append(frame.text)
                    if len(" ".join(self.parts)) > 4000:
                        self.parts.clear()
                        self.session.event(
                            "error",
                            message="That turn is too long. Please say it in smaller parts.",
                        )
        await self.push_frame(frame, direction)

    async def _fallback(self):
        await asyncio.sleep(1.2)
        await self.session.interrupt()

    async def finish(self):
        text = " ".join(self.parts).strip()
        self.parts.clear()
        overlap, self.overlap = self.overlap, False
        if not text or (overlap and acknowledgment(text)):
            return
        await self.session.start_response(text=text)

    async def cleanup(self):
        if self.fallback:
            self.fallback.cancel()
            with suppress(asyncio.CancelledError):
                await self.fallback
        await super().cleanup()


class OutputFence(FrameProcessor):
    def __init__(self, session):
        super().__init__()
        self.session = session

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            context_id = getattr(frame, "context_id", None)
            if context_id and (
                not self.session.response_id
                or self.session.tts.contexts.get(context_id) != self.session.response_id
            ):
                return
        await self.push_frame(frame, direction)


class Delivered(FrameProcessor):
    def __init__(self, session):
        super().__init__()
        self.session = session

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, OutputAudioRawFrame) and self.session.delivery:
                self.session.delivery.sent_seconds += len(frame.audio) / (
                    frame.sample_rate * frame.num_channels * 2
                )
            elif isinstance(frame, LLMFullResponseEndFrame):
                if getattr(frame, "voice_response_id", None) == self.session.response_id:
                    self.session.done.set()
            elif isinstance(frame, ErrorFrame):
                # STT transport errors require reconnect: missing speech cannot be replayed.
                self.session.event(
                    "error",
                    message="Audio service failed. Reconnecting may require repeating your last words.",
                )
                self.session.event("reconnect")
                asyncio.create_task(self.session.close(notify=False))
        await self.push_frame(frame, direction)


async def build(session, connection):
    # Libraries emit raw text/payloads at debug level. Disable their namespaces entirely.
    logger.disable("pipecat")
    logger.disable("pipecat_murf_tts")
    if env_truthy("PIPECAT_SMART_TURN_LOG_DATA"):
        raise ValueError("Audio debug recording must be disabled.")
    transport = SmallWebRTCTransport(
        connection,
        TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            audio_out_10ms_chunks=2,
            audio_out_end_silence_secs=0,
        ),
    )
    stt = DeepgramSTTService(
        session,
        api_key=session.settings.deepgram_api_key,
        mip_opt_out=True,
        settings=DeepgramSTTService.Settings(
            model="nova-3",
            language="multi",
            endpointing=False,
            interim_results=True,
            punctuate=True,
            vad_events=False,
        ),
    )
    capture = CaptureTurn(session)
    session.capture = capture
    turn = UserTurnProcessor(
        user_turn_strategies=UserTurnStrategies(
            start=[
                VADUserTurnStartStrategy(enable_interruptions=False),
                TranscriptionUserTurnStartStrategy(enable_interruptions=False),
            ],
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=2.5))
                )
            ],
        )
    )
    agent = AgentOutput()
    tts = TimedMurf(
        session,
        api_key=session.settings.murf_api_key,
        params=TimedMurf.InputParams(
            voice_id=session.settings.murf_voice_id,
            model="falcon-2",
            sample_rate=24000,
            format="PCM",
            style="Conversational",
        ),
        text_aggregation_mode=TextAggregationMode.TOKEN,
    )
    session.agent, session.tts, session.connection = agent, tts, connection
    pipeline = Pipeline(
        [
            transport.input(),
            VADProcessor(vad_analyzer=SileroVADAnalyzer()),
            stt,
            capture,
            turn,
            agent,
            tts,
            OutputFence(session),
            transport.output(),
            Delivered(session),
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        idle_timeout_secs=0,
    )
    session.pipeline_task = task

    @transport.event_handler("on_client_disconnected")
    async def disconnected(_transport, _connection):
        if not session.closed:
            session.event("reconnect")
            await session.close(notify=False)

    @transport.event_handler("on_app_message")
    async def message(_transport, body, _sender):
        if not isinstance(body, dict):
            return
        if body.get("type") == "ready":
            await session.ready()
        elif body.get("type") == "stop":
            await session.interrupt()

    async def run():
        try:
            await PipelineRunner(handle_sigint=False).run(task)
        finally:
            await session.close()

    session.runner_task = asyncio.create_task(run())
    session.watch_task = asyncio.create_task(session.watch())
    return session
