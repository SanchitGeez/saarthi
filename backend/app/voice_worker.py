"""Run with: python -m app.voice_worker dev (or start in production)."""
import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from livekit import agents, api, rtc
from livekit.agents import Agent, AgentServer, AgentSession, APIConnectOptions, TurnHandlingOptions, function_tool, llm, room_io
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents.voice.agent_session import SessionConnectOptions
from sqlalchemy import select

from app.config import settings
from app.providers import build_llm, build_stt, build_tts, missing_credentials
from app.continuity import continuity_context, voice_instructions, OPENING_INSTRUCTIONS
from app.db import SessionLocal
from app.models import Conversation, User, VoiceSession
from app.scripture import verse_payload, VERSES
from app.voice_sessions import ACTIVE, expired, participant_identity, record_message, remember_from_voice

logger = logging.getLogger(__name__)
def prewarm(proc):
    # Warm local VAD and imports before accepting a call.
    from huggingface_hub import hf_hub_download
    proc.userdata['vad'] = silero.VAD.load()
    # Load selected provider imports off the call's latency path.
    if settings.llm_provider == "openrouter":
        from livekit.plugins import openai
    else:
        from livekit.plugins import google

server = AgentServer(setup_fnc=prewarm, num_idle_processes=1, initialize_process_timeout=30)


async def load_context(session_id):
    async with SessionLocal() as db:
        call = await db.get(VoiceSession, session_id)
        if not call or call.status not in ACTIVE or call.expires_at <= datetime.now(UTC):
            return None
        user = await db.get(User, call.user_id)
        conversation = await db.get(Conversation, call.conversation_id)
        if not user or not conversation or conversation.user_id != user.id:
            return None
        return user.language, await continuity_context(db, user, conversation)


class Parth(Agent):
    def __init__(self, session_id, language, context, user_spoke):
        super().__init__(instructions=voice_instructions(language, context))
        self.session_id = session_id
        self.user_spoke = user_spoke

    async def on_user_turn_completed(self, turn_ctx, new_message):
        self.user_spoke.set()
        context = await load_context(self.session_id)
        if context is None:
            raise agents.StopResponse()
        instructions = voice_instructions(*context)
        await self.update_instructions(instructions)
        # LiveKit gives this hook a copy made before update_instructions.
        # Refresh that copy too, so this turn receives current privacy/context.
        for item in turn_ctx.items:
            if isinstance(item, llm.ChatMessage) and item.role == 'system':
                item.content = [instructions]
                break
        source_id = await record_message(self.session_id, new_message.id, 'user',
            new_message.text_content or '', new_message.created_at)
        if source_id:
            turn_ctx.add_message(role='system', content=f'Current user transcript source_message_id: {source_id}. Use only this ID as evidence when remembering this turn. Before answering the question, honor any explicit safe request to remember a fact by calling remember_detail with an exact quote from the current transcript.')

    @function_tool
    async def get_gita_verse(self, reference: str):
        """Retrieve verified Sanskrit and English/Hindi renderings. Only 2.14, 2.47, 2.48, 6.5, 6.26, 12.13 are available."""
        if not await load_context(self.session_id):
            return {'found': False, 'reason': 'Call ended.'}
        verse = verse_payload(reference)
        return {'found': bool(verse), **(verse or {'available': list(VERSES)})}

    @function_tool
    async def remember_detail(self, source_message_id: str, content: str, kind: str,
                              evidence: str, memory_id: str = ''):
        """Remember one safe lasting fact with an exact quote from the current user transcript. Optional memory_id corrects a previously saved fact."""
        try:
            source = UUID(source_message_id)
            correction = UUID(memory_id) if memory_id else None
        except ValueError:
            return {'saved': False, 'reason': 'Invalid evidence ID.'}
        return await remember_from_voice(self.session_id, source, content, kind, evidence, correction)


@server.rtc_session(agent_name=settings.livekit_agent_name)
async def parth_call(ctx: agents.JobContext):
    try:
        session_id = UUID(json.loads(ctx.job.metadata)['session_id'])
    except (ValueError, KeyError, TypeError):
        return
    async with SessionLocal() as db:
        call = await db.scalar(select(VoiceSession).where(VoiceSession.id == session_id).with_for_update())
        if (not call or call.room_name != ctx.job.room.name or call.status not in ACTIVE or
                expired(call, datetime.now(UTC)) or call.worker_claimed):
            return
        call.worker_claimed = True
        expected_identity = participant_identity(call)
        deadline = call.expires_at
        await db.commit()

    session = None
    ready = asyncio.Event()
    user_spoke = asyncio.Event()
    finished = asyncio.Event()
    queue = asyncio.Queue()
    last_activity = time.monotonic()
    terminal_error = False

    async def writer():
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                await record_message(session_id, item.id, item.role,
                    item.text_content or '', item.created_at, item.interrupted)
            except Exception as exc:
                # Persistence failure is visible as a failed call, not silently lost history.
                logger.warning('Voice transcript write failed (%s)', type(exc).__name__)
                finished.set()
            finally:
                queue.task_done()

    write_task = asyncio.create_task(writer())
    async def finish():
        nonlocal session
        if session:
            await session.aclose()
        await queue.join()
        await queue.put(None)
        await write_task
        async with SessionLocal() as db:
            call = await db.scalar(select(VoiceSession).where(VoiceSession.id == session_id).with_for_update())
            if call:
                call.status, call.ended_at = 'ended', datetime.now(UTC)
                await db.commit()
        try:
            await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))
        except Exception:
            # Empty room timeout and the API's retryable end endpoint cover teardown failures.
            logger.warning('Voice room teardown delayed')

    ctx.add_shutdown_callback(finish)
    try:
        await ctx.connect()
        @ctx.room.on('disconnected')
        def disconnected(reason):
            finished.set()
            ready.set()
        @ctx.room.local_participant.register_rpc_method('saarthi.ready')
        async def client_ready(data: rtc.RpcInvocationData):
            if data.caller_identity != expected_identity:
                raise rtc.RpcError(1500, 'Unexpected participant.')
            logger.info('Voice client audio ready')
            ready.set()
            return 'ready'


        async with asyncio.timeout(30):
            await ctx.wait_for_participant(identity=expected_identity)
        context = await load_context(session_id)
        if not context:
            return
        session = AgentSession(
            stt=build_stt(context[0]),
            llm=build_llm(),
            conn_options=SessionConnectOptions(llm_conn_options=APIConnectOptions(max_retry=0, timeout=12),
                stt_conn_options=APIConnectOptions(max_retry=1, timeout=10),
                tts_conn_options=APIConnectOptions(max_retry=1, timeout=10)),
            tts=build_tts(),
            vad=ctx.proc.userdata["vad"],
            turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel(),
                endpointing={"min_delay": 0.5, "max_delay": 3.0}, preemptive_generation={"enabled": False}),
            user_away_timeout=None,
        )
        @session.on('conversation_item_added')
        def item_added(event):
            nonlocal last_activity
            last_activity = time.monotonic()
            if isinstance(event.item, llm.ChatMessage):
                queue.put_nowait(event.item.model_copy(deep=True))

        @session.on('user_state_changed')
        def user_state(event):
            nonlocal last_activity
            if event.new_state == 'speaking':
                user_spoke.set()
                last_activity = time.monotonic()

        @session.on('error')
        def error(event):
            nonlocal terminal_error
            if not event.error.recoverable:
                terminal_error = True
                finished.set()

        @session.on('close')
        def closed(event):
            finished.set()

        await session.start(agent=Parth(session_id, *context, user_spoke), room=ctx.room,
            room_options=room_io.RoomOptions(participant_identity=expected_identity,
                text_input=False, video_input=False, close_on_disconnect=False), record=False)
        async with SessionLocal() as db:
            call = await db.scalar(select(VoiceSession).where(VoiceSession.id == session_id).with_for_update())
            if not call or call.status not in ACTIVE:
                return
            call.status = 'active'
            await db.commit()
        async with asyncio.timeout(30):
            await ready.wait()  # client has audio output, microphone, and bell ready
        async with SessionLocal() as db:
            call = await db.scalar(select(VoiceSession).where(VoiceSession.id == session_id).with_for_update())
            if not call or call.status not in ACTIVE:
                return
            greet = not call.greeting_claimed and not user_spoke.is_set()
            call.greeting_claimed = True
            await db.commit()
        if greet:
            session.generate_reply(instructions=OPENING_INSTRUCTIONS)
        while not finished.is_set():
            if datetime.now(UTC) >= deadline or time.monotonic() - last_activity > settings.voice_idle_seconds:
                break
            async with SessionLocal() as db:
                call = await db.get(VoiceSession, session_id)
                if not call or call.status not in ACTIVE:
                    break
            try:
                await asyncio.wait_for(finished.wait(), timeout=2)
            except TimeoutError:
                pass
    except Exception as exc:
        terminal_error = True
        logger.warning('Parth call failed (%s)', type(exc).__name__)
    finally:
        if terminal_error and ctx.room.isconnected():
            try:
                await ctx.room.local_participant.publish_data(
                    json.dumps({'error': 'Parth couldn’t complete the call. Please try again or use Type.'}).encode(),
                    reliable=True, topic='saarthi.error', destination_identities=[expected_identity])
            except Exception:
                pass
        # Callback also runs on worker shutdown. JobContext callbacks run once.
        ctx.shutdown(reason='Call finished')


if __name__ == '__main__':
    if not settings.livekit_url or not settings.livekit_api_key or not settings.livekit_api_secret:
        raise SystemExit('Configure LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET first.')
    if missing_credentials():
        raise SystemExit('Missing selected provider credentials: ' + ', '.join(missing_credentials()))
    import os
    os.environ['LIVEKIT_URL'] = settings.livekit_url
    os.environ['LIVEKIT_API_KEY'] = settings.livekit_api_key
    os.environ['LIVEKIT_API_SECRET'] = settings.livekit_api_secret
    agents.cli.run_app(server)
