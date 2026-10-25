const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

// Run the shipped browser scripts with fake media and an in-memory HTTP boundary.
async function browser() {
  class Element {
    textContent = '';
    children = [];
    value = '';
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
    pause() {}
    reset() {}
  }
  const nodes = new Map();
  const document = {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, new Element());
      return nodes.get(id);
    },
    createElement: () => new Element(),
    querySelectorAll: () => [],
  };
  const database = {
    conversation: { id: 'conversation', title: 'Voice test', status: 'active', generation_status: 'idle' },
    messages: [{ id: 'greeting', role: 'assistant', content: 'Haan, bolo.', delivery_status: 'complete' }],
  };
  const events = new EventTarget();
  let channel, deferredChat;
  const context = vm.createContext({
    document, Event, CustomEvent, console,
    addEventListener: events.addEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
    isSecureContext: true,
    crypto: { randomUUID: () => 'session' },
    navigator: { mediaDevices: { getUserMedia: async () => ({
      getTracks: () => [], getAudioTracks: () => [{ getSettings: () => ({ echoCancellation: true }) }],
    }) } },
    RTCPeerConnection: class {
      iceGatheringState = 'complete';
      localDescription = { sdp: 'test' };
      createDataChannel() { channel = {}; return channel; }
      async createOffer() { return {}; }
      async setLocalDescription() {}
      async setRemoteDescription() {}
      close() {}
    },
    setTimeout: () => 1, clearInterval() {},
    fetch: async path => {
      let value;
      if (path === '/me') value = { id: 'user', onboarding_required: false };
      else if (path === '/conversations') value = { items: [database.conversation], active_conversation_id: 'conversation' };
      else if (path === '/conversations/conversation') {
        value = structuredClone(database);
        if (deferredChat) {
          const callback = deferredChat;
          deferredChat = null;
          await new Promise(resolve => callback(resolve));
        }
      } else value = {};
      return { ok: true, status: 200, json: async () => structuredClone(value) };
    },
  });
  context.window = context;
  for (const file of ['voice.js', 'app.js']) {
    vm.runInContext(readFileSync(join(__dirname, '..', file), 'utf8'), context);
  }
  // Drain the async initial page load; no clocks or external requests are involved.
  for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  await context.saarthiVoice.start('conversation');
  const send = (event, values) => channel.onmessage({ data: JSON.stringify({ type: 'voice', event, ...values }) });
  const saved = () => vm.runInContext('state.current.messages.map(message => message.content)', context);
  return {
    context, nodes, send, saved,
    deferNextChat(callback) { deferredChat = callback; },
    accept(text, id, conversation = 'conversation') {
      if (conversation === 'conversation' && !database.messages.some(message => message.id === id)) {
        database.messages.push({ id, role: 'user', content: text, delivery_status: 'complete' });
      }
      send('user_turn', { text, message_id: id, conversation_id: conversation });
    },
  };
}

test('saved speech remains visible when the live transcript advances to its tail', async () => {
  const page = await browser();
  const prefix = 'मैं क्या बोल रहा था मैं भूल गया. क्या तुम बोल सकते हो मैंने last';
  page.send('transcript', { text: prefix });
  page.accept(prefix, 'first');
  page.send('transcript', { text: 'क्या बोला?' });
  assert.ok(page.saved().includes(prefix));
  assert.equal(page.nodes.get('voice-transcript').textContent, 'Live speech: क्या बोला?');
  page.accept('क्या बोला?', 'second');
  assert.ok(page.saved().includes('क्या बोला?'));
  assert.equal(page.nodes.get('messages').children.length, 3);
  assert.equal(page.nodes.get('voice-transcript').textContent, '');
});

test('a delayed acceptance does not erase newer live speech or duplicate a bubble', async () => {
  const page = await browser();
  page.send('transcript', { text: 'but party थी तो मैं काम कर ही नहीं पाया' });
  page.accept('मैं सोचा था', 'first');
  page.accept('मैं सोचा था', 'first');
  assert.equal(page.nodes.get('voice-transcript').textContent, 'Live speech: but party थी तो मैं काम कर ही नहीं पाया');
  assert.equal(page.nodes.get('messages').children.length, 2);
  page.accept('another conversation', 'unrelated', 'other');
  assert.equal(page.nodes.get('messages').children.length, 2);
});

test('an older chat refresh cannot overwrite a newly saved voice message', async () => {
  const page = await browser();
  let release;
  page.deferNextChat(resolve => { release = resolve; });
  const oldRefresh = vm.runInContext("openChat('conversation')", page.context);
  page.accept('earlier words survived', 'first');
  release();
  await oldRefresh;
  assert.ok(page.saved().includes('earlier words survived'));
});

test('the newest chat refresh wins when HTTP responses arrive out of order', async () => {
  const page = await browser();
  let release;
  page.deferNextChat(resolve => { release = resolve; });
  const oldRefresh = vm.runInContext("openChat('conversation')", page.context);
  page.accept('new fragment', 'first');
  await vm.runInContext("openChat('conversation')", page.context);
  release();
  await oldRefresh;
  assert.ok(page.saved().includes('new fragment'));
});
