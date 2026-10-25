/* Browser media only. Provider credentials and conversation state stay on the server. */
window.saarthiVoice = (() => {
  let active = false, epoch = 0, peer, channel, stream, sessionId, keepalive;
  let retries = 0, conversationId, reconnecting = false, responseId, connecting = false;
  let liveTranscript = '';
  const audio = document.getElementById('voice-audio');
  const status = value => { document.getElementById('voice-status').textContent = value; };
  const captions = value => { document.getElementById('voice-caption').textContent = value; };
  const transcript = value => {
    liveTranscript = value;
    document.getElementById('voice-transcript').textContent = value ? `Live speech: ${value}` : '';
  };
  const emit = () => window.dispatchEvent(new CustomEvent('voicechange', { detail: { active } }));
  async function request(path, method, body) {
    const response = await fetch(path, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) {
      const result = await response.json();
      const error = new Error(result.error?.message || 'Voice connection failed.');
      error.retryable = response.status >= 500 && !['voice_disabled', 'voice_not_configured', 'voice_dependencies'].includes(result.error?.code);
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  async function cleanup() {
    clearInterval(keepalive);
    const oldId = sessionId;
    sessionId = null;
    if (peer) { peer.onconnectionstatechange = null; peer.close(); peer = null; }
    channel = null;
    stream?.getTracks().forEach(track => track.stop()); stream = null;
    audio.pause(); audio.srcObject = null;
    if (oldId) await request(`/voice/sessions/${oldId}`, 'DELETE').catch(() => {});
  }
  async function stop() {
    ++epoch; active = false; connecting = false;
    emit(); status('Leaving voice…'); captions(''); transcript('');
    await cleanup(); status('Voice off. Your chat is still active.');
    window.dispatchEvent(new Event('voicefinal'));
  }
  function event(message, currentEpoch) {
    if (currentEpoch !== epoch || message.type !== 'voice') return;
    switch (message.event) {
      case 'responding':
        responseId = message.response_id;
        audio.muted = false;
        status('Saarthi is responding…');
        break;
      case 'caption': captions(message.text); break;
      case 'transcript': transcript(message.text); status('Listening…'); break;
      case 'user_turn':
        if (liveTranscript.trim() === message.text.trim()) transcript('');
        window.dispatchEvent(new CustomEvent('voiceuser', { detail: message }));
        break;
      case 'clear': {
        const old = responseId; audio.muted = true;
        // Bounded WebRTC jitter tail; server also clears synthesis and media queues.
        setTimeout(() => { if (currentEpoch === epoch && responseId === old) audio.muted = false; }, 350);
        break;
      }
      case 'retrying': captions(message.text); status(message.message || `Reconnecting speech service (attempt ${message.attempt})…`); break;
      case 'final': captions(message.text + (message.interrupted ? ' · Interrupted' : '')); window.dispatchEvent(new Event('voicefinal')); break;
      case 'listening': status('Listening. You can speak naturally.'); break;
      case 'error': status(message.message); break;
      case 'reconnect': recover(currentEpoch); break;
      case 'ended': stop(); break;
    }
  }
  async function connect(currentEpoch, resume) {
    connecting = true;
    status(resume ? 'Reconnecting… Please repeat speech from the disconnected interval.' : 'Allow microphone access to start voice.');
    const captured = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false });
    if (currentEpoch !== epoch) { captured.getTracks().forEach(track => track.stop()); return; }
    stream = captured;
    const settings = stream.getAudioTracks()[0].getSettings();
    document.getElementById('voice-capture').textContent = settings.echoCancellation === true ? 'Echo cancellation enabled' : 'Echo cancellation is unavailable or unconfirmed on this device';
    sessionId = crypto.randomUUID();
    const id = sessionId;
    await request('/voice/sessions', 'POST', { id, conversation_id: conversationId, resume });
    if (currentEpoch !== epoch) { await request(`/voice/sessions/${id}`, 'DELETE'); return; }
    peer = new RTCPeerConnection({ iceServers: [] });
    const pc = peer;
    stream.getTracks().forEach(track => pc.addTrack(track, stream));
    channel = pc.createDataChannel('saarthi');
    const dc = channel;
    let playing = false, sentReady = false;
    function ready() {
      if (!sentReady && playing && dc.readyState === 'open' && currentEpoch === epoch) {
        sentReady = true; dc.send(JSON.stringify({ type: 'ready' }));
        keepalive = setInterval(() => { if (dc.readyState === 'open') dc.send('ping'); }, 1000);
        connecting = false; retries = 0; status('Connected.');
      }
    }
    dc.onopen = ready;
    dc.onmessage = e => { try { event(JSON.parse(e.data), currentEpoch); } catch { /* Ignore unrelated signaling. */ } };
    pc.ontrack = async e => {
      if (currentEpoch !== epoch) return;
      audio.srcObject = new MediaStream([e.track]); audio.muted = false;
      try { await audio.play(); playing = true; ready(); }
      catch { status('Press Play audio to allow browser playback.'); document.getElementById('voice-play').hidden = false; }
    };
    document.getElementById('voice-play').onclick = async () => { await audio.play(); playing = true; ready(); document.getElementById('voice-play').hidden = true; };
    pc.onconnectionstatechange = () => {
      if (currentEpoch === epoch && ['failed', 'disconnected', 'closed'].includes(pc.connectionState)) recover(currentEpoch);
    };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((resolve, reject) => {
      if (pc.iceGatheringState === 'complete') return resolve();
      const timer = setTimeout(() => reject(new Error('Local media negotiation timed out.')), 10000);
      pc.addEventListener('icegatheringstatechange', () => { if (pc.iceGatheringState === 'complete') { clearTimeout(timer); resolve(); } });
    });
    if (currentEpoch !== epoch) return;
    const answer = await request(`/voice/sessions/${id}/offer`, 'POST', { sdp: pc.localDescription.sdp, type: 'offer' });
    if (currentEpoch !== epoch) return;
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    setTimeout(() => { if (currentEpoch === epoch && connecting) recover(currentEpoch); }, 15000);
  }
  async function recover(currentEpoch) {
    if (reconnecting || !active || currentEpoch !== epoch) return;
    reconnecting = true;
    try {
      while (active && currentEpoch === epoch && retries < 3) {
        await cleanup();
        const delay = 1000 * 2 ** retries++ + Math.random() * 250;
        status(`Reconnecting voice (attempt ${retries})…`);
        await new Promise(resolve => setTimeout(resolve, delay));
        if (!active || currentEpoch !== epoch) return;
        try { await connect(currentEpoch, true); return; }
        catch (error) { if (error.retryable === false) throw error; }
      }
      if (active && currentEpoch === epoch) throw new Error('Could not reconnect. Leave voice and try again.');
    } catch (error) { await stop(); status(error.message); }
    finally { reconnecting = false; }
  }
  async function start(id) {
    if (active) return;
    if (!window.isSecureContext || !navigator.mediaDevices) { status('Voice needs localhost or HTTPS and microphone access.'); return; }
    active = true; retries = 0; conversationId = id; transcript(''); const currentEpoch = ++epoch; emit();
    try { await connect(currentEpoch, false); }
    catch (error) {
      if (currentEpoch !== epoch) return;
      if (error.retryable) await recover(currentEpoch);
      else { await stop(); status(error.message); }
    }
  }
  document.getElementById('voice-stop-speaking').onclick = () => { if (channel?.readyState === 'open') channel.send(JSON.stringify({ type: 'stop' })); };
  document.getElementById('voice-mute').onclick = () => {
    if (!stream) return;
    const track = stream.getAudioTracks()[0]; track.enabled = !track.enabled;
    document.getElementById('voice-mute').textContent = track.enabled ? 'Mute microphone' : 'Unmute microphone';
  };
  window.addEventListener('pagehide', () => {
    ++epoch; stream?.getTracks().forEach(track => track.stop()); peer?.close();
    if (sessionId) fetch(`/voice/sessions/${sessionId}`, { method: 'DELETE', credentials: 'same-origin', keepalive: true });
  });
  return { start, stop, get active() { return active; } };
})();
