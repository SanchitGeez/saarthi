"""Small adapter over the pinned official integration for timing and backpressure."""

import asyncio
import json

from pipecat_murf_tts import MurfTTSService

from voice.deepgram import transient


class TimedMurf(MurfTTSService):
    def __init__(self, session, **kwargs):
        super().__init__(reconnect_on_error=False, **kwargs)
        self.session = session
        self.contexts = {}
        self.audio_seconds = {}

    def _build_voice_config_message(self, text, context_id, is_last=False):
        self.contexts = {
            key: value for key, value in self.contexts.items() if value == self.session.response_id
        }
        self.contexts[context_id] = self.session.response_id
        result = super()._build_voice_config_message(text, context_id, is_last)
        result["add_word_timestamps"] = True
        result["predictive_chunking"] = "lenient"
        return result

    async def _process_json_message(self, data):
        context_id = data.get("context_id")
        if (
            not self.session.response_id
            or self.contexts.get(context_id) != self.session.response_id
        ):
            return
        timings = data.get("timestamps")
        if timings and self.session.delivery:
            try:
                self.session.delivery.timestamps(
                    [w["word"] for w in timings["words"]], [w["end_s"] for w in timings["words"]]
                )
            except (KeyError, TypeError, ValueError):
                self.session.delivery.aligned = False
        # Timestamp-only messages are handled above; avoid provider payload logging.
        if "error" in data:
            error = data.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            self.session.provider_failure(code in {408, 429, 500, 502, 503, 504})
            return
        if "audio" in data or data.get("final"):
            await super()._process_json_message(data)
        if data.get("final"):
            self.audio_seconds.pop(context_id, None)

    async def _process_audio_data_to_context(self, context_id, audio_data):
        generation = self.contexts.get(context_id)
        if not generation or generation != self.session.response_id or not self.session.delivery:
            return
        for offset in range(0, len(audio_data), 24000):
            chunk = audio_data[offset : offset + 24000]
            seconds = self.audio_seconds.get(context_id, 0) + len(chunk) / 48000
            self.audio_seconds[context_id] = seconds
            if seconds > 120:
                self.session.provider_failure(False)
                return
            # Bound synthesized lead to 5s, including a large provider audio frame.
            while seconds - self.session.delivery.sent_seconds > 5:
                if generation != self.session.response_id or self.session.closed:
                    return
                await asyncio.sleep(0.02)
            await super()._process_audio_data_to_context(context_id, chunk)

    async def push_error(self, error_msg, exception=None, fatal=False):
        self.session.provider_failure(transient(exception) if exception else False)

    async def run_tts(self, text, context_id):
        try:
            if not self._websocket:
                await self._connect()
            if not self._websocket:
                return
            message = self._build_voice_config_message(text, context_id)
            await self._websocket.send(json.dumps(message))
        except Exception as exc:
            self.session.provider_failure(transient(exc))
        # Async generator interface required by Pipecat; audio arrives via receive task.
        yield None

    async def _receive_messages(self):
        # The official adapter reconnects forever here; recovery belongs to the turn.
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
