"""Voice policy/API integration tests against real PostgreSQL; provider network mocked."""
import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import jwt
from sqlalchemy import select

from app.auth import create_access_token
from app.config import settings
from app.continuity import continuity_context, OPENING_INSTRUCTIONS
from app.db import SessionLocal
from app.main import app
from app.models import ChatTurn, Conversation, Memory, User, VoiceSession
from app.voice_sessions import record_message, remember_from_voice


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = [patch.object(settings, 'llm_provider', 'gemini'), patch.object(settings, 'stt_provider', 'elevenlabs'), patch.object(settings, 'tts_provider', 'elevenlabs'), patch.object(settings, 'livekit_url', 'ws://127.0.0.1:7880'),
            patch.object(settings, 'livekit_api_key', 'devkey'),
            patch.object(settings, 'livekit_api_secret', 'test-only-secret-long-enough-32-chars'),
            patch.object(settings, 'eleven_labs_api_key', 'test-only'),
            patch.object(settings, 'google_api_key', 'test-only')]
        for p in self.config: p.start()
        self.cleanup = patch('app.voice_sessions.remove_room', new_callable=AsyncMock)
        self.remove_room = self.cleanup.start()
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        async with SessionLocal() as db:
            users = [User(email=f'voice-tests-{uuid4().hex}@example.com') for _ in range(2)]
            db.add_all(users); await db.commit()
            self.uid, self.other_uid = [u.id for u in users]
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.auth = {'Authorization': 'Bearer ' + create_access_token(str(self.uid))}
        self.other = {'Authorization': 'Bearer ' + create_access_token(str(self.other_uid))}
        self.cid = UUID((await self.client.post('/api/conversations', headers=self.auth, json={})).json()['id'])

    async def asyncTearDown(self):
        self.remove_room.side_effect = None
        for headers in [self.auth, self.other]:
            await self.client.delete('/api/auth/me', headers=headers)
        await self.client.aclose(); await self.lifespan.__aexit__(None, None, None)
        self.cleanup.stop()
        for p in reversed(self.config): p.stop()

    async def start(self, id=None, headers=None, cid=None):
        return await self.client.post('/api/voice/sessions', headers=headers or self.auth,
            json={'client_id': str(id or uuid4()), 'conversation_id': str(cid or self.cid)})

    async def seed(self, private=False, text='I planned to talk to my manager.'):
        async with SessionLocal() as db:
            c = Conversation(user_id=self.uid, private=private)
            db.add(c); await db.flush()
            db.add(ChatTurn(conversation_id=c.id, text=text, answer='One calm conversation could help.', status='completed'))
            await db.commit(); return c.id

    async def context(self, cid=None):
        async with SessionLocal() as db:
            return await continuity_context(db, await db.get(User, self.uid), await db.get(Conversation, cid or self.cid))

    async def test_auth_and_ownership(self):
        self.assertEqual((await self.client.get('/api/voice/sessions/status')).status_code, 401)
        self.assertEqual((await self.start(headers=self.other)).status_code, 404)
        response = await self.start(); sid = response.json()['session_id']
        self.assertEqual((await self.client.delete('/api/voice/sessions/'+sid, headers=self.other)).status_code, 404)
        self.assertEqual((await self.start(id=UUID(sid), headers=self.other)).status_code, 404)

    async def test_token_restricts_room_camera_and_dispatch_context(self):
        result = (await self.start()).json()
        claims = jwt.decode(result['participant_token'], settings.livekit_api_secret, algorithms=['HS256'], options={'verify_aud': False})
        grant = claims['video']
        self.assertEqual(grant['room'], 'saarthi-'+UUID(result['session_id']).hex)
        self.assertEqual(grant['canPublishSources'], ['microphone'])
        self.assertTrue(grant['canPublishData']); self.assertFalse(grant['canUpdateOwnMetadata'])
        self.assertEqual(claims['sub'], 'user-'+str(self.uid))
        import json
        metadata = json.loads(claims['roomConfig']['agents'][0]['metadata'])
        self.assertEqual(metadata, {'session_id': result['session_id']})
        self.assertNotIn('google_api_key', result)

    async def test_idempotent_start_and_parallel_limit(self):
        id = uuid4()
        a, b = await asyncio.gather(self.start(id=id), self.start(id=id))
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(a.json()['session_id'], b.json()['session_id'])
        self.assertEqual((await self.start()).status_code, 409)
        await self.client.delete('/api/voice/sessions/'+str(id), headers=self.auth)
        self.assertEqual((await self.start(id=id)).status_code, 409)

    async def test_end_retry_and_cleanup_failure_no_new_room(self):
        result = (await self.start()).json(); sid = result['session_id']
        self.remove_room.side_effect = RuntimeError('network')
        response = await self.client.delete('/api/voice/sessions/'+sid, headers=self.auth)
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(await record_message(UUID(sid), 'late', 'user', 'late words', datetime.now(UTC).timestamp()))
        self.assertEqual((await self.start()).status_code, 503)
        self.remove_room.side_effect = None
        self.assertEqual((await self.client.delete('/api/voice/sessions/'+sid, headers=self.auth)).status_code, 204)
        self.assertEqual(self.remove_room.call_count, 3)

    async def test_expired_call_cleanup_and_replacement(self):
        sid = UUID((await self.start()).json()['session_id'])
        async with SessionLocal() as db:
            c = await db.get(VoiceSession, sid); c.expires_at = datetime.now(UTC)-timedelta(seconds=1); await db.commit()
        self.remove_room.side_effect = RuntimeError('network')
        self.assertEqual((await self.start()).status_code, 503)
        self.remove_room.side_effect = None
        self.assertEqual((await self.start()).status_code, 200)
        self.assertIsNone(await record_message(sid, 'late', 'user', 'late', datetime.now(UTC).timestamp()))

    async def test_cross_chat_context_excludes_private_other_user_and_failed_turns(self):
        await self.seed(); await self.seed(private=True, text='PRIVATE SECRET')
        async with SessionLocal() as db:
            c = Conversation(user_id=self.other_uid); db.add(c); await db.flush()
            db.add(ChatTurn(conversation_id=c.id, text='OTHER SECRET', answer='reply', status='completed'))
            db.add(ChatTurn(conversation_id=self.cid, text='FAILED SECRET', status='failed'))
            db.add(Memory(user_id=self.uid, content='Prefers short answers.', source_excerpt='short answers', status='confirmed', kind='preference'))
            await db.commit()
        data = await self.context()
        self.assertIn('manager', str(data)); self.assertIn('Prefers short', str(data))
        for hidden in ['PRIVATE SECRET', 'OTHER SECRET', 'FAILED SECRET']: self.assertNotIn(hidden, str(data))
        self.assertTrue(data['last_conversation_at'])
        self.assertIn('no fixed opener', OPENING_INSTRUCTIONS)
        self.assertIn('plain greeting', OPENING_INSTRUCTIONS)

    async def test_private_and_memory_off_context_and_writes(self):
        await self.seed()
        await self.client.patch('/api/me/preferences', headers=self.auth, json={'memory_enabled': False})
        self.assertFalse((await self.context())['cross_chat_recall'])
        self.assertEqual((await self.context())['recent_messages'], [])
        sid = UUID((await self.start()).json()['session_id'])
        mid = await record_message(sid, 'input', 'user', 'I work in Pune.', datetime.now(UTC).timestamp())
        self.assertFalse((await remember_from_voice(sid, mid, 'Works in Pune', 'context', 'work in Pune'))['saved'])
        await self.client.delete('/api/voice/sessions/'+str(sid), headers=self.auth)
        await self.client.patch('/api/me/preferences', headers=self.auth, json={'memory_enabled': True})
        private_cid = await self.seed(private=True, text='current private chat')
        data = await self.context(private_cid)
        self.assertFalse(data['cross_chat_recall']); self.assertIn('current private', str(data)); self.assertNotIn('manager', str(data))
        sid = UUID((await self.start(cid=private_cid)).json()['session_id'])
        mid = await record_message(sid, 'input', 'user', 'I work in Pune.', datetime.now(UTC).timestamp())
        self.assertFalse((await remember_from_voice(sid, mid, 'Works in Pune', 'context', 'work in Pune'))['saved'])

    async def test_voice_evidence_once_stale_and_foreign_ids(self):
        sid = UUID((await self.start()).json()['session_id']); now = datetime.now(UTC).timestamp()
        mid = await record_message(sid, 'input', 'user', 'I work in Pune.', now)
        self.assertFalse((await remember_from_voice(sid, uuid4(), 'Works in Pune', 'context', 'work in Pune'))['saved'])
        self.assertFalse((await remember_from_voice(sid, mid, 'Works in Pune', 'context', 'Mumbai'))['saved'])
        self.assertTrue((await remember_from_voice(sid, mid, 'Works in Pune', 'context', 'work in Pune'))['saved'])
        self.assertFalse((await remember_from_voice(sid, mid, 'Another fact', 'context', 'Pune'))['saved'])
        second = await record_message(sid, 'input2', 'user', 'I now work in Delhi.', now+1)
        self.assertFalse((await remember_from_voice(sid, mid, 'Wrong update', 'context', 'Pune'))['saved'])
        memory = (await self.client.get('/api/memories', headers=self.auth)).json()[0]
        self.assertTrue((await remember_from_voice(sid, second, 'Works in Delhi', 'context', 'work in Delhi', UUID(memory['id'])))['saved'])
        self.assertEqual((await self.client.get('/api/memories', headers=self.auth)).json()[0]['content'], 'Works in Delhi')

    async def test_transcript_order_deduplication_and_interrupted_delivery(self):
        async with SessionLocal() as db:
            db.add(ChatTurn(conversation_id=self.cid, text='typed earlier', answer='typed answer', status='completed')); await db.commit()
        sid = UUID((await self.start()).json()['session_id']); now = datetime.now(UTC).timestamp()
        one = await record_message(sid, 'user1', 'user', 'spoken next', now)
        two = await record_message(sid, 'user1', 'user', 'spoken next', now)
        self.assertEqual(one, two)
        await record_message(sid, 'reply1', 'assistant', 'partial reply', now+1, True)
        messages = (await self.client.get(f'/api/conversations/{self.cid}/messages', headers=self.auth)).json()
        self.assertEqual([m['text'] for m in messages], ['typed earlier','typed answer','spoken next','partial reply'])
        self.assertTrue(messages[-1]['interrupted']); self.assertEqual(messages[-1]['delivery'], 'interrupted')
        self.assertEqual((await self.client.post(f'/api/conversations/{self.cid}/turns', headers=self.auth, json={'text':'overlap'})).status_code, 409)

    async def test_delete_during_call_closes_media_and_late_events_cannot_restore_data(self):
        sid = UUID((await self.start()).json()['session_id'])
        mid = await record_message(sid, 'input', 'user', 'I work in Pune.', datetime.now(UTC).timestamp())
        self.assertEqual((await self.client.delete(f'/api/conversations/{self.cid}', headers=self.auth)).status_code, 204)
        self.assertIsNone(await record_message(sid, 'late', 'assistant', 'late reply', datetime.now(UTC).timestamp()))
        self.assertFalse((await remember_from_voice(sid, mid, 'Works in Pune','context','Pune'))['saved'])
        self.assertEqual((await self.client.get('/api/memories',headers=self.auth)).json(), [])
        self.remove_room.assert_awaited()

    async def test_unconfigured_call_has_actionable_error(self):
        with patch.object(settings, 'livekit_url', ''):
            self.assertFalse((await self.client.get('/api/voice/sessions/status', headers=self.auth)).json()['available'])
            self.assertEqual((await self.start()).status_code, 503)

if __name__ == '__main__': unittest.main()
