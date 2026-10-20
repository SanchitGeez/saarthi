"""One coordinator owns response cancellation, retries, delivery and live lifecycle."""

import asyncio
import random
from contextlib import suppress
from time import monotonic
from uuid import uuid4

from agents import saarthi
from agents.runner import AgentFailure
from core import service
from core.errors import Problem
from voice import store
from voice.policy import Delivery


class VoiceSession:
    def __init__(self, factory, settings, user_id, conversation_id, auth_hash, token):
        self.factory, self.settings = factory, settings
        self.user_id, self.conversation_id = user_id, conversation_id
        self.auth_hash, self.token = auth_hash, token
        self.closed = False
        self.connected = False
        self.started = monotonic()
        self.activity = self.started
        self.checked_in = False
        self.response_id = None
        self.delivery = None
        self.heard = ""
        self.message_id = None
        self.notice_id = None
        self.response_task = None
        self.pipeline_task = self.runner_task = self.watch_task = None
        self.connection = self.agent = self.tts = None
        self.done = asyncio.Event()
        self.failure = None
        self.ready_once = False
        self.resume = False
        self.lock = asyncio.Lock()

    def event(self, kind, **values):
        if self.connection and not self.closed:
            # A closed data channel must not prevent cancellation or lease release.
            with suppress(Exception):
                self.connection.send_app_message({"type": "voice", "event": kind, **values})

    def provider_failure(self, retryable=False):
        self.failure = retryable
        self.done.set()

    async def ready(self):
        if self.ready_once or self.closed:
            return
        self.ready_once = True
        self.connected = True
        self.activity = monotonic()
        if self.resume:
            self.event("listening")
            return
        saved = service.get_conversation(self.factory, self.user_id, self.conversation_id)
        greeting = saved["messages"][0]["content"] if len(saved["messages"]) == 1 else "Haan, bolo…"
        # Existing text messages have already been delivered in the text UI; don't rewrite them.
        await self.start_response(fixed=greeting, notice=len(saved["messages"]) != 1)

    async def start_response(self, text=None, fixed=None, notice=False):
        async with self.lock:
            if self.closed:
                return
            await self._interrupt()
            self.activity = monotonic()
            if text:
                self.checked_in = False
            self.message_id = uuid4() if text else None
            self.notice_id = uuid4() if notice else None
            payload = (
                store.prepare(
                    self.factory,
                    self.user_id,
                    self.conversation_id,
                    self.token,
                    text,
                    self.message_id,
                )
                if text
                else None
            )
            self.heard = ""
            self.response_task = asyncio.create_task(self._respond(payload, fixed))

    async def interrupt(self):
        async with self.lock:
            await self._interrupt()

    async def _clear_output(self):
        self.event("clear", response_id=self.response_id)
        self.response_id = None  # Fence provider callbacks before cancelling queues.
        if self.agent:
            await self.agent.broadcast_interruption()
            # Let downstream system-frame handlers flush before accepting a new response.
            await asyncio.sleep(0.05)

    async def _interrupt(self):
        task = self.response_task
        if task and not task.done():
            self._remember_prefix()
            await self._clear_output()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            self._save(True)
        self.response_task = None
        self.delivery = None
        self.message_id = None
        self.notice_id = None
        self.heard = ""

    def _remember_prefix(self):
        prefix = self.delivery.prefix() if self.delivery else ""
        self.heard += prefix

    def _save(self, interrupted):
        if self.message_id or self.notice_id:
            store.commit(
                self.factory,
                self.user_id,
                self.conversation_id,
                self.token,
                self.message_id,
                self.heard,
                interrupted,
                **({"notice_id": self.notice_id} if self.notice_id else {}),
            )
        self.event("final", text=self.heard, interrupted=interrupted)

    async def _respond(self, payload, fixed):
        from pipecat.frames.frames import (
            LLMFullResponseEndFrame,
            LLMFullResponseStartFrame,
            TextFrame,
        )

        remaining = fixed
        model_complete = fixed is not None
        budget_started = monotonic()
        try:
            for attempt in range(4):
                if self.closed:
                    return
                self.response_id = str(uuid4())
                self.delivery = Delivery()
                self.done.clear()
                self.failure = None
                self.event("responding", response_id=self.response_id, prefix=self.heard)
                await self.agent.push_frame(LLMFullResponseStartFrame())
                try:
                    async with asyncio.timeout(
                        min(90, max(0.1, 120 - (monotonic() - budget_started)))
                    ):
                        if model_complete:
                            self.delivery.text = remaining
                            self.event("caption", text=self.heard + remaining)
                            await self.agent.push_frame(TextFrame(remaining))
                        else:
                            continuation = dict(payload)
                            if self.heard:
                                continuation["transcript"] = [
                                    *payload["transcript"],
                                    {
                                        "role": "assistant",
                                        "content": self.heard,
                                        "interrupted": True,
                                    },
                                ]
                                continuation["voice_recovery"] = (
                                    "Continue the interrupted reply without repeating the delivered prefix."
                                )
                            pending = ""
                            async for chunk in saarthi.stream(self.settings, continuation):
                                if len(self.heard) + len(self.delivery.text) + len(chunk) > 8000:
                                    raise AgentFailure()
                                self.delivery.text += chunk
                                pending += chunk
                                self.event("caption", text=self.heard + self.delivery.text)
                                # Pipecat drops whitespace-only TextFrames; carry spaces into
                                # the next token so spoken words stay separated.
                                if pending.strip():
                                    await self.agent.push_frame(TextFrame(pending))
                                    pending = ""
                                if self.failure is not None:
                                    raise VoiceProviderFailure(self.failure)
                            model_complete = True
                        end = LLMFullResponseEndFrame()
                        end.voice_response_id = self.response_id
                        await self.agent.push_frame(end)
                        await self.done.wait()
                        if self.failure is not None:
                            raise VoiceProviderFailure(self.failure)
                        if self.delivery.sent_seconds <= 0:
                            raise VoiceProviderFailure(True)
                        # Playout estimate: media has drained at real-time pace, allow jitter tail.
                        await asyncio.sleep(0.35)
                        self.heard += self.delivery.text
                        self._save(False)
                        self.response_id = None
                        self.delivery = None
                        self.activity = monotonic()
                        self.event("listening")
                        return
                except (AgentFailure, VoiceProviderFailure, TimeoutError) as exc:
                    prefix = self.delivery.prefix()
                    remaining = self.delivery.text[len(prefix) :] if model_complete else None
                    self.heard += prefix
                    await self._clear_output()
                    self.delivery = None
                    retryable = isinstance(exc, TimeoutError) or getattr(exc, "retryable", False)
                    if not retryable or attempt == 3 or monotonic() - budget_started > 110:
                        self._save(True)
                        self.event(
                            "error",
                            message="Voice reply failed. You can speak again or leave voice and type.",
                        )
                        return
                    delay = 2**attempt + random.uniform(0, 0.25)
                    self.event("retrying", attempt=attempt + 1, delay=delay, text=self.heard)
                    await asyncio.sleep(delay)
                    # Re-open TTS after a broken provider socket; STT remains live.
                    await self.tts._disconnect()
                    await self.tts._connect()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never include provider errors, prompts or audio in UI/logs.
            self._remember_prefix()
            await self._clear_output()
            with suppress(Problem):
                self._save(True)
            self.event("error", message="Voice reply failed. Speak again or reconnect.")
        finally:
            self.response_id = None
            self.delivery = None

    async def watch(self):
        try:
            while not self.closed:
                await asyncio.sleep(2)
                store.renew(
                    self.factory, self.user_id, self.conversation_id, self.token, self.auth_hash
                )
                if (self.message_id or self.notice_id) and self.delivery:
                    prefix = self.heard + self.delivery.prefix()
                    store.commit(
                        self.factory,
                        self.user_id,
                        self.conversation_id,
                        self.token,
                        self.message_id,
                        prefix,
                        True,
                        **({"notice_id": self.notice_id} if self.notice_id else {}),
                    )
                elapsed = monotonic() - self.started
                quiet = monotonic() - self.activity
                if (
                    (not self.connected and elapsed > 20)
                    or elapsed > self.settings.voice_max_seconds
                    or quiet > self.settings.voice_idle_seconds
                ):
                    self.event("ended", message="Voice session ended. Your chat is still here.")
                    await self.close()
                    return
                if (
                    self.connected
                    and not self.response_id
                    and not self.checked_in
                    and quiet > self.settings.voice_checkin_seconds
                ):
                    self.checked_in = True
                    await self.start_response(
                        fixed="Main yahin hoon. Kuch aur kehna chahoge?", notice=True
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            self.event("ended", message="Voice connection expired. Reconnect to continue.")
            await self.close()

    async def close(self, *, notify=True):
        async with self.lock:
            if self.closed:
                return
            # Finalize delivery while the durable lease is still ours.
            with suppress(Problem):
                await self._interrupt()
            if notify:
                self.event("ended", message="Voice disconnected.")
            self.closed = True
            if self.watch_task and self.watch_task is not asyncio.current_task():
                self.watch_task.cancel()
            with suppress(Exception):
                if self.pipeline_task:
                    await self.pipeline_task.cancel()
            with suppress(Exception):
                if self.connection:
                    await self.connection.disconnect()
            with suppress(Problem):
                store.release(self.factory, self.user_id, self.conversation_id, self.token)


class VoiceProviderFailure(Exception):
    def __init__(self, retryable):
        self.retryable = retryable
