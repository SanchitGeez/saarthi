import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from core import service
from core.errors import Problem
from core.models import Conversation, now
from tests.conftest import sign_in, start
from voice import store
from voice.policy import Delivery, acknowledgment


def test_acknowledgment_is_whole_utterance():
    for text in ["Haan.", "हाँ", "hmm", "achha"]:
        assert acknowledgment(text)
    for text in ["haan lekin ruko", "nahi", "stop", "achha kyun?"]:
        assert not acknowledgment(text)


def test_delivery_is_prefix_of_original_text_and_undercounts_normalization():
    delivery = Delivery(text="Haan, samajh aaya. $50 bache.", sent_seconds=1.2)
    delivery.timestamps(["Haan", "samajh", "aaya", "fifty", "dollars"], [0.2, 0.6, 0.9, 1, 1.2])
    assert delivery.prefix() == "Haan, samajh"
    assert not delivery.aligned
    delivery.sent_seconds = 10
    assert delivery.prefix() == "Haan, samajh aaya."


def test_voice_lease_blocks_text_and_end_and_fences_late_commits(client, factory, settings):
    sign_in(client)
    conversation_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])
    token = uuid4()
    store.acquire(factory, user_id, conversation_id, token)
    for path, body in [
        (f"/conversations/{conversation_id}/messages", {"id": str(uuid4()), "content": "hello"}),
        (f"/conversations/{conversation_id}/end", None),
    ]:
        response = client.post(path, json=body) if body else client.post(path)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "voice_active"
    with pytest.raises(Problem):
        store.acquire(factory, user_id, conversation_id, uuid4())
    message_id = uuid4()
    store.prepare(factory, user_id, conversation_id, token, "aaj kaam mushkil tha", message_id)
    store.commit(factory, user_id, conversation_id, token, message_id, "Kya hua", True)
    # A duplicate completion cannot overwrite the delivered prefix.
    store.commit(factory, user_id, conversation_id, token, message_id, "unheard response", False)
    result = service.get_conversation(factory, user_id, conversation_id)
    assert result["messages"][-1]["content"] == "Kya hua"
    assert result["messages"][-1]["delivery_status"] == "interrupted"
    next_payload = store.prepare(factory, user_id, conversation_id, token, "ruko", uuid4())
    assert next_payload["transcript"][-2] == {
        "role": "assistant",
        "content": "Kya hua",
        "interrupted": True,
    }
    store.release(factory, user_id, conversation_id, token)
    with pytest.raises(Problem):
        store.commit(factory, user_id, conversation_id, token, message_id, "late", False)
    assert (
        client.post(
            f"/conversations/{conversation_id}/messages",
            json={"id": str(uuid4()), "content": "hello"},
        ).status_code
        == 201
    )


def test_expired_lease_can_be_replaced_without_stale_release(client, factory):
    sign_in(client)
    conversation_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])
    old, new = uuid4(), uuid4()
    store.acquire(factory, user_id, conversation_id, old)
    with factory.begin() as db:
        db.get(Conversation, conversation_id).voice_expires_at = now() - timedelta(seconds=1)
    store.acquire(factory, user_id, conversation_id, new)
    store.release(factory, user_id, conversation_id, old)
    with factory() as db:
        assert db.get(Conversation, conversation_id).voice_token == new
    store.release(factory, user_id, conversation_id, new)


def test_voice_start_is_disabled_and_authorized(client, settings):
    settings.voice_enabled = False
    assert (
        client.post(
            "/voice/sessions", json={"id": str(uuid4()), "conversation_id": str(uuid4())}
        ).status_code
        == 401
    )
    sign_in(client)
    assert (
        client.post(
            "/voice/sessions", json={"id": str(uuid4()), "conversation_id": start(client)}
        ).status_code
        == 503
    )


def test_voice_start_requires_cartesia_credentials(client, settings):
    settings.voice_enabled = True
    settings.deepgram_api_key = settings.openrouter_api_key = "test"
    settings.murf_api_key = settings.murf_voice_id = "retained-murf-config"
    settings.cartesia_api_key = ""
    sign_in(client)
    response = client.post(
        "/voice/sessions", json={"id": str(uuid4()), "conversation_id": start(client)}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "voice_not_configured"
    assert "Cartesia" in response.json()["error"]["message"]


def test_voice_start_retry_ownership_stop_and_logout(client, settings, factory):
    pytest.importorskip("pipecat")
    settings.voice_enabled = True
    settings.deepgram_api_key = settings.cartesia_api_key = settings.openrouter_api_key = "test"
    sign_in(client)
    conv = start(client)
    body = {"id": str(uuid4()), "conversation_id": conv}
    assert client.post("/voice/sessions", json=body).status_code == 201
    assert client.post("/voice/sessions", json=body).status_code == 201
    assert client.post("/voice/sessions", json={**body, "id": str(uuid4())}).status_code == 409
    assert client.delete("/voice/sessions/" + body["id"]).status_code == 204
    assert client.delete("/voice/sessions/" + body["id"]).status_code == 204
    body["id"] = str(uuid4())
    assert client.post("/voice/sessions", json=body).status_code == 201
    assert client.post("/auth/logout").status_code == 204
    with factory() as db:
        assert db.get(Conversation, UUID(conv)).voice_token is None


def test_streamed_agent_does_not_duplicate_final_event(monkeypatch):
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.genai import types

    from agents.runner import invoke_stream
    from config import Settings

    async def events(self, **kwargs):
        assert kwargs["run_config"].streaming_mode.value == "sse"
        for text, partial in [("Haan, ", True), ("bolo.", True), ("Haan, bolo.", False)]:
            yield Event(
                author="saarthi",
                partial=partial,
                content=types.Content(role="model", parts=[types.Part(text=text)]),
            )

    monkeypatch.setattr(Runner, "run_async", events)

    async def run():
        return [
            part
            async for part in invoke_stream(
                Settings(_env_file=None, openrouter_api_key="test"), "saarthi", "test", {}
            )
        ]

    assert asyncio.run(run()) == ["Haan, ", "bolo."]


def test_interrupt_cancels_generation_and_saves_only_delivered_text(monkeypatch):
    pytest.importorskip("pipecat")
    from config import Settings
    from voice.session import VoiceSession

    saved = []
    monkeypatch.setattr(store, "commit", lambda *args: saved.append(args[-2:]))

    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        session.message_id = uuid4()
        session.response_id = "old"
        session.delivery = Delivery(text="Haan bolo aur suno", sent_seconds=0.8)
        session.delivery.timestamps(["Haan", "bolo", "aur", "suno"], [0.2, 0.5, 0.8, 1.2])
        session.response_task = asyncio.create_task(asyncio.sleep(30))

        async def clear(frame):
            from pipecat.frames.frames import InterruptionFrame

            assert isinstance(frame, InterruptionFrame)

        session.agent = SimpleNamespace(push_frame=clear)
        await session.interrupt()
        assert session.response_id is None
        assert session.response_task is None
        assert saved == [("Haan", True)]

    asyncio.run(run())


def test_retry_preserves_delivered_prefix_and_only_synthesizes_suffix(monkeypatch):
    pytest.importorskip("pipecat")
    from pipecat.frames.frames import LLMFullResponseEndFrame, TextFrame

    from config import Settings
    from voice.session import VoiceSession

    saved, texts = [], []
    monkeypatch.setattr(store, "commit", lambda *args: saved.append(args[-2:]))

    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        session.message_id = uuid4()
        attempts = 0

        async def push(frame):
            nonlocal attempts
            if type(frame) is TextFrame:
                texts.append(frame.text)
                attempts += 1
                session.delivery.sent_seconds = 1
                session.delivery.timestamps(
                    frame.text.split(), [0.2] if attempts > 1 else [0.2, 0.9]
                )
            elif isinstance(frame, LLMFullResponseEndFrame):
                if attempts == 1:
                    session.provider_failure(True)
                else:
                    session.done.set()

        async def noop(*args):
            pass

        session.agent = SimpleNamespace(push_frame=push)
        session.tts = SimpleNamespace(_disconnect=noop, _connect=noop)
        await session._respond(None, "Haan bolo")
        assert texts == ["Haan bolo", " bolo"]
        assert saved == [("Haan bolo", False)]

    asyncio.run(run())


def test_cancelled_interruption_request_still_stops_and_saves_reply(monkeypatch):
    pytest.importorskip("pipecat")
    from config import Settings
    from voice.session import VoiceSession

    saved = []
    monkeypatch.setattr(store, "commit", lambda *args: saved.append(args[-2:]))

    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        session.message_id = uuid4()
        session.delivery = Delivery(text="Haan bolo", sent_seconds=1)
        session.delivery.timestamps(["Haan", "bolo"], [0.2, 0.9])
        old = session.response_task = asyncio.create_task(asyncio.sleep(30))
        clearing, release = asyncio.Event(), asyncio.Event()

        async def push(frame):
            clearing.set()
            await release.wait()

        session.agent = SimpleNamespace(push_frame=push)
        request = asyncio.create_task(session.interrupt())
        await asyncio.wait_for(clearing.wait(), 2)
        request.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert old.cancelled()
        assert session.response_task is None
        assert saved == [("Haan", True)]

    asyncio.run(run())


def test_murf_timestamps_and_stale_generation_are_fenced():
    pytest.importorskip("pipecat")
    from voice.murf import TimedMurf

    async def run():
        session = SimpleNamespace(
            response_id="one", delivery=Delivery(text="Haan bolo"), closed=False
        )
        tts = TimedMurf(session, api_key="test")
        config = tts._build_voice_config_message("Haan bolo", "context")
        assert config["add_word_timestamps"] is True
        assert config["predictive_chunking"] == "lenient"
        assert "add_word_timestamps" not in config["voice_config"]
        await tts._process_json_message(
            {
                "context_id": "context",
                "timestamps": {
                    "words": [
                        {"word": "Haan", "start_s": 0, "end_s": 0.2},
                        {"word": "bolo", "start_s": 0.3, "end_s": 0.7},
                    ]
                },
            }
        )
        assert session.delivery.words == [(0.2, 4), (0.7, 9)]
        session.response_id = "two"
        await tts._process_json_message(
            {
                "context_id": "context",
                "timestamps": {
                    "words": [
                        {"word": "unheard", "end_s": 1},
                    ]
                },
            }
        )
        assert session.delivery.aligned
        session.response_id = None
        await tts._process_json_message(
            {
                "context_id": "unknown",
                "timestamps": {
                    "words": [
                        {"word": "unheard", "end_s": 1},
                    ]
                },
            }
        )
        assert session.delivery.aligned
        await tts.cleanup()

    asyncio.run(run())


def test_transient_error_classification():
    pytest.importorskip("pipecat")
    from httpx import ConnectError
    from websockets.exceptions import ConnectionClosedError

    from voice.deepgram import transient

    assert transient(ConnectError("test"))
    assert transient(ConnectionClosedError(None, None))
    assert transient(SimpleNamespace(status_code=429))
    assert not transient(SimpleNamespace(status_code=401))
    assert not transient(ValueError("invalid input"))


def test_playback_checkpoint_can_complete_and_does_not_allow_rewrite(client, factory):
    sign_in(client)
    conversation_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])
    token, message_id = uuid4(), uuid4()
    store.acquire(factory, user_id, conversation_id, token)
    store.prepare(factory, user_id, conversation_id, token, "hello", message_id)
    for content, interrupted in [
        ("Haan", True),
        ("Haan bolo", True),
        ("Haan bolo.", False),
        ("changed", False),
    ]:
        store.commit(factory, user_id, conversation_id, token, message_id, content, interrupted)
    result = service.get_conversation(factory, user_id, conversation_id)["messages"]
    assert len(result) == 3
    assert result[-1]["content"] == "Haan bolo."
    assert result[-1]["delivery_status"] == "complete"
    store.release(factory, user_id, conversation_id, token)


def test_cancel_during_retry_stops_pending_attempt(monkeypatch):
    pytest.importorskip("pipecat")
    from pipecat.frames.frames import LLMFullResponseEndFrame, TextFrame

    from config import Settings
    from voice.session import VoiceSession

    saved = []
    monkeypatch.setattr(store, "commit", lambda *args: saved.append(args[-2:]))

    async def run():
        session = VoiceSession(None, Settings(_env_file=None), uuid4(), uuid4(), "", uuid4())
        session.message_id = uuid4()
        waiting = asyncio.Event()
        attempts = []

        async def push(frame):
            if type(frame) is TextFrame:
                attempts.append(frame.text)
            if isinstance(frame, LLMFullResponseEndFrame):
                session.provider_failure(True)

        def event(kind, **values):
            if kind == "retrying":
                waiting.set()

        session.event = event
        session.agent = SimpleNamespace(push_frame=push)
        session.response_task = asyncio.create_task(session._respond(None, "Haan bolo"))
        await asyncio.wait_for(waiting.wait(), 2)
        await session.interrupt()
        await asyncio.sleep(0.05)
        assert attempts == ["Haan bolo"]
        assert saved == [("", True)]

    asyncio.run(run())


def test_suppressed_acknowledgment_and_listening_answer(monkeypatch):
    pytest.importorskip("pipecat")
    from voice.pipeline import CaptureTurn

    replies = []

    async def respond(**kwargs):
        replies.append(kwargs["text"])

    async def run():
        capture = CaptureTurn(SimpleNamespace(start_response=respond))
        capture.parts, capture.overlap = ["haan"], True
        await capture.finish()
        assert replies == []
        capture.parts = ["haan"]
        await capture.finish()
        assert replies == ["haan"]
        capture.parts, capture.overlap = ["haan lekin ruko"], True
        await capture.finish()
        assert replies[-1] == "haan lekin ruko"
        await capture.cleanup()

    asyncio.run(run())


def test_spoken_notices_do_not_duplicate_greeting_and_reach_agent_context(client, factory):
    from core import data

    sign_in(client)
    conversation_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])
    token, notice_id = uuid4(), uuid4()
    store.acquire(factory, user_id, conversation_id, token)
    store.commit(factory, user_id, conversation_id, token, None, "Haan", True, notice_id=notice_id)
    store.commit(
        factory, user_id, conversation_id, token, None, "Haan, bolo.", False, notice_id=notice_id
    )
    payload = store.prepare(factory, user_id, conversation_id, token, "haan", uuid4())
    assert payload["transcript"][-2] == {"role": "assistant", "content": "Haan, bolo."}
    with factory() as db:
        opening = data.assistant_reply(db, conversation_id, None)
        assert opening.content == "Hello. What is on your mind?"
        assert len(data.messages(db, conversation_id)) == 3
    store.release(factory, user_id, conversation_id, token)


def test_voice_migration_matches_models_and_roundtrips(database):
    from alembic import command
    from alembic.config import Config

    command.check(Config("alembic.ini"))
    command.downgrade(Config("alembic.ini"), "62b4ebea1318")
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))


def test_leave_during_signaling_does_not_start_pipeline(client, settings, monkeypatch):
    pytest.importorskip("pipecat")
    from pipecat.transports.smallwebrtc import connection

    settings.voice_enabled = True
    settings.deepgram_api_key = settings.cartesia_api_key = settings.openrouter_api_key = "test"
    sign_in(client)
    identifier = uuid4()
    assert (
        client.post(
            "/voice/sessions", json={"id": str(identifier), "conversation_id": start(client)}
        ).status_code
        == 201
    )
    session = client.app.state.voice_sessions[identifier]

    class ClosingConnection:
        def __init__(self, **kwargs):
            pass

        def send_app_message(self, message):
            pass

        async def initialize(self, *args):
            await session.close()

        async def disconnect(self):
            pass

    monkeypatch.setattr(connection, "SmallWebRTCConnection", ClosingConnection)
    response = client.post(
        f"/voice/sessions/{identifier}/offer", json={"sdp": "test", "type": "offer"}
    )
    assert response.status_code == 502
    assert session.closed
    assert session.pipeline_task is None
