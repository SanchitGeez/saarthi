"""Real PostgreSQL/ADK/HTTP regression checks; no provider calls or mocks.
Run: python -m unittest discover -s tests -p test_product.py -v
"""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
import httpx
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types
from app.agent import (TurnContext, build_runner, commit_memories, find_memories,
    get_gita_verse, remember_detail, reset_turn_context, set_turn_context, update_remembered_detail)
from app.auth import create_access_token
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ChatTurn, User

class ProductTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        async with SessionLocal() as db:
            users = [User(email=f'saarthi-policy-{uuid4().hex}@example.com') for _ in range(2)]
            db.add_all(users); await db.commit()
            self.uid, self.other_uid = [u.id for u in users]
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.auth = {'Authorization': 'Bearer ' + create_access_token(str(self.uid))}
        self.other = {'Authorization': 'Bearer ' + create_access_token(str(self.other_uid))}
        response = await self.client.post('/api/conversations', headers=self.auth, json={'private': False})
        self.assertEqual(response.status_code, 200)
        self.cid = UUID(response.json()['id']); self.path = f'/api/conversations/{self.cid}'
        service = InMemorySessionService()
        session = await service.create_session(app_name=settings.app_name, user_id=str(self.uid), session_id=str(self.cid))
        self.tool = ToolContext(InvocationContext(session_service=service, invocation_id=str(uuid4()), agent=build_runner(service).agent, session=session))
    async def asyncTearDown(self):
        for auth in [self.auth, self.other]:
            self.assertEqual((await self.client.delete('/api/auth/me', headers=auth)).status_code, 204)
        await self.client.aclose(); await self.lifespan.__aexit__(None,None,None)
    async def insert(self, **kwargs):
        async with SessionLocal() as db:
            turn = ChatTurn(conversation_id=self.cid, **kwargs)
            db.add(turn); await db.commit(); return turn.id
    async def history(self):
        response = await self.client.get(self.path+'/messages', headers=self.auth)
        self.assertEqual(response.status_code, 200); return response.json()
    async def test_openapi_resolves_voice_body_and_rejects_invalid_text(self):
        response = await self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        operation = schema['paths']['/api/voice/speak']['post']
        body = operation['requestBody']['content']['application/json']['schema']
        self.assertEqual(body['$ref'], '#/components/schemas/SpeechRequest')
        self.assertFalse(any(p['name']=='payload' for p in operation.get('parameters',[])))
        self.assertIn('audio/mpeg',operation['responses']['200']['content'])
        self.assertEqual(schema['components']['schemas']['SpeechRequest']['properties']['text']['maxLength'],10_000)
        self.assertEqual((await self.client.post('/api/voice/speak',json={'text':'Hello'})).status_code,401)
        for payload in [{}, {'text':''}, {'text':'   '}, {'text':'a'*10_001}]:
            response = await self.client.post('/api/voice/speak',headers=self.auth,json=payload)
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json()['detail'][0]['loc'],['body','text'])
    async def test_transcription_requires_an_authenticated_nonempty_file(self):
        response = await self.client.get('/openapi.json')
        operation = response.json()['paths']['/api/voice/transcribe']['post']
        self.assertIn('multipart/form-data',operation['requestBody']['content'])
        self.assertEqual((await self.client.post('/api/voice/transcribe',files={'file':('voice-note.m4a',b'','audio/mp4')})).status_code,401)
        response = await self.client.post('/api/voice/transcribe',headers=self.auth)
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.json()['detail'][0]['loc'],['body','file'])
        response = await self.client.post('/api/voice/transcribe',headers=self.auth,files={'file':('voice-note.m4a',b'','audio/mp4')})
        self.assertEqual(response.status_code,400)
        self.assertIn('empty',response.json()['detail'])
    async def test_interrupted_turn_becomes_retryable_and_removable(self):
        tid = await self.insert(text='Interrupted',status='processing',updated_at=datetime.now(UTC)-timedelta(minutes=3))
        history = await self.history()
        self.assertEqual(history[0]['status'], 'failed'); self.assertEqual(history[0]['error_code'],504)
        self.assertEqual((await self.client.delete(self.path+f'/turns/{tid}',headers=self.other)).status_code,404)
        self.assertEqual((await self.client.delete(self.path+f'/turns/{tid}',headers=self.auth)).status_code,204)
        self.assertEqual(await self.history(),[])
    async def test_processing_duplicate_is_rejected_without_another_generation(self):
        tid = await self.insert(text='Still processing',status='processing')
        response = await self.client.post(self.path+'/turns',headers=self.auth,json={'text':'Still processing','client_id':str(tid)})
        self.assertEqual(response.status_code,409)
        self.assertEqual((await self.client.delete(self.path+f'/turns/{tid}',headers=self.auth)).status_code,409)
        self.assertEqual(len(await self.history()),1)
    async def test_completed_delivery_is_idempotent_and_owner_scoped(self):
        tid = await self.insert(text='Original',answer='Saved reply',status='completed',scripture_refs=['2.47'])
        response = await self.client.post(self.path+'/turns',headers=self.auth,json={'text':'Original','client_id':str(tid)})
        self.assertEqual(response.status_code,200); self.assertEqual(response.json()['text'],'Saved reply')
        self.assertEqual(response.json()['verses'][0]['reference'],'2.47')
        response = await self.client.post(self.path+'/turns',headers=self.auth,json={'text':'Changed','client_id':str(tid)})
        self.assertEqual(response.status_code,409)
        response = await self.client.post(self.path+'/turns',headers=self.other,json={'text':'Original','client_id':str(tid)})
        self.assertEqual(response.status_code,404); self.assertEqual(len(await self.history()),2)
    async def test_legacy_import_preserves_success_and_marks_orphans_once(self):
        service = app.state.session_service
        session = await service.create_session(app_name=settings.app_name,user_id=str(self.uid),session_id=str(self.cid))
        for author,role,value in [('user','user','Earlier question'),('mitra','model','Earlier reply'),('user','user','Unanswered question')]:
            await service.append_event(session,Event(author=author,invocation_id=str(uuid4()),content=types.Content(role=role,parts=[types.Part(text=value)])))
        first = await self.history(); self.assertEqual(first,await self.history())
        self.assertEqual([m['text'] for m in first],['Earlier question','Earlier reply','Unanswered question'])
        self.assertEqual(first[-1]['status'],'failed')
    async def test_discard_last_legacy_orphan_does_not_reimport_it(self):
        service = app.state.session_service
        session = await service.create_session(app_name=settings.app_name,user_id=str(self.uid),session_id=str(self.cid))
        await service.append_event(session,Event(author='user',invocation_id=str(uuid4()),content=types.Content(role='user',parts=[types.Part(text='Orphan')])))
        first = await self.history()
        self.assertEqual(first[0]['status'],'failed')
        response = await self.client.delete(self.path+'/turns/'+first[0]['turn_id'],headers=self.auth)
        self.assertEqual(response.status_code,204)
        self.assertEqual(await self.history(),[])
        self.assertEqual(await self.history(),[])
    async def test_otp_throttle_and_immediate_signin_after_consumed_code(self):
        async with SessionLocal() as db:
            user = await db.get(User,self.uid); email=user.email
        response = await self.client.post('/api/auth/request-code',json={'email':email})
        self.assertEqual(response.status_code,200)
        code = response.json()['dev_code']
        response = await self.client.post('/api/auth/request-code',json={'email':email})
        self.assertEqual(response.status_code,429)
        self.assertIn('retry-after',response.headers)
        response = await self.client.post('/api/auth/verify-code',json={'email':email,'code':code})
        self.assertEqual(response.status_code,200)
        response = await self.client.post('/api/auth/request-code',json={'email':email})
        self.assertEqual(response.status_code,200)
        response = await self.client.post('/api/auth/verify-code',json={'email':email,'code':code})
        self.assertNotEqual(response.status_code,200)
    async def test_memory_is_staged_selective_automatic_deduplicated_and_editable(self):
        ctx = TurnContext(self.uid,self.cid,'I work as a software engineer in Pune.',True)
        token = set_turn_context(ctx)
        try:
            self.assertFalse((await remember_detail('Guess','context','not a quote',self.tool))['saved'])
            self.assertFalse((await remember_detail('Passing emotion','concern','I work',self.tool))['saved'])
            self.assertTrue((await remember_detail('Software engineer in Pune','context','software engineer in Pune',self.tool))['saved'])
            self.assertFalse((await remember_detail('Another detail','context','I work',self.tool))['saved'])
            self.assertEqual((await self.client.get('/api/memories',headers=self.auth)).json(),[])
            async with SessionLocal() as db:
                self.assertEqual(len(await commit_memories(db,ctx)),1); await db.commit()
            memory = (await self.client.get('/api/memories',headers=self.auth)).json()[0]
            self.assertEqual(memory['status'],'confirmed')
            ctx.memory_changes.clear()
            await remember_detail('Software engineer in Pune','context','software engineer in Pune',self.tool)
            async with SessionLocal() as db:
                self.assertEqual(await commit_memories(db,ctx),[]); await db.commit()
            self.assertEqual(len((await find_memories('मेरी नौकरी',self.tool))['memories']),1)
            ctx.user_text='I now work as a designer in Delhi.'; ctx.memory_changes.clear()
            self.assertTrue((await update_remembered_detail(memory['id'],'Designer in Delhi','designer in Delhi',self.tool))['saved'])
            async with SessionLocal() as db:
                await commit_memories(db,ctx); await db.commit()
            self.assertEqual((await self.client.get('/api/memories',headers=self.auth)).json()[0]['content'],'Designer in Delhi')
            self.assertEqual((await self.client.patch('/api/memories/'+memory['id'],headers=self.auth,json={'content':'   '})).status_code,422)
            self.assertEqual((await self.client.delete('/api/memories/'+memory['id'],headers=self.other)).status_code,404)
            self.assertEqual((await self.client.delete('/api/memories/'+memory['id'],headers=self.auth)).status_code,204)
        finally: reset_turn_context(token)
    async def test_private_and_disabled_memory_do_not_persist(self):
        ctx = TurnContext(self.uid,self.cid,'I prefer short replies.',False)
        token = set_turn_context(ctx)
        try:
            self.assertFalse((await remember_detail('Prefers short replies','preference','short replies',self.tool))['saved'])
            self.assertEqual((await find_memories('preferences',self.tool))['memories'],[])
            ctx.memory_allowed=True
            await remember_detail('Prefers short replies','preference','short replies',self.tool)
            await self.client.patch('/api/me/preferences',headers=self.auth,json={'memory_enabled':False})
            async with SessionLocal() as db:
                self.assertEqual(await commit_memories(db,ctx),[]); await db.commit()
            self.assertEqual((await self.client.get('/api/memories',headers=self.auth)).json(),[])
        finally: reset_turn_context(token)
    async def test_verified_scripture_and_unknown_reference(self):
        ctx = TurnContext(self.uid,self.cid,'Work feels hard.',True); token=set_turn_context(ctx)
        try:
            verse=get_gita_verse('2.47',self.tool)
            self.assertTrue(verse['found']); self.assertIn('कर्मण्येवाधिकारस्ते',verse['sanskrit'])
            self.assertTrue(verse['english'] and verse['hindi'] and verse['source_url'])
            self.assertFalse(get_gita_verse('99.99',self.tool)['found']); self.assertEqual(ctx.scripture_refs,['2.47'])
        finally: reset_turn_context(token)
if __name__=='__main__': unittest.main()
