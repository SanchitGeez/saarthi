import { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { createAudioPlayer } from 'expo-audio';
import { CallController } from './controller';
import { prepareTransport } from './transport';
import { endCall, startCall } from '../api';
import { INITIAL_CALL, type CallState } from './types';

export function useVoiceSession() {
  const [state, setState] = useState<CallState>(INITIAL_CALL);
  const mounted = useRef(true);
  const bell = useRef<ReturnType<typeof createAudioPlayer> | null>(null);
  const controller = useRef<CallController | null>(null);
  if (!controller.current) controller.current = new CallController({
    prepare: prepareTransport, start: startCall, end: endCall,
    change: value => { if (mounted.current) setState(value); },
    bell: async () => {
      const player = createAudioPlayer(require('../../assets/temple-bell.wav'));
      bell.current = player; player.volume = 0.35;
      // Sound is a cue, not a prerequisite: audio routing/autoplay may block it.
      try { player.play(); await new Promise(resolve => setTimeout(resolve, 1200)); }
      finally { if (bell.current === player) { bell.current = null; player.remove(); } }
    },
  });
  useEffect(() => {
    mounted.current = true;
    const subscription = AppState.addEventListener('change', value => {
      if (value !== 'active') { bell.current?.remove(); bell.current = null; void controller.current?.end(); }
    });
    return () => { mounted.current = false; subscription.remove(); bell.current?.remove(); bell.current = null; void controller.current?.end(); };
  }, []);
  return { state,
    start: (id: string, requestId: string) => controller.current!.start(id, requestId),
    end: () => { bell.current?.remove(); bell.current = null; return controller.current!.end(); },
    mute: () => controller.current!.mute(),
    retryCleanup: () => controller.current!.retryCleanup(),
  };
}
