import { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo, ActivityIndicator, AppState, BackHandler, Keyboard, KeyboardAvoidingView,
  Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, useWindowDimensions,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { randomUUID } from "expo-crypto";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { removeVoiceFile, voiceError } from "../voice";
import { ApiError, createConversation, deleteConversation, discardTurn, getConversations, getMessages, getVoiceStatus, sendTurn, transcribeVoice } from "../api";
import { ConversationDrawer } from "../components/ConversationDrawer";
import { Icon, SaarthiMark } from "../components/Icons";
import { useModalAccessibility } from "../components/useModalAccessibility";
import { ChatMessage } from "../components/ChatMessage";
import { MemorySettings } from "./MemorySettings";
import { colors, fonts, radii } from "../theme";
import type { Conversation, Message, User } from "../types";

const suggestions = [
  { label: "Work & purpose", prompt: "I've been feeling stuck at work. Can we talk about it?", icon: "leaf" as const },
  { label: "Relationships", prompt: "Something in a relationship has been weighing on me.", icon: "book" as const },
  { label: "A restless mind", prompt: "My mind keeps going in circles, and I want to understand why.", icon: "down" as const },
];
export function ChatHome({ user, onSignOut, onUserChange }: { user: User; onSignOut: () => void; onUserChange: (user: User) => void }) {
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recording = useAudioRecorderState(recorder);
  const scrollRef = useRef<ScrollView>(null);
  const drawerRef = useRef<View>(null);
  const inputRef = useRef<TextInput>(null);
  const live = useRef(true);
  const active = useRef<string | null>(null);
  const flight = useRef(false);
  const recordFlight = useRef(false);
  const pendingVoice = useRef<string | null>(null);
  const draftText = useRef("");
  const selection = useRef(0);
  const nearBottom = useRef(true);
  const cache = useRef(new Map<string, Message[]>());
  const drafts = useRef(new Map<string, string>());
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [privateDraft, setPrivateDraft] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [busy, setBusy] = useState(false);
  const [replyConversation, setReplyConversation] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [startingRecording, setStartingRecording] = useState(false);
  const [voiceFailure, setVoiceFailure] = useState("");
  draftText.current = text;
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [showLatest, setShowLatest] = useState(false);
  useModalAccessibility(drawerOpen, drawerRef, () => setDrawerOpen(false));
  const activeConversation = conversations.find(item => item.id === activeId);
  const isPrivate = activeConversation?.private ?? privateDraft;
  const waiting = messages.some(m => m.role === "user" && m.status === "processing");

  async function refreshList() {
    setListError("");
    try { const list = await getConversations(); if (live.current) setConversations(list); }
    catch (err) { if (live.current) setListError(err instanceof Error ? err.message : "Couldn't load conversations."); }
    finally { if (live.current) setListLoading(false); }
  }
  useEffect(() => {
    live.current = true;
    void refreshList();
    void getVoiceStatus().then(s => { if (live.current) setVoiceAvailable(s.available); }).catch(() => {});
    void AccessibilityInfo.isReduceMotionEnabled().then(setReducedMotion);
    const motion = AccessibilityInfo.addEventListener("reduceMotionChanged", setReducedMotion);
    const show = Keyboard.addListener("keyboardDidShow", () => { setKeyboardOpen(true); if (nearBottom.current) scrollRef.current?.scrollToEnd({ animated: false }); });
    const hide = Keyboard.addListener("keyboardDidHide", () => setKeyboardOpen(false));
    return () => { live.current = false; removeVoiceFile(pendingVoice.current); pendingVoice.current = null; motion.remove(); show.remove(); hide.remove(); };
  }, []);
  useEffect(() => {
    const listener = BackHandler.addEventListener("hardwareBackPress", () => {
      if (settingsOpen) { setSettingsOpen(false); return true; }
      if (drawerOpen) { setDrawerOpen(false); return true; }
      return false;
    });
    return () => listener.remove();
  }, [settingsOpen, drawerOpen]);
  function putMessages(id: string, next: Message[] | ((items: Message[]) => Message[])) {
    const value = typeof next === "function" ? next(cache.current.get(id) ?? []) : next;
    cache.current.set(id, value);
    if (live.current && active.current === id) setMessages(value);
  }
  async function syncMessages(id: string) {
    const items = await getMessages(id);
    const known = new Set(items.map(m => m.id));
    // Keep messages that never reached the API so offline failures remain retryable.
    const unsent = (cache.current.get(id) ?? []).filter(m => m.role === "user" && (m.status === "failed" || (flight.current && m.status === "processing")) && !known.has(m.id));
    putMessages(id, [...items, ...unsent]);
    return items;
  }
  useEffect(() => {
    if (!activeId) return;
    const id = activeId;
    let polling = false;
    const poll = async () => {
      if (polling) return; polling = true;
      try { await syncMessages(id); } catch {} finally { polling = false; }
    };
    const timer = waiting ? setInterval(() => void poll(), 4000) : null;
    const appState = AppState.addEventListener("change", state => { if (state === "active") { void poll(); void refreshList(); } });
    return () => { if (timer) clearInterval(timer); appState.remove(); };
  }, [activeId, waiting]);
  function saveDraft() { drafts.current.set(active.current ?? "new", text); }
  function canNavigate() {
    if (recorder.isRecording || recordFlight.current || pendingVoice.current) { setNotice("Finish, retry, or discard your voice note before changing screens."); return false; }
    return true;
  }
  function openSettings() {
    if (!canNavigate()) return;
    setSettingsOpen(true); setDrawerOpen(false); Keyboard.dismiss();
  }
  function newConversation(isPrivate = false) {
    if (!canNavigate()) return;
    saveDraft(); selection.current++; active.current = null; setActiveId(null);
    setMessages([]); setText(""); drafts.current.delete("new"); setPrivateDraft(isPrivate);
    setSettingsOpen(false); setDrawerOpen(false); setNotice(""); setHistoryError(""); setLoading(false);
    nearBottom.current = true; setShowLatest(false); Keyboard.dismiss();
  }
  async function chooseConversation(id: string) {
    if (!canNavigate()) return;
    saveDraft(); const version = ++selection.current; active.current = id; setActiveId(id);
    setSettingsOpen(false); setDrawerOpen(false); setNotice(""); setHistoryError("");
    setText(drafts.current.get(id) ?? ""); setMessages(cache.current.get(id) ?? []);
    setLoading(true); nearBottom.current = true; setShowLatest(false); Keyboard.dismiss();
    try { await syncMessages(id); }
    catch (err) { if (version === selection.current) setHistoryError(err instanceof Error ? err.message : "Couldn't load messages."); }
    finally { if (live.current && version === selection.current) setLoading(false); }
  }
  async function removeConversation(id: string) {
    try {
      await deleteConversation(id); cache.current.delete(id); drafts.current.delete(id);
      setConversations(items => items.filter(c => c.id !== id));
      if (active.current === id) newConversation();
    } catch (err) { setListError(err instanceof Error ? err.message : "Couldn't delete this conversation."); throw err; }
  }
  async function sendMessage(raw: string, retryId?: string) {
    const value = raw.trim();
    if (!value || flight.current || waiting || recordFlight.current || pendingVoice.current || recorder.isRecording || historyError) return;
    flight.current = true; setBusy(true); setNotice("");
    const version = selection.current;
    let id = active.current;
    const clientId = retryId ?? randomUUID();
    let queued = false;
    try {
      if (!id) {
        const created = await createConversation(privateDraft); id = created.id;
        setConversations(items => [created, ...items]);
        if (selection.current !== version) throw new Error("Your chat is ready in recent conversations. Send your message there.");
        active.current = id; setActiveId(id); cache.current.set(id, []);
      }
      setReplyConversation(id);
      const optimistic: Message = { id: clientId, turn_id: clientId, role: "user", text: value, status: "processing" };
      putMessages(id, items => retryId ? items.map(m => m.id === clientId ? optimistic : m) : [...items, optimistic]);
      queued = true; if (!retryId) { setText(""); drafts.current.delete(id); drafts.current.delete("new"); }
      nearBottom.current = true; setShowLatest(false);
      const reply = await sendTurn(id, value, clientId);
      putMessages(id, items => [...items.filter(m => m.id !== reply.id).map(m => m.id === clientId ? { ...m, status: "completed" as const, error: null } : m), reply]);
      void refreshList();
    } catch (err) {
      if (!live.current) return;
      const message = err instanceof Error ? err.message : "Couldn't finish the reply.";
      if (id && queued) {
        putMessages(id, items => items.map(m => m.id === clientId ? { ...m, status: "failed", error: message } : m));
        // A lost response is not proof of failure. Reconcile with the saved state.
        try { await syncMessages(id); } catch {}
        void refreshList();
      } else setNotice(message);
    } finally { flight.current = false; if (live.current) { setBusy(false); setReplyConversation(null); } }
  }
  async function discardMessage(message: Message) {
    const id = active.current; if (!id) return;
    try { await discardTurn(id, message.turn_id ?? message.id); }
    catch (err) { if (!(err instanceof ApiError && err.status === 404)) { setNotice(err instanceof Error ? err.message : "Couldn't remove this message."); return; } }
    putMessages(id, items => items.filter(m => m.id !== message.id));
  }
  async function resetAudioMode() {
    try { await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }); }
    catch { if (__DEV__) console.info("[voice] Audio mode reset failed."); }
  }
  function discardVoiceNote() {
    if (recordFlight.current) return;
    removeVoiceFile(pendingVoice.current); pendingVoice.current = null;
    setVoiceFailure(""); setNotice("");
  }
  async function uploadVoiceNote(uri: string) {
    setTranscribing(true); setVoiceFailure("");
    try {
      const transcript = (await transcribeVoice(uri)).trim();
      if (!live.current) return;
      if (!transcript) throw new ApiError("No words were heard. Discard this note and record again, closer to the microphone.", 0);
      const next = draftText.current ? `${draftText.current}\n${transcript}` : transcript;
      if (next.length > 6000) throw new ApiError("Your draft is too long. Shorten the text, then retry this voice note.", 0);
      draftText.current = next; setText(next);
      removeVoiceFile(uri); pendingVoice.current = null;
      setNotice("Review your words, then send when you're ready.");
    } catch (error) {
      if (live.current) setVoiceFailure(voiceError(error, "Couldn't transcribe this note. Your recording is kept on this device; retry or discard it."));
    } finally { if (live.current) setTranscribing(false); }
  }
  async function retryVoiceNote() {
    const uri = pendingVoice.current;
    if (!uri || recordFlight.current) return;
    recordFlight.current = true;
    try { await uploadVoiceNote(uri); }
    finally { recordFlight.current = false; }
  }
  async function cancelRecording() {
    if (recordFlight.current) return;
    recordFlight.current = true;
    try {
      if (recorder.isRecording) await recorder.stop();
      removeVoiceFile(recorder.uri);
      if (live.current) setNotice("");
    } catch (error) {
      if (live.current) setNotice(voiceError(error, "Couldn't stop the microphone. Try Cancel again."));
    } finally { await resetAudioMode(); recordFlight.current = false; }
  }
  async function toggleRecording() {
    if (recordFlight.current || pendingVoice.current) return;
    recordFlight.current = true;
    try {
      if (recorder.isRecording) {
        setTranscribing(true);
        await recorder.stop();
        const uri = recorder.uri;
        await resetAudioMode();
        if (!live.current) { removeVoiceFile(uri); return; }
        if (!uri) throw new ApiError("The recording didn't finish. Please record it again.", 0);
        pendingVoice.current = uri;
        await uploadVoiceNote(uri);
      } else {
        if (busy || waiting || loading || historyError) return;
        setStartingRecording(true); setNotice("");
        const permission = await AudioModule.requestRecordingPermissionsAsync();
        if (!live.current) return;
        if (!permission.granted) throw new ApiError("Allow microphone access in your phone's settings to record a voice note.", 0);
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
        await recorder.prepareToRecordAsync();
        if (!live.current) { await resetAudioMode(); return; }
        recorder.record();
      }
    } catch (error) {
      await resetAudioMode();
      if (live.current) setNotice(voiceError(error, "Couldn't use the microphone. Try recording again."));
    } finally {
      recordFlight.current = false;
      if (live.current) { setStartingRecording(false); setTranscribing(false); }
    }
  }
  useEffect(() => {
    if (!recording.isRecording) return;
    const timer = setTimeout(() => void toggleRecording(), Math.max(0, 60000 - recording.durationMillis));
    return () => clearTimeout(timer);
  }, [recording.isRecording]);
  const blocked = busy || waiting || transcribing || startingRecording || !!voiceFailure || recording.isRecording || loading || !!historyError;
  const drawer = <ConversationDrawer conversations={conversations} activeId={activeId} email={user.email} onSelect={id => void chooseConversation(id)} onCreate={newConversation} onSettings={openSettings} onSignOut={onSignOut} onDelete={removeConversation} onClose={wide ? undefined : () => setDrawerOpen(false)} loading={listLoading} error={listError} onRefresh={() => { setListLoading(true); void refreshList(); }} />;
  return <View style={styles.root}>
    {wide ? <View style={styles.wideSidebar}>{drawer}</View> : null}
    <View style={styles.main} aria-hidden={drawerOpen} accessibilityElementsHidden={drawerOpen} importantForAccessibility={drawerOpen ? "no-hide-descendants" : "auto"}>
      {settingsOpen ? <MemorySettings user={user} onBack={() => setSettingsOpen(false)} onSignOut={onSignOut} onUserChange={onUserChange} /> : <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "ios" ? "padding" : Platform.OS === "android" ? "height" : undefined} keyboardVerticalOffset={insets.top}>
        <View style={styles.header}>
          {!wide ? <Pressable accessibilityRole="button" accessibilityLabel="Open conversations and account" onPress={() => { Keyboard.dismiss(); setDrawerOpen(true); }} style={styles.headerIcon}><Icon name="menu" color={colors.body} /></Pressable> : null}
          <View style={styles.headerCopy}><Text style={styles.headerTitle}>Saarthi</Text><View style={styles.headerSubtitle}><View style={styles.statusDot} /><Text style={styles.headerSub}>{isPrivate ? "Memory off for this chat" : !user.memory_enabled ? "Memory is turned off" : "Rooted in the Bhagavad Gita"}</Text></View></View>
          <Pressable accessibilityRole="button" accessibilityLabel="Start new conversation" onPress={() => newConversation()} style={styles.headerIcon}><Icon name="plus" color={colors.primary} /></Pressable>
        </View>
        {notice ? <View style={styles.notice}><Text accessibilityRole="alert" style={styles.noticeText}>{notice}</Text><Pressable accessibilityRole="button" accessibilityLabel="Dismiss notification" onPress={() => setNotice("")} style={styles.headerIcon}><Icon name="close" size={18} /></Pressable></View> : null}
        {historyError ? <View style={styles.historyError}><Text accessibilityRole="alert" style={styles.errorText}>{historyError}</Text><Pressable accessibilityRole="button" onPress={() => activeId && void chooseConversation(activeId)} style={styles.retry}><Icon name="retry" color={colors.primary} size={18} /><Text style={styles.retryLabel}>Load messages again</Text></Pressable></View> : null}
        {loading ? <View style={styles.loadingArea}><View style={styles.skeletonLine} /><View style={[styles.skeletonLine, { width: "48%" }]} /><View style={[styles.skeletonLine, { width: "65%", marginTop: 28 }]} /></View> : !messages.length ? <ScrollView style={styles.fill} contentContainerStyle={styles.welcomeScroll} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <View style={styles.welcome}>
            <SaarthiMark size={80} />
            <Text style={styles.sanskritWelcome}>मन की बात, गीता के साथ</Text>
            <Text accessibilityRole="header" style={styles.welcomeTitle}>A quieter mind.{"\n"}A clearer way.</Text>
            <Text style={styles.welcomeText}>Some things are easier to untangle when you don’t carry them alone. Start wherever you are.</Text>
            <View style={styles.suggestions}>{suggestions.map(item => <Pressable key={item.label} accessibilityRole="button" onPress={() => { setText(item.prompt); inputRef.current?.focus(); }} style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}><Icon name={item.icon} size={18} color={colors.accent} /><Text style={styles.suggestionText}>{item.label}</Text><Text style={styles.suggestionArrow}>↗</Text></Pressable>)}</View>
            <View style={styles.memoryNote}><Icon name="lock" size={14} color={colors.quiet} /><Text style={styles.privateNote}>{isPrivate || !user.memory_enabled ? "This chat won’t read or save memories." : "A private space, just for you."}</Text></View>
          </View>
        </ScrollView> : <View style={styles.fill}>
          <ScrollView ref={scrollRef} style={styles.fill} contentContainerStyle={styles.messageList} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" scrollEventThrottle={100} onScroll={event => {
            const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
            nearBottom.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 100;
            setShowLatest(!nearBottom.current);
          }} onContentSizeChange={() => { if (nearBottom.current) scrollRef.current?.scrollToEnd({ animated: !reducedMotion }); }}>
            {messages.map(message => <ChatMessage key={message.id} message={message} voiceAvailable={voiceAvailable && !recording.isRecording && !transcribing && !startingRecording} language={user.language} retryDisabled={blocked} onRetry={() => void sendMessage(message.text, message.turn_id ?? message.id)} onDiscard={() => void discardMessage(message)} />)}
            {waiting ? <View style={styles.thinking} accessibilityLiveRegion="polite"><SaarthiMark size={28} /><ActivityIndicator size="small" color={colors.primary} /><Text style={styles.thinkingLabel}>Saarthi is reflecting…</Text></View> : null}
          </ScrollView>
          {showLatest ? <Pressable accessibilityRole="button" accessibilityLabel="Scroll to latest message" onPress={() => { nearBottom.current = true; scrollRef.current?.scrollToEnd({ animated: !reducedMotion }); setShowLatest(false); }} style={styles.latest}><Icon name="down" size={18} color={colors.primary} /><Text style={styles.retryLabel}>Latest</Text></Pressable> : null}
        </View>}
        <View style={styles.composerDock}>
          {busy && replyConversation && replyConversation !== activeId ? <View style={styles.transcribing}><ActivityIndicator size="small" color={colors.primary} /><Text style={[styles.thinkingLabel, { flex: 1 }]}>Finishing a reply in another chat.</Text><Pressable accessibilityRole="button" onPress={() => void chooseConversation(replyConversation)} style={styles.recordAction}><Text style={styles.retryLabel}>View</Text></Pressable></View> : null}
          {recording.isRecording ? <View style={styles.recordingBar}><View style={styles.recordDot} /><Text style={styles.recordingText}>Recording · {Math.floor(recording.durationMillis / 1000)}s / 60s</Text><Pressable accessibilityRole="button" disabled={transcribing} onPress={() => void cancelRecording()} style={styles.recordAction}><Text style={styles.cancelLabel}>Cancel</Text></Pressable><Pressable accessibilityRole="button" disabled={transcribing} onPress={() => void toggleRecording()} style={styles.recordAction}><Text style={styles.retryLabel}>Finish</Text></Pressable></View> : null}
          {voiceFailure ? <View style={styles.voiceFailure}>
            <Text accessibilityRole="alert" style={styles.errorText}>{voiceFailure}</Text>
            <Text style={styles.privateNote}>Your voice note stays here until you retry or discard it.</Text>
            <View style={styles.voiceActions}>
              <Pressable accessibilityRole="button" accessibilityLabel="Retry transcribing voice note" disabled={transcribing} onPress={() => void retryVoiceNote()} style={styles.recordAction}><Text style={styles.retryLabel}>Retry</Text></Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Discard voice note" disabled={transcribing} onPress={discardVoiceNote} style={styles.recordAction}><Text style={styles.cancelLabel}>Discard</Text></Pressable>
            </View>
          </View> : null}
          {startingRecording ? <View style={styles.transcribing}><ActivityIndicator size="small" color={colors.primary} /><Text style={styles.thinkingLabel}>Opening the microphone…</Text></View> : null}
          {transcribing ? <View style={styles.transcribing}><ActivityIndicator size="small" color={colors.primary} /><Text style={styles.thinkingLabel}>Turning your voice into words…</Text></View> : null}
          <View style={styles.composer}>
            <TextInput ref={inputRef} accessibilityLabel="Message Saarthi" value={text} onChangeText={setText} placeholder="What's on your mind?" placeholderTextColor={colors.quiet} multiline maxLength={6000} editable={!transcribing && !startingRecording && !recording.isRecording} style={styles.input} textAlignVertical="top" onFocus={() => { nearBottom.current = true; }} onKeyPress={event => {
              if (Platform.OS === "web" && event.nativeEvent.key === "Enter" && !(event.nativeEvent as unknown as { shiftKey?: boolean }).shiftKey) { event.preventDefault(); void sendMessage(text); }
            }} />
            {voiceAvailable ? <Pressable accessibilityRole="button" accessibilityLabel={recording.isRecording ? "Finish recording" : "Record a voice note"} accessibilityState={{ disabled: busy || waiting || transcribing || startingRecording || !!voiceFailure || loading || !!historyError }} disabled={busy || waiting || transcribing || startingRecording || !!voiceFailure || loading || !!historyError} onPress={() => void toggleRecording()} style={styles.composerIcon}><Icon name={recording.isRecording ? "stop" : "mic"} size={21} color={recording.isRecording ? colors.danger : colors.body} /></Pressable> : null}
            <Pressable accessibilityRole="button" accessibilityLabel="Send message" accessibilityState={{ disabled: !text.trim() || blocked, busy }} disabled={!text.trim() || blocked} onPress={() => void sendMessage(text)} style={({ pressed }) => [styles.sendButton, (!text.trim() || blocked) && styles.sendDisabled, pressed && styles.pressed]}><Icon name="send" size={20} color={!text.trim() || blocked ? colors.quiet : colors.white} /></Pressable>
          </View>
          {text.length > 5500 ? <Text style={styles.limit}>{6000 - text.length} characters left</Text> : null}
          {!keyboardOpen ? <Text style={styles.composerFootnote}>Guidance for reflection. Your path is yours to choose.</Text> : null}
        </View>
      </KeyboardAvoidingView>}
    </View>
    {!wide ? <Modal visible={drawerOpen} transparent animationType={reducedMotion ? "none" : "fade"} onRequestClose={() => setDrawerOpen(false)}><View style={styles.modalRow}><SafeAreaView ref={drawerRef} accessibilityViewIsModal role="dialog" aria-modal={true} accessibilityLabel="Conversations and account" style={styles.mobileSidebar}>{drawer}</SafeAreaView><Pressable accessibilityRole="button" accessibilityLabel="Close conversations" onPress={() => setDrawerOpen(false)} style={styles.scrim} /></View></Modal> : null}
  </View>;
}
const styles = StyleSheet.create({
  root: { flex: 1, flexDirection: "row", backgroundColor: colors.background }, fill: { flex: 1 }, main: { flex: 1, minWidth: 0 },
  wideSidebar: { width: 300, borderRightWidth: 1, borderRightColor: colors.border },
  header: { minHeight: 74, flexDirection: "row", alignItems: "center", paddingHorizontal: 12, gap: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerIcon: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: radii.control }, headerCopy: { flex: 1, minWidth: 0 },
  headerTitle: { color: colors.primary, fontFamily: fonts.heading, fontSize: 25 }, headerSubtitle: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3 }, headerSub: { color: colors.quiet, fontSize: 11, flexShrink: 1 }, statusDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.accent },
  notice: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.goldWash, marginHorizontal: 16, marginTop: 12, borderRadius: radii.control, paddingLeft: 12 }, noticeText: { flex: 1, color: colors.body, fontSize: 13, lineHeight: 20 },
  historyError: { padding: 20, gap: 8 }, errorText: { color: colors.danger, fontSize: 14, lineHeight: 21 }, retry: { minHeight: 48, flexDirection: "row", gap: 8, alignItems: "center" }, retryLabel: { color: colors.primary, fontSize: 14, fontWeight: "600" },
  loadingArea: { flex: 1, padding: 24, paddingTop: 40, gap: 12 }, skeletonLine: { width: "82%", height: 16, borderRadius: 6, backgroundColor: colors.surface },
  welcomeScroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 26, paddingVertical: 32 }, welcome: { width: "100%", maxWidth: 480, alignSelf: "center", alignItems: "center", gap: 20 },
  sanskritWelcome: { color: colors.accent, fontSize: 14, lineHeight: 23, marginTop: -6 }, welcomeTitle: { color: colors.ink, fontFamily: fonts.heading, fontSize: 36, lineHeight: 44, textAlign: "center" },
  welcomeText: { color: colors.body, fontSize: 15, lineHeight: 25, textAlign: "center", maxWidth: 360 },
  suggestions: { width: "100%", marginTop: 6, gap: 0 }, suggestion: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: colors.border }, suggestionText: { flex: 1, color: colors.body, fontSize: 14 }, suggestionArrow: { color: colors.quiet, fontSize: 18 },
  memoryNote: { flexDirection: "row", gap: 6, alignItems: "center", marginTop: 2 }, privateNote: { color: colors.quiet, fontSize: 12, lineHeight: 19 },
  messageList: { paddingTop: 28, paddingBottom: 12 }, thinking: { width: "100%", maxWidth: 760, alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 22, paddingBottom: 24 }, thinkingLabel: { color: colors.quiet, fontSize: 13, lineHeight: 20 },
  latest: { position: "absolute", bottom: 12, alignSelf: "center", flexDirection: "row", gap: 8, alignItems: "center", minHeight: 44, paddingHorizontal: 16, borderRadius: radii.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.white },
  composerDock: { backgroundColor: colors.white, paddingTop: 10, paddingHorizontal: 16, paddingBottom: 10 }, composer: { width: "100%", maxWidth: 720, alignSelf: "center", minHeight: 58, maxHeight: 170, flexDirection: "row", alignItems: "flex-end", gap: 2, borderWidth: 1, borderColor: colors.border, borderRadius: radii.panel, padding: 5, backgroundColor: colors.background },
  input: { fontFamily: fonts.body, flex: 1, minHeight: 46, maxHeight: 154, paddingHorizontal: 10, paddingTop: 12, paddingBottom: 10, fontSize: 16, lineHeight: 24, color: colors.ink }, composerIcon: { width: 44, height: 46, alignItems: "center", justifyContent: "center" }, sendButton: { width: 44, height: 46, alignItems: "center", justifyContent: "center", borderRadius: 11, backgroundColor: colors.primary }, sendDisabled: { backgroundColor: colors.surface }, pressed: { opacity: .75 },
  composerFootnote: { color: colors.quiet, fontSize: 11, lineHeight: 18, textAlign: "center", paddingTop: 8 }, limit: { textAlign: "right", color: colors.quiet, fontSize: 12, paddingTop: 5 },
  voiceFailure: { backgroundColor: colors.dangerWash, borderRadius: radii.control, padding: 12, gap: 6 }, voiceActions: { flexDirection: "row", gap: 8 },
  recordingBar: { width: "100%", maxWidth: 720, alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 4 }, recordDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.danger }, recordingText: { flex: 1, color: colors.body, fontSize: 12 }, recordAction: { minHeight: 44, justifyContent: "center", paddingHorizontal: 10 }, cancelLabel: { color: colors.quiet, fontSize: 14 }, transcribing: { flexDirection: "row", gap: 8, padding: 10, alignItems: "center" },
  modalRow: { flex: 1, flexDirection: "row", backgroundColor: "rgba(35,18,25,0.35)" }, mobileSidebar: { width: "88%", maxWidth: 340, backgroundColor: colors.surface }, scrim: { flex: 1 },
});
