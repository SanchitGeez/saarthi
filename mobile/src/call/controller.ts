import { INITIAL_CALL, type CallCredentials, type CallState, type CallTransport, type TransportEvent } from './types';

type Dependencies = {
  prepare: (emit: (event: TransportEvent) => void) => Promise<CallTransport>;
  start: (conversationId: string, requestId: string) => Promise<CallCredentials>;
  end: (sessionId: string) => Promise<void>;
  bell: () => Promise<void>;
  change: (state: CallState) => void;
};

/** Own every acquired resource, even when End is pressed during an awaited step. */
export class CallController {
  state: CallState = { ...INITIAL_CALL };
  private generation = 0;
  private transport: CallTransport | null = null;
  private sessionId: string | null = null;
  private ending: Promise<void> | null = null;
  private busy = false;
  private welcomed = false;
  private pendingEnd = new Set<string>();
  private muteBusy = false;
  private expiry: ReturnType<typeof setTimeout> | null = null;
  constructor(private deps: Dependencies) {}
  private change(patch: Partial<CallState>) { this.state = { ...this.state, ...patch }; this.deps.change(this.state); }
  async start(conversationId: string, requestId: string) {
    if (this.busy || this.transport || this.ending) return;
    this.busy = true; this.welcomed = false;
    const version = ++this.generation;
    this.change({ ...INITIAL_CALL, phase: 'connecting' });
    let transport: CallTransport | null = null;
    let credentials: CallCredentials | null = null;
    try {
      // Resolve earlier cleanup first. Never open two rooms after an uncertain End.
      await this.retryCleanup();
      if (version !== this.generation) return;
      transport = await this.deps.prepare(event => {
        if (version !== this.generation) return;
        if (event.error) {
          const message = event.error;
          void this.end().then(() => this.change({ phase: 'error', error: message })); return;
        }
        if (event.disconnected) { void this.end(); return; }
        if (event.caption !== undefined) this.change({ caption: event.caption });
        if (event.phase && this.welcomed) this.change({ phase: event.phase });
      });
      if (version !== this.generation) { await transport.close(); return; }
      this.transport = transport;
      // The client ID is also the server session ID, so a lost response can be closed.
      this.sessionId = requestId;
      credentials = await this.deps.start(conversationId, requestId);
      if (version !== this.generation) { await this.closeServer(credentials.session_id); return; }
      this.sessionId = credentials.session_id;
      this.expiry = setTimeout(() => { void this.end(); }, Math.max(0, new Date(credentials.expires_at).getTime() - Date.now()));
      await transport.connect(credentials);
      if (version !== this.generation) return;
      this.change({ lit: true });
      await this.deps.bell();
      if (version !== this.generation) return;
      this.welcomed = true;
      this.change({ phase: 'listening' });
      await transport.ready();
    } catch (error) {
      if (version === this.generation) {
        const message = error instanceof Error ? error.message : 'Couldn’t connect. Please try again.';
        await this.end();
        this.change({ phase: 'error', error: message, lit: false });
      }
    } finally {
      this.busy = false;
    }
  }
  private async closeServer(id: string) {
    this.pendingEnd.add(id);
    try { await this.deps.end(id); this.pendingEnd.delete(id); }
    catch { this.change({ error: 'Your microphone is off. Closing the call needs a retry.' }); }
  }
  async retryCleanup() {
    for (const id of [...this.pendingEnd]) await this.closeServer(id);
    if (this.pendingEnd.size) throw new Error('The previous call is still closing. Please retry.');
  }
  async mute() {
    if (!this.transport || this.muteBusy || !this.welcomed) return;
    this.muteBusy = true;
    try { const next = !this.state.muted; await this.transport.mute(next); this.change({ muted: next }); }
    catch { this.change({ error: 'Couldn’t change the microphone. End the call and try again.' }); }
    finally { this.muteBusy = false; }
  }
  async end() {
    if (this.ending) return this.ending;
    ++this.generation; this.welcomed = false;
    if (this.expiry) clearTimeout(this.expiry); this.expiry = null;
    const transport = this.transport, id = this.sessionId;
    this.transport = null; this.sessionId = null;
    this.change({ phase: 'ended', muted: false, lit: false, caption: '' });
    this.ending = (async () => {
      try { await transport?.close(); } catch { /* server close still runs */ }
      if (id) await this.closeServer(id);
    })();
    try { await this.ending; } finally { this.ending = null; }
  }
}
