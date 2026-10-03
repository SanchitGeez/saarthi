import { CallController } from '../src/call/controller';
import type { CallCredentials, TransportEvent } from '../src/call/types';
const deferred = <T,>() => { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const credentials: CallCredentials = { session_id: 'session-1', conversation_id: 'chat-1', participant_token: 'test-only', server_url: 'ws://localhost', expires_at: new Date(Date.now() + 900000).toISOString() };
function fixture() {
  let emit!: (event: TransportEvent) => void;
  const transport = { connect: jest.fn(async () => {}), ready: jest.fn(async () => {}), close: jest.fn(async () => {}), mute: jest.fn(async () => {}) };
  const deps = { prepare: jest.fn(async (callback: typeof emit) => { emit = callback; return transport; }), start: jest.fn(async () => credentials), end: jest.fn(async () => {}), bell: jest.fn(async () => {}), change: jest.fn() };
  const controller = new CallController(deps);
  return { transport, deps, controller, emit: (event: TransportEvent) => emit(event) };
}

afterEach(() => jest.useRealTimers());
test('bell precedes readiness, states come from agent, End closes mic and server', async () => {
  const f = fixture(); const order: string[] = [];
  f.deps.bell.mockImplementation(async () => { order.push('bell'); });
  f.transport.ready.mockImplementation(async () => { order.push('ready'); });
  await f.controller.start('chat-1', 'request');
  expect(order).toEqual(['bell', 'ready']); expect(f.controller.state.lit).toBe(true);
  f.emit({ phase: 'speaking', caption: 'Parth: hello' }); expect(f.controller.state.phase).toBe('speaking');
  await f.controller.mute(); expect(f.transport.mute).toHaveBeenCalledWith(true);
  expect(f.controller.state.muted).toBe(true);
  await f.controller.end(); expect(f.transport.close).toHaveBeenCalledTimes(1);
  expect(f.deps.end).toHaveBeenCalledWith('session-1'); expect(f.controller.state.lit).toBe(false);
});
test('duplicate starts do not acquire another mic or session', async () => {
  const f = fixture(); const pending = deferred<CallCredentials>(); f.deps.start.mockReturnValue(pending.promise);
  const one = f.controller.start('chat-1','one'); const two = f.controller.start('chat-1','two');
  await Promise.resolve(); await Promise.resolve(); pending.resolve(credentials);
  await Promise.all([one,two]); expect(f.deps.prepare).toHaveBeenCalledTimes(1); expect(f.deps.start).toHaveBeenCalledTimes(1);
  await f.controller.end();
});
test('cancelling during microphone permission closes the acquired mic and never starts a room', async () => {
  const f = fixture(); const pending = deferred<typeof f.transport>(); f.deps.prepare.mockReturnValue(pending.promise);
  const start = f.controller.start('chat-1','one'); await Promise.resolve(); await Promise.resolve();
  await f.controller.end(); pending.resolve(f.transport); await start;
  expect(f.transport.close).toHaveBeenCalledTimes(1); expect(f.deps.start).not.toHaveBeenCalled(); expect(f.deps.bell).not.toHaveBeenCalled();
});
test('cancelling while API is pending closes the room when its response arrives', async () => {
  const f = fixture(); const pending = deferred<CallCredentials>(); f.deps.start.mockReturnValue(pending.promise);
  const start = f.controller.start('chat-1','one'); await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  await f.controller.end(); pending.resolve(credentials); await start;
  expect(f.transport.close).toHaveBeenCalledTimes(1); expect(f.deps.end).toHaveBeenCalledWith('one'); expect(f.deps.end).toHaveBeenCalledWith('session-1'); expect(f.transport.connect).not.toHaveBeenCalled();
});
test('permission failure offers retry without calling API', async () => {
  const f = fixture(); f.deps.prepare.mockRejectedValue(new Error('Allow microphone access'));
  await f.controller.start('chat-1','one'); expect(f.controller.state.phase).toBe('error'); expect(f.controller.state.error).toContain('microphone'); expect(f.deps.start).not.toHaveBeenCalled();
});
test('connection timeout and provider failure clean up resources', async () => {
  const f = fixture(); f.transport.connect.mockRejectedValue(new Error('Parth couldn’t join'));
  await f.controller.start('chat-1','one'); expect(f.transport.close).toHaveBeenCalled(); expect(f.deps.end).toHaveBeenCalled(); expect(f.controller.state.lit).toBe(false);
});
test('reconnect changes state without replaying bell/readiness, stale events ignored after End', async () => {
  const f = fixture(); await f.controller.start('chat-1','one');
  f.emit({ phase:'reconnecting' }); expect(f.controller.state.phase).toBe('reconnecting');
  f.emit({ phase:'listening' }); expect(f.deps.bell).toHaveBeenCalledTimes(1); expect(f.transport.ready).toHaveBeenCalledTimes(1);
  await f.controller.end(); f.emit({ phase:'speaking' }); expect(f.controller.state.phase).toBe('ended');
});
test('failed server cleanup must succeed before starting another call', async () => {
  const f = fixture(); await f.controller.start('chat-1','one'); f.deps.end.mockRejectedValue(new Error('network'));
  await f.controller.end(); await f.controller.start('chat-1','two'); expect(f.deps.start).toHaveBeenCalledTimes(1);
  f.deps.end.mockResolvedValue(); await f.controller.start('chat-1','three'); expect(f.deps.start).toHaveBeenCalledTimes(2); await f.controller.end();
});
test('absolute deadline ends the call and microphone', async () => {
  jest.useFakeTimers(); const f = fixture(); f.deps.start.mockResolvedValue({ ...credentials, expires_at: new Date(Date.now()+2000).toISOString() });
  await f.controller.start('chat-1','one'); await jest.advanceTimersByTimeAsync(2001);
  expect(f.controller.state.phase).toBe('ended'); expect(f.transport.close).toHaveBeenCalled(); expect(f.deps.end).toHaveBeenCalled();
});

test('lost start response still closes the known request ID', async () => {
  const f = fixture(); f.deps.start.mockRejectedValue(new Error('The connection took too long'));
  await f.controller.start('chat-1','lost-request'); expect(f.deps.end).toHaveBeenCalledWith('lost-request'); expect(f.transport.close).toHaveBeenCalled();
});
test('worker error closes the microphone and presents a retryable message', async () => {
  const f = fixture(); await f.controller.start('chat-1','one');
  f.emit({ error:'Parth couldn’t complete the call. Please use Type.' });
  await f.controller.end(); await Promise.resolve();
  expect(f.transport.close).toHaveBeenCalled(); expect(f.controller.state.error).toContain('Type');
});
