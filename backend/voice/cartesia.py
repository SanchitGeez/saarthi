"""Cartesia streaming with delivery timing, output fences and bounded recovery."""

import asyncio
import base64
import json

from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame
from pipecat.services.cartesia.tts import CartesiaTTSService
from websockets.protocol import State

from voice.deepgram import transient


class TimedCartesia(CartesiaTTSService):
    def __init__(self, session, **kwargs):
        super().__init__(reconnect_on_error=False, cartesia_version="2026-03-01", **kwargs)
        self.session = session
        self.contexts = {}
        self.audio_seconds = {}

    def _build_msg(self, text="", continue_transcript=True, add_timestamps=True, context_id=""):
        self.contexts = {
            key: value for key, value in self.contexts.items() if value == self.session.response_id
        }
        self.audio_seconds = {
            key: value for key, value in self.audio_seconds.items() if key in self.contexts
        }
        self.contexts[context_id] = self.session.response_id
        return super()._build_msg(text, continue_transcript, add_timestamps, context_id)

    async def _process_json_message(self, data):
        context_id = data.get("context_id")
        generation = self.contexts.get(context_id)
        if data.get("type") == "error" and not context_id:
            self.session.provider_failure(data.get("status_code") in {408, 429, 500, 502, 503, 504})
            return
        if (
            not generation
            or generation != self.session.response_id
            or not self.audio_context_available(context_id)
        ):
            return
        if data["type"] == "timestamps":
            timings = data.get("word_timestamps")
            if timings and self.session.delivery:
                try:
                    self.session.delivery.timestamps(timings["words"], timings["end"])
                except (KeyError, TypeError, ValueError):
                    self.session.delivery.aligned = False
            # Captions use the original agent text; provider timings only track delivery.
        elif data["type"] == "chunk":
            audio = base64.b64decode(data["data"])
            for offset in range(0, len(audio), 24000):
                if (
                    generation != self.session.response_id
                    or self.session.closed
                    or not self.session.delivery
                ):
                    return
                chunk = audio[offset : offset + 24000]
                seconds = self.audio_seconds.get(context_id, 0) + len(chunk) / 48000
                self.audio_seconds[context_id] = seconds
                if seconds > 120:
                    self.session.provider_failure(False)
                    return
                while seconds - self.session.delivery.sent_seconds > 5:
                    await asyncio.sleep(0.02)
                    if (
                        generation != self.session.response_id
                        or self.session.closed
                        or not self.session.delivery
                    ):
                        return
                await self.append_to_audio_context(
                    context_id,
                    TTSAudioRawFrame(
                        audio=chunk,
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    ),
                )
        elif data["type"] == "done":
            await self.stop_ttfb_metrics()
            await self.append_to_audio_context(context_id, TTSStoppedFrame(context_id=context_id))
            await self.remove_audio_context(context_id)
            self.audio_seconds.pop(context_id, None)
        elif data["type"] == "error":
            self.session.provider_failure(data.get("status_code") in {408, 429, 500, 502, 503, 504})

    async def _process_messages(self):
        async for message in self._get_websocket():
            await self._process_json_message(json.loads(message))

    async def push_error(self, error_msg, exception=None, fatal=False):
        self.session.provider_failure(transient(exception) if exception else False)

    async def run_tts(self, text, context_id):
        try:
            if not self._websocket or self._websocket.state is State.CLOSED:
                await self._connect()
            if not self._websocket:
                return
            await self._websocket.send(self._build_msg(text=text, context_id=context_id))
            await self.start_tts_usage_metrics(text)
        except Exception as exc:
            self.session.provider_failure(transient(exc))
        yield None

    async def _receive_messages(self):
        # Turn-level recovery owns retries instead of the adapter's unlimited loop.
        await self._process_messages()
        if not self._disconnecting:
            self.session.provider_failure(True)

    async def _receive_task_handler(self, report_error):
        try:
            await self._receive_messages()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.session.provider_failure(transient(exc))
