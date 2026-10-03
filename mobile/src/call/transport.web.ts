import { createLocalAudioTrack, Room } from 'livekit-client';
import { roomTransport } from './roomTransport';
import type { TransportEvent } from './types';

export async function prepareTransport(emit: (event: TransportEvent) => void) {
  if (!globalThis.isSecureContext || !navigator.mediaDevices) throw new Error('Live calls need HTTPS or localhost. You can still use Type.');
  const mic = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true, autoGainControl: true });
  const elements = new Set<HTMLMediaElement>();
  try {
    return roomTransport(new Room(), mic, emit, track => {
      const element = track.attach(); element.style.display = 'none'; document.body.appendChild(element);
      elements.add(element); void element.play().catch(() => {});
    }, () => { elements.forEach(el => { el.pause(); el.srcObject = null; el.remove(); }); elements.clear(); }, async () => {});
  } catch (error) { mic.stop(); throw error; }
}
