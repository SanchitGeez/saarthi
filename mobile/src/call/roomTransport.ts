import { ParticipantKind, Room, RoomEvent, Track, type LocalAudioTrack, type RemoteTrack, type RemoteParticipant } from 'livekit-client';
import type { CallCredentials, CallTransport, TransportEvent } from './types';

export function roomTransport(room: Room, mic: LocalAudioTrack,
  emit: (event: TransportEvent) => void, attach: (track: RemoteTrack) => void,
  detach: () => void, stopAudio: () => Promise<void>): CallTransport {
  let closed = false, agent: RemoteParticipant | undefined;
  let resolveReady: (() => void) | null = null;
  let rejectReady: ((error: Error) => void) | null = null;
  const agentReady = new Promise<void>((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  // An early rejection must be handled even while room.connect is pending.
  void agentReady.catch(() => {});
  function sync() {
    agent = [...room.remoteParticipants.values()].find(p => p.kind === ParticipantKind.AGENT);
    const state = agent?.attributes['lk.agent.state'];
    if (state === 'speaking' || state === 'thinking' || state === 'listening') emit({ phase: state });
    if (state && state !== 'initializing' && agent?.getTrackPublication(Track.Source.Microphone)?.isSubscribed) resolveReady?.();
  }
  room.on(RoomEvent.ParticipantConnected, sync);
  room.on(RoomEvent.ParticipantAttributesChanged, sync);
  room.on(RoomEvent.TrackSubscribed, (track, _, participant) => {
    if (track.kind === Track.Kind.Audio && participant.kind === ParticipantKind.AGENT) { attach(track); sync(); }
  });
  room.on(RoomEvent.TrackUnsubscribed, track => { if (track.kind === Track.Kind.Audio) track.detach(); });
  room.on(RoomEvent.DataReceived, (data, participant, _, topic) => {
    if (topic !== 'saarthi.error' || participant?.kind !== ParticipantKind.AGENT) return;
    try { const payload = JSON.parse(new TextDecoder().decode(data)); if (typeof payload.error === 'string') emit({ error: payload.error }); } catch {}
  });
  room.on(RoomEvent.Reconnecting, () => emit({ phase: 'reconnecting' }));
  room.on(RoomEvent.Reconnected, sync);
  room.on(RoomEvent.Disconnected, () => { rejectReady?.(new Error('The call disconnected. Please try again.')); if (!closed) emit({ disconnected: true }); });
  room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
    const segment = segments[segments.length - 1];
    if (segment) emit({ caption: `${participant?.kind === ParticipantKind.AGENT ? 'Parth' : 'You'}: ${segment.text}` });
  });
  room.registerTextStreamHandler('lk.transcription', async (reader, participant) => {
    let text = '';
    for await (const chunk of reader) {
      if (closed) return;
      text += chunk;
      emit({ caption: `${participant.identity === agent?.identity ? 'Parth' : 'You'}: ${text}` });
    }
  });
  return {
    async connect(credentials: CallCredentials) {
      if (closed) throw new Error('Call cancelled.');
      await room.connect(credentials.server_url, credentials.participant_token, { autoSubscribe: true });
      if (closed) { await room.disconnect(); return; }
      await room.startAudio();
      sync();
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([agentReady, new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error('Parth couldn’t join the call. Please try again or use Type.')), 30000);
        })]);
      } finally { if (timer) clearTimeout(timer); }
      if (Date.now() >= new Date(credentials.expires_at).getTime()) throw new Error('This call has expired. Start again.');
    },
    async ready() {
      if (closed || !agent) throw new Error('Call disconnected.');
      await room.localParticipant.publishTrack(mic, { source: Track.Source.Microphone });
      await room.localParticipant.performRpc({ destinationIdentity: agent.identity, method: 'saarthi.ready', payload: '', responseTimeout: 10000 });
    },
    async mute(value) { if (value) await mic.mute(); else await mic.unmute(); },
    async close() {
      if (closed) return;
      closed = true;
      // Stop capture before any network await.
      mic.stop(); detach();
      rejectReady?.(new Error('Call cancelled.'));
      room.removeAllListeners();
      try { await room.disconnect(); } finally { await stopAudio(); }
    },
  };
}
