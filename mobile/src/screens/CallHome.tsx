import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, ActivityIndicator, Animated, BackHandler, Modal, Platform, Pressable, StatusBar, StyleSheet, Text, View } from 'react-native';
import { randomUUID } from 'expo-crypto';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { createConversation, deleteConversation, getCallStatus, getConversations } from '../api';
import { useVoiceSession } from '../call/useVoiceSession';
import { Icon } from '../components/Icons';
import { ConversationDrawer } from '../components/ConversationDrawer';
import { useModalAccessibility } from '../components/useModalAccessibility';
import { ChatHome } from './ChatHome';
import { MemorySettings } from './MemorySettings';
import type { Conversation, User } from '../types';

const phaseLabel = { idle: 'Take your time', connecting: 'Connecting with Parth…', listening: 'Parth is listening', thinking: 'Parth is reflecting…', speaking: 'Parth is speaking', reconnecting: 'Reconnecting…', ended: 'Come back whenever you like', error: 'Let’s try again' };
export function CallHome({ user, onSignOut, onUserChange }: { user: User; onSignOut: () => void; onUserChange: (user: User) => void }) {
  const call = useVoiceSession();
  const { state } = call;
  const insets = useSafeAreaInsets();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [privateDraft, setPrivateDraft] = useState(false);
  const [mode, setMode] = useState<'call' | 'text' | 'settings'>('call');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [captions, setCaptions] = useState(true);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [error, setError] = useState('');
  const [available, setAvailable] = useState<boolean | null>(null);
  const [starting, setStarting] = useState(false);
  const flight = useRef(false);
  const live = useRef(true);
  const drawerRef = useRef<View>(null);
  const opacity = useRef(new Animated.Value(0.2)).current;
  const reduced = useRef(false);
  const active = ['connecting', 'listening', 'thinking', 'speaking', 'reconnecting'].includes(state.phase);
  const isPrivate = conversations.find(c => c.id === activeId)?.private ?? privateDraft;
  useModalAccessibility(drawerOpen, drawerRef, () => setDrawerOpen(false));
  async function refresh() {
    setListLoading(true); setListError('');
    try { const items = await getConversations(); if (live.current) setConversations(items); }
    catch (err) { if (live.current) setListError(err instanceof Error ? err.message : 'Couldn’t load conversations.'); }
    finally { if (live.current) setListLoading(false); }
  }
  useEffect(() => {
    live.current = true; void refresh();
    void getCallStatus().then(value => { if (live.current) setAvailable(value.available); }).catch(() => {});
    void AccessibilityInfo.isReduceMotionEnabled().then(value => { reduced.current = value; });
    const motion = AccessibilityInfo.addEventListener('reduceMotionChanged', value => { reduced.current = value; });
    return () => { live.current = false; motion.remove(); };
  }, []);
  useEffect(() => {
    const animation = Animated.timing(opacity, { toValue: state.lit ? 1 : 0.2, duration: reduced.current ? 0 : 550, useNativeDriver: Platform.OS !== "web" });
    animation.start(); return () => animation.stop();
  }, [state.lit]);
  useEffect(() => {
    if (state.phase === 'ended' || state.phase === 'error') void refresh();
  }, [state.phase]);
  useEffect(() => {
    const back = BackHandler.addEventListener('hardwareBackPress', () => {
      if (drawerOpen) { setDrawerOpen(false); return true; }
      if (mode !== 'call') { setMode('call'); return true; }
      if (active) { void call.end(); return true; }
      return false;
    }); return () => back.remove();
  }, [drawerOpen, mode, active]);
  async function start() {
    if (flight.current || active) return;
    flight.current = true; setStarting(true); setError('');
    try {
      // Re-check configuration on each attempt so adding keys needs no app restart.
      const status = await getCallStatus(); setAvailable(status.available);
      if (!status.available) throw new Error('Live calls aren’t ready yet. You can still type to Parth.');
      let id = activeId;
      if (!id) {
        const conversation = await createConversation(privateDraft); id = conversation.id;
        if (!live.current) return;
        setActiveId(id); setConversations(items => [conversation, ...items]);
      }
      await call.start(id, randomUUID());
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : 'Couldn’t start the call.'); }
    finally { flight.current = false; if (live.current) setStarting(false); }
  }
  async function showMode(next: 'text' | 'settings') {
    await call.end(); setDrawerOpen(false); setMode(next);
  }
  async function remove(id: string) {
    if (id === activeId) await call.end();
    await deleteConversation(id);
    setConversations(items => items.filter(c => c.id !== id));
    if (id === activeId) { setActiveId(null); setPrivateDraft(false); }
  }
  if (mode === 'text') return <ChatHome user={user} onSignOut={onSignOut} onUserChange={onUserChange}
    initialConversationId={activeId} initialPrivate={privateDraft} onConversationChange={setActiveId}
    onBackToCall={() => { setMode('call'); void refresh(); }} />;
  if (mode === 'settings') return <MemorySettings user={user} onSignOut={onSignOut} onUserChange={onUserChange} onBack={() => setMode('call')} />;
  return <View style={styles.root}>
    <StatusBar barStyle="light-content" backgroundColor="#100c09" />
    <View style={styles.scene} pointerEvents="none" accessible={false}>
      <Animated.Image source={require('../../assets/temple.png')} resizeMode="cover" style={[styles.image, { opacity }]} />
      <View style={styles.shade} />
    </View>
    <View style={styles.content} aria-hidden={drawerOpen} accessibilityElementsHidden={drawerOpen} importantForAccessibility={drawerOpen ? 'no-hide-descendants' : 'auto'}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Open conversations and memory" onPress={() => setDrawerOpen(true)} style={styles.iconButton}><Icon name="menu" color="#fff6e7" /></Pressable>
        <View style={styles.name}><Text style={styles.title}>Parth <Text style={styles.ai}>· AI</Text></Text><Text style={styles.subtitle}>A conversation, at your pace</Text></View>
        <Pressable accessibilityRole="button" accessibilityLabel={captions ? 'Hide captions' : 'Show captions'} accessibilityState={{ selected: captions }} onPress={() => setCaptions(value => !value)} style={styles.iconButton}><Text style={[styles.cc, !captions && { opacity: 0.55 }]}>CC</Text></Pressable>
      </View>
      <View style={styles.space} />
      <View style={styles.dock}>
        {state.caption && captions && active ? <View style={styles.caption}><Text style={styles.captionText} numberOfLines={5}>{state.caption}</Text></View> : null}
        <View style={styles.status} accessibilityLiveRegion="polite">
          {active && ['connecting', 'thinking', 'reconnecting'].includes(state.phase) ? <ActivityIndicator color="#eac77d" size="small" /> : <View style={[styles.dot, { backgroundColor: state.lit ? '#eac77d' : '#968878' }]} />}
          <Text style={styles.statusText}>{state.muted && active ? 'Your microphone is off' : phaseLabel[state.phase]}</Text>
        </View>
        {error || state.error ? <Text style={styles.error} accessibilityRole="alert">{error || state.error}</Text> : null}
        {active ? <View style={styles.controls}>
          <Pressable accessibilityRole="button" accessibilityLabel={state.muted ? 'Unmute microphone' : 'Mute microphone'} disabled={state.phase === 'connecting'} onPress={() => void call.mute()} style={styles.secondary}><Icon name={state.muted ? 'mic-off' : 'mic'} color="#fff6e7" /><Text style={styles.secondaryText}>{state.muted ? 'Unmute' : 'Mute'}</Text></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="End call" onPress={() => void call.end()} style={styles.end}><Icon name="phone" color="#fff6e7" /><Text style={styles.secondaryText}>End</Text></Pressable>
        </View> : <View style={styles.controls}>
          <Pressable accessibilityRole="button" accessibilityLabel="Baat karein, start a live conversation" accessibilityState={{ busy: starting, disabled: starting }} disabled={starting} onPress={() => void start()} style={({ pressed }) => [styles.start, pressed && styles.pressed, starting && styles.disabled]}>
            {starting ? <ActivityIndicator color="#271b0c" /> : <Icon name="mic" color="#271b0c" size={24} />}<Text style={styles.startText}>{starting ? 'Connecting…' : 'Baat karein'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Type to Parth" disabled={starting} onPress={() => void showMode('text')} style={styles.type}><Icon name="keyboard" color="#fff6e7" size={21} /><Text style={styles.typeText}>TYPE</Text></Pressable>
        </View>}
        <Text style={styles.footnote}>{isPrivate || !user.memory_enabled ? 'Memory off · This conversation stays in your history' : available === false ? 'Live calls coming soon · Type is ready' : 'Your space to talk, reflect, and return'}</Text>
      </View>
    </View>
    <Modal visible={drawerOpen} transparent animationType="fade" onRequestClose={() => setDrawerOpen(false)}>
      <View style={styles.modal}><View ref={drawerRef} accessibilityViewIsModal style={[styles.drawer, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <ConversationDrawer conversations={conversations} activeId={activeId} email={user.email} loading={listLoading} error={listError} onRefresh={() => void refresh()} onClose={() => setDrawerOpen(false)}
          onSelect={id => { void (async () => { await call.end(); setActiveId(id); setDrawerOpen(false); setMode('text'); })(); }}
          onCreate={isPrivate => { void (async () => { await call.end(); setActiveId(null); setPrivateDraft(!!isPrivate); setDrawerOpen(false); })(); }}
          onDelete={remove} onSettings={() => void showMode('settings')}
          onSignOut={() => { void (async () => { await call.end(); onSignOut(); })(); }} />
      </View><Pressable accessibilityRole="button" accessibilityLabel="Close drawer" style={styles.scrim} onPress={() => setDrawerOpen(false)} /></View>
    </Modal>
  </View>;
}
const styles = StyleSheet.create({
  root: { flex: 1, width: '100%', maxWidth: 700, alignSelf: 'center', backgroundColor: '#100c09' }, scene: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, overflow: 'hidden' },
  // Crop the supplied mock's baked-in UI; keep its single portrait and temple.
  image: { position: 'absolute', width: '150%', height: '165%', left: '-25%', top: '-19%' },
  shade: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(16,12,9,0.12)' },
  content: { flex: 1, width: '100%', maxWidth: 700, alignSelf: 'center' },
  header: { flexDirection: 'row', padding: 14, alignItems: 'center', gap: 10, backgroundColor: 'rgba(16,12,9,0.9)' },
  iconButton: { width: 48, height: 48, justifyContent: 'center', alignItems: 'center' }, name: { flex: 1 },
  title: { color: '#fff6e7', fontSize: 25, fontWeight: '600' }, ai: { color: '#eac77d', fontSize: 13, fontWeight: '500' },
  subtitle: { color: '#dfcdb4', fontSize: 12, marginTop: 3 }, cc: { color: '#fff6e7', fontSize: 14, borderWidth: 1, borderColor: '#d6bea0', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 2 },
  space: { flex: 1, minHeight: 100 }, dock: { padding: 20, paddingTop: 22, backgroundColor: 'rgba(16,12,9,0.94)', gap: 14 },
  caption: { paddingBottom: 6 }, captionText: { color: '#fff6e7', fontSize: 17, lineHeight: 26 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 9 }, dot: { width: 6, height: 6, borderRadius: 3 }, statusText: { color: '#dfcdb4', fontSize: 14, lineHeight: 21 },
  controls: { flexDirection: 'row', gap: 10, alignItems: 'stretch' }, start: { flex: 4, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 11, minHeight: 64, borderRadius: 14, backgroundColor: '#eac77d' },
  startText: { color: '#271b0c', fontSize: 18, fontWeight: '600' }, type: { flex: 1, minWidth: 58, minHeight: 64, borderRadius: 14, borderWidth: 1, borderColor: '#806e58', alignItems: 'center', justifyContent: 'center', gap: 5 },
  typeText: { color: '#fff6e7', fontSize: 10, fontWeight: '600' }, secondary: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, minHeight: 60, borderRadius: 14, backgroundColor: '#30261c' },
  end: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, minHeight: 60, borderRadius: 14, backgroundColor: '#703c2e' }, secondaryText: { color: '#fff6e7', fontSize: 16, fontWeight: '500' },
  footnote: { color: '#c6b8a4', fontSize: 11, lineHeight: 17, textAlign: 'center' }, error: { color: '#ffd5c2', fontSize: 14, lineHeight: 21 },
  pressed: { opacity: 0.82 }, disabled: { opacity: 0.6 }, modal: { flex: 1, flexDirection: 'row', backgroundColor: 'rgba(0,0,0,0.6)' }, drawer: { width: '88%', maxWidth: 360, backgroundColor: '#fff' }, scrim: { flex: 1 },
});
