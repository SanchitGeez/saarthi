"""Bounded STT recovery instead of the pinned adapter's unlimited retry loop."""

import asyncio
import random

from deepgram.core.events import EventType
from httpx import TransportError
from pipecat.services.deepgram.stt import DeepgramSTTService
from websockets.exceptions import ConnectionClosed


def transient(exc):
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in {408, 429, 500, 502, 503, 504} or (
        status is None
        and isinstance(
            exc, (OSError, ConnectionError, TimeoutError, TransportError, ConnectionClosed)
        )
    )


class BoundedDeepgram(DeepgramSTTService):
    def __init__(self, session, **kwargs):
        super().__init__(**kwargs)
        self.session = session

    async def _connection_handler(self):
        for attempt in range(4):
            try:
                async with self._client.listen.v1.connect(
                    **self._build_connect_kwargs()
                ) as connection:
                    self._connection = connection
                    connection.on(EventType.MESSAGE, self._on_message)
                    connection.on(EventType.ERROR, self._on_error)
                    keepalive = self.create_task(self._keepalive_handler())
                    self.session.event("listening")
                    try:
                        await connection.start_listening()
                    finally:
                        await self.cancel_task(keepalive)
                    raise ConnectionError("STT stream closed")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connection = None
                self.session.capture.parts.clear()
                if not transient(exc) or attempt == 3:
                    self.session.event(
                        "ended",
                        message="Speech recognition failed. Reconnect or type.",
                    )
                    asyncio.create_task(self.session.close(notify=False))
                    return
                self.session.event(
                    "retrying",
                    attempt=attempt + 1,
                    text=self.session.heard,
                    message="Speech recognition reconnecting. Please repeat your last words.",
                )
                await asyncio.sleep(2**attempt + random.uniform(0, 0.25))
            finally:
                self._connection = None

    async def _on_error(self, error):
        # No raw provider messages in logs or pipeline ErrorFrames.
        self.session.event(
            "error",
            message="Speech recognition connection failed. You may need to repeat your words.",
        )
