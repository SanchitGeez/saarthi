import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

from app.config import settings
from app.providers import missing_credentials, build_llm, build_stt, build_tts
from app.agent import TurnContext, set_turn_context, reset_turn_context
from app.openrouter_turn import run_openrouter_turn


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_selected_keys_only_and_no_implicit_fallback(self):
        with patch.multiple(settings, llm_provider='openrouter', stt_provider='deepgram', tts_provider='murf',
            openrouter_api_key='', deepgram_api_key='', murf_api_key='', google_api_key='other', eleven_labs_api_key='other'):
            self.assertEqual(len(missing_credentials()), 3)
            self.assertEqual(missing_credentials(voice=False), ['OPENROUTER_API_KEY'])
        with patch.multiple(settings, llm_provider='openrouter', stt_provider='deepgram', tts_provider='murf',
            openrouter_api_key='test-router', deepgram_api_key='test-stt', murf_api_key='test-tts'):
            self.assertEqual(missing_credentials(), [])

    def test_factories_use_explicit_provider_credentials(self):
        with patch.multiple(settings, llm_provider='openrouter', stt_provider='deepgram', tts_provider='murf',
            openrouter_api_key='test-router', deepgram_api_key='test-stt', murf_api_key='test-tts'), \
            patch('livekit.plugins.openai.LLM') as llm, patch('livekit.plugins.deepgram.STT') as stt, patch('livekit.plugins.murf.TTS') as tts:
            build_llm(); build_stt(); build_tts()
            self.assertEqual(llm.call_args.kwargs['base_url'],'https://openrouter.ai/api/v1')
            self.assertEqual(llm.call_args.kwargs['api_key'],'test-router')
            self.assertEqual(stt.call_args.kwargs['api_key'],'test-stt')
            self.assertEqual(stt.call_args.kwargs['language'],'multi')
            self.assertEqual(tts.call_args.kwargs['api_key'],'test-tts')

    async def test_model_cannot_supply_trusted_user_identity(self):
        uid=uuid4(); cid=uuid4(); context=TurnContext(uid,cid,'I prefer short replies.',True)
        call=SimpleNamespace(id='tool-1',function=SimpleNamespace(name='remember_detail',arguments='{"content":"Prefers short replies","kind":"preference","evidence":"I prefer short replies.","tool_context":{"user_id":"foreign"}}'))
        reply=SimpleNamespace(tool_calls=[call],model_dump=lambda **_: {'role':'assistant','tool_calls':[{'id':'tool-1','type':'function','function':{'name':'remember_detail','arguments':call.function.arguments}}]})
        final=SimpleNamespace(tool_calls=None,content='I’ll keep it brief.')
        client=AsyncMock(); client.chat.completions.create.side_effect=[SimpleNamespace(choices=[SimpleNamespace(message=m)]) for m in [reply,final]]
        client.__aenter__.return_value=client
        token=set_turn_context(context)
        try:
            with patch('app.openrouter_turn.AsyncOpenAI',return_value=client), patch('app.agent.load_memories',new=AsyncMock(return_value={'memories':[]})), patch.object(settings,'openrouter_api_key','test'):
                answer=await run_openrouter_turn(uid,cid,context.user_text,[],'en',[])
                self.assertIn('brief',answer); self.assertEqual(len(context.memory_changes),1)
                self.assertEqual(context.memory_changes[0]['evidence'],context.user_text)
        finally: reset_turn_context(token)

    async def test_unquoted_evidence_does_not_queue_memory(self):
        from app.agent import remember_detail
        context=TurnContext(uuid4(),uuid4(),'Hello there.',True); token=set_turn_context(context)
        try:
            result=await remember_detail('Has a medical condition','context','not in current message',SimpleNamespace(user_id=str(context.user_id)))
            self.assertFalse(result['saved']); self.assertEqual(context.memory_changes,[])
        finally: reset_turn_context(token)

    async def test_voice_hook_refreshes_current_turn_copy_and_attaches_trusted_evidence(self):
        import asyncio
        from livekit.agents import llm
        from app.voice_worker import Parth
        agent=Parth(uuid4(),'en',{'memories':[]},asyncio.Event())
        turn=llm.ChatContext.empty(); turn.add_message(role='system',content='old settings')
        message=llm.ChatMessage(role='user',content=['Please remember I prefer short replies.'])
        source=uuid4()
        with patch('app.voice_worker.load_context',new=AsyncMock(return_value=('hi',{'memories':[], 'cross_chat_recall':False}))), patch('app.voice_worker.record_message',new=AsyncMock(return_value=source)):
            await agent.on_user_turn_completed(turn,message)
        self.assertIn('Speak natural Hindi',turn.items[0].text_content)
        self.assertIn(str(source),turn.items[-1].text_content)
        self.assertTrue(agent.user_spoke.is_set())
