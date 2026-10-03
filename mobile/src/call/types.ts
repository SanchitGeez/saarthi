export type CallPhase = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'reconnecting' | 'ended' | 'error';
export type CallState = { phase: CallPhase; muted: boolean; caption: string; error: string; lit: boolean };
export type CallCredentials = { session_id: string; conversation_id: string; server_url: string; participant_token: string; expires_at: string };
export type TransportEvent = { phase?: CallPhase; caption?: string; ready?: boolean; error?: string; disconnected?: boolean };
export interface CallTransport {
  connect(credentials: CallCredentials): Promise<void>;
  ready(): Promise<void>;
  mute(value: boolean): Promise<void>;
  close(): Promise<void>;
}
export const INITIAL_CALL: CallState = { phase: 'idle', muted: false, caption: '', error: '', lit: false };
