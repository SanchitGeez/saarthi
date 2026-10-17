const $ = id => document.getElementById(id);
const state = { user: null, current: null, history: [], cursor: null, active: null, busy: false, edit: null };
function text(tag, value) { const node = document.createElement(tag); node.textContent = value; return node; }
function visible(id, value) { $(id).hidden = !value; }
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' });
  const result = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401) { state.user = null; state.current = null; showEntry(); }
    const error = new Error(result?.error?.message || 'Request failed. Please retry.');
    error.code = result?.error?.code;
    throw error;
  }
  return result;
}
const post = (path, body) => api(path, { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
async function action(label, work) {
  if (state.busy) return;
  state.busy = true;
  $('notice').textContent = label;
  visible('error', false);
  document.querySelectorAll('button').forEach(button => button.disabled = true);
  try { await work(); } catch (error) { $('error').textContent = error.message; visible('error', true); }
  finally { state.busy = false; $('notice').textContent = ''; document.querySelectorAll('button').forEach(button => button.disabled = false); }
}
function showEntry() {
  visible('login', !state.user); visible('onboarding', !!state.user?.onboarding_required);
  visible('workspace', !!state.user && !state.user.onboarding_required); visible('logout', !!state.user);
}
async function history(more = false) {
  const result = await api('/conversations' + (more && state.cursor ? '?before=' + encodeURIComponent(state.cursor) : ''));
  state.history = more ? [...state.history, ...result.items] : result.items;
  state.cursor = result.next_cursor; state.active = result.active_conversation_id;
  renderHistory();
}
function renderHistory() {
  $('history').replaceChildren();
  for (const conversation of state.history) {
    const pending = conversation.status === 'ended' && conversation.knowledge_status !== 'completed';
    const button = text('button', `${conversation.title} (${conversation.status})${pending ? ' — knowledge not updated' : ''}`);
    button.setAttribute('aria-current', String(state.current?.conversation.id === conversation.id));
    button.onclick = () => action('Loading conversation…', () => openChat(conversation.id));
    $('history').append(button);
  }
  visible('more-history', !!state.cursor);
  $('new-chat').textContent = state.active ? 'Resume active conversation' : 'New conversation';
}
async function openChat(id) {
  state.current = await api(`/conversations/${id}`);
  visible('chat', true); visible('knowledge-panel', false);
  renderChat(); renderHistory();
}
function renderChat() {
  const current = state.current;
  $('messages').replaceChildren();
  if (!current) {
    $('chat-title').textContent = 'Conversation ended'; $('chat-status').textContent = 'Choose New conversation when you are ready.';
    for (const id of ['end-chat', 'message-form', 'retry-extraction', 'retry-message']) visible(id, false);
    return;
  }
  const conv = current.conversation, ended = conv.status === 'ended';
  const pending = conv.generation_status !== 'idle' || !current.messages.length;
  $('chat-title').textContent = conv.title;
  $('chat-status').textContent = ended ? (conv.knowledge_status === 'completed' ? 'Ended · knowledge saved.' : 'Ended · knowledge has not been updated. Retry extraction; you can also start a new conversation.') : pending ? 'A reply is pending. Retry uses the saved message and will not duplicate it.' : 'Active conversation';
  for (const message of current.messages) {
    const node = text('article', ''); node.className = 'message';
    node.append(text('strong', message.role === 'user' ? 'You' : 'Saarthi'), text('p', message.content));
    $('messages').append(node);
  }
  visible('end-chat', !ended); visible('message-form', !ended && !pending);
  visible('retry-extraction', ended && conv.knowledge_status !== 'completed'); visible('retry-message', !ended && pending);
}
async function createChat() {
  if (state.active) return openChat(state.active);
  const id = crypto.randomUUID();
  try { await post('/conversations', { id }); }
  finally { await history(); if (state.active) await openChat(state.active); }
}
async function enter() {
  showEntry();
  if (!state.user || state.user.onboarding_required) return;
  await history();
  if (state.active) await openChat(state.active); else await createChat();
}
$('phone-form').onsubmit = event => { event.preventDefault(); action('Preparing mock login…', async () => {
  const result = await post('/auth/otp/request', { phone: $('phone').value });
  $('phone').value = result.phone; visible('phone-form', false); visible('otp-form', true); $('otp').focus();
}); };
$('change-phone').onclick = () => { visible('phone-form', true); visible('otp-form', false); };
$('otp-form').onsubmit = event => { event.preventDefault(); action('Signing in…', async () => {
  const result = await post('/auth/otp/verify', { phone: $('phone').value, otp: $('otp').value });
  state.user = result.user; $('otp').value = ''; await enter();
}); };
$('profile-form').onsubmit = event => { event.preventDefault(); action('Saving profile…', async () => {
  state.user = await api('/me', { method: 'PATCH', body: JSON.stringify({ name: $('name').value, gender: $('gender').value, age: Number($('age').value) }) });
  await enter();
}); };
$('logout').onclick = () => action('Signing out…', async () => {
  await post('/auth/logout'); state.user = null; state.current = null; state.history = []; state.edit = null;
  $('message').value = ''; $('knowledge-content').value = ''; $('knowledge-list').replaceChildren(); $('messages').replaceChildren();
  visible('phone-form', true); visible('otp-form', false); showEntry();
});
$('new-chat').onclick = () => action('Opening conversation…', async () => { visible('chat', true); visible('knowledge-panel', false); await history(); await createChat(); });
$('more-history').onclick = () => action('Loading history…', () => history(true));
$('message-form').onsubmit = event => { event.preventDefault(); action('Saarthi is thinking…', async () => {
  const content = $('message').value.trim(); if (!content) return;
  const conversationId = state.current.conversation.id, id = crypto.randomUUID();
  let accepted = false;
  try { await post(`/conversations/${conversationId}/messages`, { id, content }); accepted = true; }
  finally {
    await openChat(conversationId); await history();
    if (accepted || state.current.messages.some(message => message.id === id)) $('message').value = '';
  }
}); };
$('retry-message').onclick = () => action('Retrying reply…', async () => {
  const { conversation, messages } = state.current;
  const pending = messages.find(message => message.id === conversation.generation_message_id);
  try {
    if (pending) await post(`/conversations/${conversation.id}/messages`, { id: pending.id, content: pending.content });
    else await post('/conversations', { id: conversation.id });
  } finally { await openChat(conversation.id); await history(); }
});
async function endChat() {
  const id = state.current.conversation.id;
  try { await post(`/conversations/${id}/end`); }
  finally { await openChat(id); await history(); }
}
$('end-chat').onclick = () => action('Saarthi is saving what it learned…', endChat);
$('retry-extraction').onclick = () => action('Retrying knowledge extraction…', endChat);
function resetKnowledgeForm() {
  state.edit = null; $('knowledge-form').reset(); $('save-knowledge').textContent = 'Add knowledge'; visible('cancel-knowledge', false);
}
async function showKnowledge(more = false) {
  const result = await api('/knowledge' + (more && state.knowledgeCursor ? '?after=' + state.knowledgeCursor : ''));
  state.knowledgeCursor = result.next_cursor; visible('more-knowledge', !!state.knowledgeCursor);
  visible('chat', false); visible('knowledge-panel', true); if (!more) $('knowledge-list').replaceChildren();
  if (!result.items.length) $('knowledge-list').append(text('p', 'No knowledge saved yet.'));
  for (const record of result.items) {
    const node = text('article', ''); node.className = 'knowledge-record';
    node.append(text('strong', `${record.type} · ${record.status}`), text('p', record.content), text('p', record.source_conversation_id ? `Source conversation: ${record.source_conversation_id}` : 'Manually added'));
    const edit = text('button', 'Edit'); edit.onclick = () => {
      state.edit = record.id; $('knowledge-type').value = record.type; $('knowledge-content').value = record.content; $('knowledge-status').value = record.status;
      $('save-knowledge').textContent = 'Save changes'; visible('cancel-knowledge', true); $('knowledge-content').focus();
    };
    const remove = text('button', 'Delete'); remove.onclick = () => action('Deleting knowledge…', async () => {
      await api(`/knowledge/${record.id}`, { method: 'DELETE' }); resetKnowledgeForm(); await showKnowledge();
    });
    node.append(edit, remove); $('knowledge-list').append(node);
  }
}
$('more-knowledge').onclick = () => action('Loading knowledge…', () => showKnowledge(true));
$('show-knowledge').onclick = () => action('Loading knowledge…', showKnowledge);
$('close-knowledge').onclick = () => { visible('knowledge-panel', false); visible('chat', true); };
$('cancel-knowledge').onclick = resetKnowledgeForm;
$('knowledge-form').onsubmit = event => { event.preventDefault(); action('Saving knowledge…', async () => {
  const body = { type: $('knowledge-type').value, content: $('knowledge-content').value, status: $('knowledge-status').value };
  await api(state.edit ? `/knowledge/${state.edit}` : '/knowledge', { method: state.edit ? 'PATCH' : 'POST', body: JSON.stringify(body) });
  resetKnowledgeForm(); await showKnowledge();
}); };
action('Loading…', async () => {
  try { state.user = await api('/me'); } catch (error) { if (error.code !== 'unauthenticated') throw error; }
  await enter();
});
