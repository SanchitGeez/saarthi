import { PermissionsAndroid, Platform } from 'react-native';
import type { TransportEvent } from './types';

export async function prepareTransport(emit: (event: TransportEvent) => void) {
  // Lazy load so Expo Go can still use Type and show an actionable voice error.
  let sdk: typeof import('@livekit/react-native');
  try { sdk = await import('@livekit/react-native'); sdk.registerGlobals(); }
  catch { throw new Error('Live calls need the Saarthi development build. Expo Go supports Type only.'); }
  if (Platform.OS === 'android') {
    const permission = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
    if (permission !== PermissionsAndroid.RESULTS.GRANTED) throw new Error('Allow microphone access to talk with Parth, or use Type.');
  }
  await sdk.AudioSession.startAudioSession();
  try {
    const { Room, createLocalAudioTrack } = await import('livekit-client');
    const { roomTransport } = await import('./roomTransport');
    const mic = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true, autoGainControl: true });
    return roomTransport(new Room(), mic, emit, () => {}, () => {}, () => sdk.AudioSession.stopAudioSession());
  } catch (error) { await sdk.AudioSession.stopAudioSession(); throw error; }
}
