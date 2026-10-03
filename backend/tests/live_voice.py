"""Opt-in real LiveKit/STT/LLM/TTS smoke test. Consumes provider usage.
Run an API + Parth worker first, then: python tests/live_voice.py
All accounts/rooms created here are removed. Only synthetic fixture speech is sent.
"""
import asyncio
import io
import logging
import os
from uuid import uuid4

import av
import sys
import httpx
from livekit import rtc

API = os.environ.get('SAARTHI_TEST_API', 'http://127.0.0.1:8001/api')
logging.basicConfig(level=logging.WARNING)


async def run():
    room = rtc.Room()
    tasks = []
    audio = {'samples': 0}
    async def consume(track):
        async for event in rtc.AudioStream(track):
            audio['samples'] += event.frame.samples_per_channel
    @room.on('track_subscribed')
    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(asyncio.create_task(consume(track)))
    async with httpx.AsyncClient(base_url=API, timeout=45) as client:
        auth = None; sid = None; source = None; pump = None
        fixture_frames = asyncio.Queue()
        try:
            email = f'voice-smoke-{uuid4().hex}@example.com'
            response = await client.post('/auth/request-code', json={'email': email}); response.raise_for_status()
            code = response.json().get('dev_code')
            if not code: raise RuntimeError('Requires development OTP mode with SMTP disabled.')
            response = await client.post('/auth/verify-code', json={'email': email, 'code': code}); response.raise_for_status()
            auth = {'Authorization': 'Bearer '+response.json()['access_token']}
            await client.patch('/me/preferences', headers=auth, json={'language':'en'})
            response = await client.post('/conversations', headers=auth, json={}); response.raise_for_status(); cid = response.json()['id']
            response = await client.post('/voice/sessions', headers=auth, json={'conversation_id':cid, 'client_id':str(uuid4())}); response.raise_for_status()
            call = response.json(); sid = call['session_id']
            await room.connect(call['server_url'], call['participant_token'])
            source = rtc.AudioSource(16000, 1)
            async def audio_pump():
                while True:
                    try: frame = fixture_frames.get_nowait()
                    except asyncio.QueueEmpty: frame = rtc.AudioFrame(bytes(640),16000,1,320)
                    await source.capture_frame(frame)
                    await asyncio.sleep(frame.samples_per_channel / 16000)
            pump = asyncio.create_task(audio_pump())
            track = rtc.LocalAudioTrack.create_audio_track('synthetic-test-mic', source)
            await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
            async with asyncio.timeout(35):
                while True:
                    agents = [p for p in room.remote_participants.values() if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT]
                    if agents and agents[0].attributes.get('lk.agent.state') == 'listening': break
                    await asyncio.sleep(0.1)
            agent = agents[0]
            await room.local_participant.perform_rpc(destination_identity=agent.identity, method='saarthi.ready', payload='')
            async def history():
                result = await client.get(f'/conversations/{cid}/messages', headers=auth); result.raise_for_status(); return result.json()
            async with asyncio.timeout(45):
                while not any(m['role']=='assistant' for m in await history()): await asyncio.sleep(0.3)
            assert audio['samples'] > 0, 'No actual audio received from Parth'
            greeting = [m['text'] for m in await history() if m['role']=='assistant'][0]
            print('PASS generated opening and real audio:', greeting)
            before = len(await history())
            # Duplicate readiness cannot replay the greeting.
            await room.local_participant.perform_rpc(destination_identity=agent.identity, method='saarthi.ready', payload='')
            await asyncio.sleep(1)
            assert len(await history()) == before, 'Readiness replayed greeting'
            fixture = 'I prefer short replies. Please remember that. What is one small way to make my workday calmer?'
            response = await client.post('/voice/speak', headers=auth, json={'text':fixture}); response.raise_for_status()
            container = av.open(io.BytesIO(response.content))
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    raw = converted.to_ndarray().tobytes()
                    await fixture_frames.put(rtc.AudioFrame(raw,16000,1,len(raw)//2))
            for converted in resampler.resample(None):
                raw = converted.to_ndarray().tobytes()
                await fixture_frames.put(rtc.AudioFrame(raw,16000,1,len(raw)//2))
            async with asyncio.timeout(50):
                while True:
                    messages = await history()
                    if any(m['role']=='user' for m in messages) and len([m for m in messages if m['role']=='assistant']) >= 2: break
                    await asyncio.sleep(0.3)
            user_text = next(m['text'] for m in messages if m['role']=='user')
            assert 'short' in user_text.lower(), user_text
            print('PASS speech → STT → LLM → spoken reply → saved history', [(m['role'],m['text']) for m in messages], flush=True)
            memories = (await client.get('/memories',headers=auth)).json()
            assert any('short' in m['content'].lower() for m in memories), 'Explicit memory request was not saved'
            print('PASS evidence-backed voice memory:', memories[0]['content'])
            response = await client.delete('/voice/sessions/'+sid, headers=auth); response.raise_for_status()
            print('PASS call ends and room is removed')
            return {'audio_samples': audio['samples'], 'messages': len(messages)}
        finally:
            if pump:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            await room.disconnect()
            if source: await source.aclose()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if sid and auth: await client.delete('/voice/sessions/'+sid, headers=auth)
            if auth: await client.delete('/auth/me', headers=auth)

if __name__ == '__main__':
    try: print(asyncio.run(run()))
    except Exception as exc:
        print(f'FAIL real voice smoke test: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
