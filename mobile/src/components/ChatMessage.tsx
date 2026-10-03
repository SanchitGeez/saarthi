import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { speakReply } from "../api";
import { playbackUri, removeVoiceFile, voiceError } from "../voice";
import { Icon, SaarthiMark } from "./Icons";
import { colors, radii } from "../theme";
import type { Message, User, Verse } from "../types";

type ActivePlayer = { player: AudioPlayer; uri: string; subscription: { remove: () => void } };
let stopPrevious: (() => void) | null = null;
function ListenButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [error, setError] = useState("");
  const active = useRef<ActivePlayer | null>(null);
  const live = useRef(true);
  const flight = useRef(false);
  function release() {
    const current = active.current;
    active.current = null;
    if (current) {
      try { current.subscription.remove(); current.player.release(); }
      catch { if (__DEV__) console.info("[voice] Player cleanup failed."); }
      finally { removeVoiceFile(current.uri); }
    }
    if (stopPrevious === release) stopPrevious = null;
    if (live.current) setState("idle");
  }
  useEffect(() => { live.current = true; return () => { live.current = false; release(); }; }, []);
  async function play() {
    if (active.current) { release(); return; }
    if (flight.current) return;
    flight.current = true;
    stopPrevious?.(); setState("loading"); setError("");
    let uri: string | null = null;
    let player: AudioPlayer | null = null;
    try {
      const buffer = await speakReply(text);
      if (!live.current) return;
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      if (!live.current) return;
      uri = playbackUri(buffer);
      player = createAudioPlayer({ uri });
      const subscription = player.addListener("playbackStatusUpdate", status => {
        if (status.error) { if (live.current) setError("Playback stopped. Try listening again."); release(); }
        else if (status.didJustFinish) release();
      });
      stopPrevious?.(); active.current = { player, uri, subscription }; stopPrevious = release;
      setState("playing"); player.play();
    } catch (err) {
      if (!active.current) {
        try { player?.release(); } catch { if (__DEV__) console.info("[voice] Player cleanup failed."); }
        removeVoiceFile(uri);
      }
      release(); if (live.current) setError(voiceError(err, "Couldn't prepare this audio. Try listening again."));
    } finally { flight.current = false; }
  }
  return <View>
    <Pressable accessibilityRole="button" accessibilityLabel={state === "playing" ? "Stop listening" : "Listen to this reply"} accessibilityState={{ busy: state === "loading", disabled: state === "loading" }} disabled={state === "loading"} onPress={() => void play()} style={styles.listen}>
      {state === "loading" ? <ActivityIndicator size="small" color={colors.primary} /> : <Icon name={state === "playing" ? "stop" : "volume"} size={17} color={colors.primary} />}
      <Text style={styles.listenText}>{state === "loading" ? "Preparing audio…" : state === "playing" ? "Stop listening" : error ? "Try listening again" : "Listen"}</Text>
    </Pressable>
    {error ? <Text accessibilityRole="alert" style={styles.errorText}>{error}</Text> : null}
  </View>;
}

function VerseCard({ verse, language }: { verse: Verse; language: User["language"] }) {
  const [translation, setTranslation] = useState<"en" | "hi">(language === "hi" || language === "hinglish" ? "hi" : "en");
  const [error, setError] = useState("");
  return <View style={styles.verse}>
    <View style={styles.verseHeader}><Icon name="book" size={18} color={colors.accent} /><Text style={styles.verseTitle}>{verse.title}</Text></View>
    <Text selectable style={styles.sanskrit}>{verse.sanskrit}</Text>
    <View accessibilityRole="radiogroup" accessibilityLabel="Verse translation" style={styles.translationTabs}>
      {([['en', 'English'], ['hi', 'हिन्दी']] as const).map(([value, label]) => <Pressable key={value} accessibilityRole="radio" aria-checked={translation === value} accessibilityState={{ checked: translation === value }} onPress={() => setTranslation(value)} style={[styles.translationTab, translation === value && styles.translationActive]}><Text style={[styles.translationLabel, translation === value && styles.translationSelected]}>{label}</Text></Pressable>)}
    </View>
    <Text selectable style={styles.translation}>{translation === "hi" ? verse.hindi : verse.english}</Text>
    {verse.note ? <Text style={styles.verseNote}>{verse.note}</Text> : null}
    <View style={styles.sourceRow}><Text style={styles.verseNote}>A plain-language rendering</Text><Pressable accessibilityRole="link" accessibilityLabel={`Read source for ${verse.title}`} onPress={() => void Linking.openURL(verse.source_url).catch(() => setError("Couldn't open the source. Please try again."))} style={styles.source}><Text style={styles.sourceLabel}>View source ↗</Text></Pressable></View>
    {error ? <Text style={styles.errorText}>{error}</Text> : null}
  </View>;
}
function Prose({ text }: { text: string }) {
  return <>{text.trim().split(/\n\s*\n/).filter(Boolean).map((paragraph, index) => <Text key={index} selectable style={styles.text}>{paragraph.split(/(\*\*[^*]+\*\*)/g).map((part, i) => <Text key={i} style={part.startsWith("**") ? styles.bold : undefined}>{part.startsWith("**") ? part.slice(2, -2) : part}</Text>)}</Text>)}</>;
}
export function ChatMessage({ message, voiceAvailable, language, retryDisabled = false, onRetry, onDiscard }: {
  message: Message; voiceAvailable: boolean; language: User["language"];
  retryDisabled?: boolean; onRetry?: () => void; onDiscard?: () => void;
}) {
  const mine = message.role === "user";
  const parts = message.text.split(/(\[\[gita:[\d.]+\]\])/g);
  const spoken = message.text.replace(/\[\[gita:([\d.]+)\]\]/g, (_, ref) => {
    const verse = message.verses?.find(v => v.reference === ref);
    return verse ? `${verse.title}. ${language === "hi" || language === "hinglish" ? verse.hindi : verse.english}` : "";
  }).replace(/\*\*/g, "");
  return <View style={[styles.row, mine && styles.rowMine]}>
    <View style={[styles.body, mine && styles.bodyMine]}>
      {!mine ? <View style={styles.identity}><SaarthiMark size={26} /><Text style={styles.name}>Parth</Text></View> : null}
      {mine ? <View style={[styles.userBubble, message.status === "failed" && styles.failedBubble]}><Text selectable style={styles.userText}>{message.text}</Text></View> : <View style={styles.prose}>
        {parts.map((part, index) => {
          const reference = /^\[\[gita:([\d.]+)\]\]$/.exec(part)?.[1];
          const verse = message.verses?.find(v => v.reference === reference);
          return verse ? <VerseCard key={index} verse={verse} language={language} /> : reference ? null : <Prose key={index} text={part} />;
        })}
      </View>}
      {mine && message.status === "failed" ? <View style={styles.failure}>
        <Text accessibilityRole="alert" style={styles.errorText}>{message.error || "This message hasn't received a reply."}</Text>
        <View style={styles.failureActions}>
          <Pressable accessibilityRole="button" accessibilityLabel="Retry this message" accessibilityState={{ disabled: retryDisabled }} disabled={retryDisabled} onPress={onRetry} style={styles.retry}><Icon name="retry" size={16} color={colors.primary} /><Text style={styles.listenText}>Retry</Text></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Remove failed message" disabled={retryDisabled} onPress={onDiscard} style={styles.retry}><Text style={styles.removeLabel}>Remove</Text></Pressable>
        </View>
      </View> : mine && message.status === "processing" ? <Text style={styles.delivery}>Sent · awaiting a reply</Text> : null}
      {!mine && voiceAvailable ? <ListenButton text={spoken} /> : null}
    </View>
  </View>;
}
const styles = StyleSheet.create({
  row: { width: "100%", maxWidth: 760, alignSelf: "center", paddingHorizontal: 22, marginBottom: 28 },
  rowMine: { alignItems: "flex-end" }, body: { width: "100%", gap: 12 }, bodyMine: { width: "auto", maxWidth: "90%", alignItems: "flex-end" },
  identity: { flexDirection: "row", alignItems: "center", gap: 8 }, name: { color: colors.primary, fontSize: 13, fontWeight: "600" },
  prose: { gap: 16 }, text: { color: colors.ink, fontSize: 17, lineHeight: 28 }, bold: { fontWeight: "600" },
  userBubble: { paddingVertical: 13, paddingHorizontal: 17, borderRadius: radii.panel, borderBottomRightRadius: 4, backgroundColor: colors.surface },
  failedBubble: { backgroundColor: colors.dangerWash }, userText: { color: colors.ink, fontSize: 16, lineHeight: 25 },
  listen: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 7, minHeight: 44, paddingHorizontal: 2 }, listenText: { color: colors.primary, fontSize: 13, fontWeight: "600" },
  failure: { maxWidth: "100%", gap: 0, alignItems: "flex-end" }, failureActions: { flexDirection: "row", gap: 16 },
  errorText: { color: colors.danger, fontSize: 13, lineHeight: 20 }, retry: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, paddingHorizontal: 4 }, removeLabel: { color: colors.quiet, fontSize: 13 },
  delivery: { color: colors.quiet, fontSize: 12, lineHeight: 18 },
  verse: { backgroundColor: colors.goldWash, borderRadius: radii.control, padding: 18, gap: 14, marginVertical: 2 },
  verseHeader: { flexDirection: "row", alignItems: "center", gap: 8 }, verseTitle: { color: colors.accent, fontSize: 13, fontWeight: "600" },
  sanskrit: { color: colors.primary, fontSize: 18, lineHeight: 32 }, translation: { fontSize: 15, lineHeight: 25, color: colors.ink },
  translationTabs: { flexDirection: "row", gap: 8 }, translationTab: { minHeight: 44, paddingHorizontal: 14, justifyContent: "center", borderRadius: 8 }, translationActive: { backgroundColor: colors.white },
  translationLabel: { color: colors.body, fontSize: 13 }, translationSelected: { color: colors.primary, fontWeight: "600" },
  verseNote: { color: colors.quiet, fontSize: 12, lineHeight: 19, flexShrink: 1 }, sourceRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 6 }, source: { minHeight: 44, justifyContent: "center" }, sourceLabel: { color: colors.primary, fontSize: 12, fontWeight: "600" },
});
