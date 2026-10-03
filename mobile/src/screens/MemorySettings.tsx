import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { deleteAccount, deleteMemory, getMemories, updateMemory, updatePreferences } from "../api";
import { Icon } from "../components/Icons";
import { ConfirmDialog } from "../components/ConfirmDialog";
import type { Memory, User } from "../types";
import { colors, fonts, radii } from "../theme";

const kindLabel: Record<string, string> = { context: "About you", preference: "Preference", pattern: "A pattern you shared", goal: "Long-term goal", concern: "Context", action: "Context" };
export function MemorySettings({ user, onBack, onSignOut, onUserChange }: { user: User; onBack: () => void; onSignOut: () => void; onUserChange: (user: User) => void }) {
  const insets = useSafeAreaInsets();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState<Memory | "account" | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  async function refresh() {
    setError(""); setLoading(true);
    try { setMemories((await getMemories()).filter(m => m.status !== "rejected")); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't load memories."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function preference(patch: { memory_enabled?: boolean; language?: User["language"] }) {
    if (preferenceBusy) return;
    setPreferenceBusy(true); setError(""); setNotice("");
    try { const updated = await updatePreferences(patch); onUserChange({ ...user, ...updated }); setNotice(patch.language ? "Reply language updated." : updated.memory_enabled ? "Memory is on." : "Memory is off. Saved details remain available to edit or delete."); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't update this setting."); }
    finally { setPreferenceBusy(false); }
  }
  async function save(item: Memory) {
    if (!draft.trim() || busyId) return;
    setBusyId(item.id); setError(""); setNotice("");
    try {
      const result = await updateMemory(item.id, { content: draft.trim() });
      setMemories(items => items.map(m => m.id === item.id ? { ...m, content: result.content, proposed_content: null, status: "confirmed" } : m));
      setEditingId(null); setNotice("Memory updated.");
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't update this memory."); }
    finally { setBusyId(null); }
  }
  async function confirmDelete() {
    if (!deleting || deletingBusy) return;
    setDeletingBusy(true); setError("");
    try {
      if (deleting === "account") { await deleteAccount(); onSignOut(); }
      else {
        await deleteMemory(deleting.id); setMemories(items => items.filter(m => m.id !== deleting.id));
        if (editingId === deleting.id) setEditingId(null);
        setNotice("Memory deleted. Saarthi won’t use it in future chats.");
      }
      setDeleting(null);
    } catch (err) { setDeleting(null); setError(err instanceof Error ? err.message : "Couldn't delete this. Please try again."); }
    finally { setDeletingBusy(false); }
  }
  const filtered = memories.filter(m => (m.proposed_content ?? m.content).toLocaleLowerCase().includes(query.toLocaleLowerCase().trim()));
  return <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === "ios" ? "padding" : Platform.OS === "android" ? "height" : undefined} keyboardVerticalOffset={insets.top}>
    <View style={styles.header}><Pressable accessibilityRole="button" accessibilityLabel="Back to chat" onPress={onBack} style={styles.iconButton}><Icon name="back" /></Pressable><Text accessibilityRole="header" style={styles.headerTitle}>Memory & settings</Text></View>
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
      <Text style={styles.sectionTitle}>A companion who remembers.</Text>
      <Text style={styles.body}>Saarthi automatically remembers useful, lasting details you share—your preferences, goals, and patterns you describe. Everyday feelings and each message don’t need a memory.</Text>
      <View style={styles.toggleRow}><View style={styles.toggleCopy}><Text style={styles.label}>Remember between conversations</Text><Text style={styles.helper}>You can edit or delete any detail below. Chats without memory never read or save these details.</Text></View><Switch accessibilityLabel="Remember between conversations" disabled={preferenceBusy} value={user.memory_enabled} onValueChange={value => void preference({ memory_enabled: value })} trackColor={{ false: colors.border, true: colors.primary }} thumbColor={colors.white} hitSlop={{ top: 12, bottom: 12, left: 10, right: 10 }} {...(Platform.OS === "web" ? { activeThumbColor: colors.white } : {})} /></View>
      <View style={styles.section}>
        <Text style={styles.label}>Reply language</Text><Text style={styles.helper}>Choose what feels most natural to you.</Text>
        <View accessibilityRole="radiogroup" accessibilityLabel="Reply language" style={styles.languageChoices}>{([['auto', 'Match my message'], ['en', 'English'], ['hi', 'हिन्दी'], ['hinglish', 'Hinglish']] as const).map(([value, label]) => <Pressable key={value} accessibilityRole="radio" aria-checked={user.language === value} aria-disabled={preferenceBusy} accessibilityState={{ checked: user.language === value, disabled: preferenceBusy }} disabled={preferenceBusy} onPress={() => void preference({ language: value })} style={[styles.languageOption, user.language === value && styles.languageSelected]}><Text style={[styles.languageLabel, user.language === value && styles.languageLabelSelected]}>{label}</Text></Pressable>)}</View>
      </View>
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{notice}</Text> : null}
      <View style={styles.headingRow}><Text style={styles.sectionTitle}>What Saarthi remembers</Text><Text style={styles.count}>{memories.length}</Text></View>
      <View style={styles.search}><Icon name="search" size={18} color={colors.quiet} /><TextInput accessibilityLabel="Search memories" value={query} onChangeText={setQuery} placeholder="Find a remembered detail" placeholderTextColor={colors.quiet} style={styles.searchInput} /></View>
      {loading ? <View style={styles.loading}><View style={styles.skeleton} /><View style={[styles.skeleton, { width: "65%" }]} /></View> : !filtered.length ? <View style={styles.empty}><Icon name="leaf" size={26} color={colors.accent} /><Text style={styles.emptyTitle}>{query ? "No matching memories" : "Nothing to remember just yet"}</Text><Text style={styles.helper}>{query ? "Try another word, or clear your search." : "Useful details will appear here naturally as you talk. There’s nothing you need to approve."}</Text></View> : filtered.map(item => {
        const editing = editingId === item.id;
        return <View key={item.id} style={styles.memoryRow}>
          <Text style={styles.kind}>{kindLabel[item.kind] ?? "About you"}</Text>
          {editing ? <TextInput accessibilityLabel="Edit remembered detail" autoFocus value={draft} onChangeText={setDraft} multiline maxLength={500} style={styles.editInput} /> : <Text selectable style={styles.memoryText}>{item.proposed_content ?? item.content}</Text>}
          <View style={styles.actions}>{editing ? <>
            <Pressable accessibilityRole="button" accessibilityLabel="Save memory changes" disabled={busyId === item.id || !draft.trim()} onPress={() => void save(item)} style={[styles.saveButton, !draft.trim() && { opacity: .5 }]}>{busyId === item.id ? <ActivityIndicator color={colors.white} /> : <Text style={styles.saveLabel}>Save changes</Text>}</Pressable>
            <Pressable accessibilityRole="button" disabled={busyId === item.id} onPress={() => setEditingId(null)} style={styles.textButton}><Text style={styles.textButtonLabel}>Cancel</Text></Pressable>
          </> : <Pressable accessibilityRole="button" accessibilityLabel={`Edit memory: ${item.content}`} onPress={() => { setEditingId(item.id); setDraft(item.proposed_content ?? item.content); setNotice(""); }} style={styles.textButton}><Icon name="edit" size={16} color={colors.primary} /><Text style={styles.textButtonLabel}>Edit</Text></Pressable>}
            <Pressable accessibilityRole="button" accessibilityLabel={`Delete memory: ${item.content}`} onPress={() => setDeleting(item)} style={styles.textButton}><Icon name="trash" size={16} color={colors.quiet} /><Text style={styles.removeLabel}>Delete</Text></Pressable>
          </View>
        </View>;
      })}
      {!loading && error ? <Pressable accessibilityRole="button" onPress={() => void refresh()} style={styles.textButton}><Icon name="retry" size={18} /><Text style={styles.textButtonLabel}>Reload memories</Text></Pressable> : null}
      <View style={styles.section}><Text style={styles.label}>Your privacy</Text><Text style={styles.helper}>Your chats belong to your account. Voice is processed for transcription or playback; recordings aren’t kept on our server. Live calls use LiveKit, Google and ElevenLabs. Their services process text and audio and may retain data under their own policies. Finalized call transcripts stay in your conversation history. Memory off stops cross-chat recall and new memory saves; it does not erase history.</Text><Text style={styles.helper}>Saarthi offers reflection, not medical treatment or divine instructions. If you need urgent support, reach out to a trusted person or local emergency service.</Text></View>
      <View style={styles.section}><Text style={styles.label}>Account</Text><Text selectable style={styles.helper}>{user.email}</Text><Pressable accessibilityRole="button" onPress={onSignOut} style={styles.accountButton}><Icon name="logout" size={18} color={colors.primary} /><Text style={styles.textButtonLabel}>Sign out</Text></Pressable><Pressable accessibilityRole="button" onPress={() => setDeleting("account")} style={styles.textButton}><Icon name="trash" size={17} color={colors.danger} /><Text style={styles.deleteLabel}>Delete account & all data</Text></Pressable></View>
      <Text style={styles.version}>Saarthi · Wisdom for everyday life</Text>
    </ScrollView>
    <ConfirmDialog visible={!!deleting} title={deleting === "account" ? "Delete your account?" : "Delete this memory?"} description={deleting === "account" ? "All your conversations and saved memories will be permanently removed. This cannot be undone." : "This saved memory will be removed. Its original messages remain in history; delete that conversation to remove them too."} confirmLabel={deleting === "account" ? "Delete account" : "Delete memory"} busy={deletingBusy} onClose={() => setDeleting(null)} onConfirm={() => void confirmDelete()} />
  </KeyboardAvoidingView>;
}
const styles = StyleSheet.create({
  root: { flex: 1 }, header: { minHeight: 74, flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: colors.border }, iconButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" }, headerTitle: { color: colors.ink, fontSize: 18, fontWeight: "600" },
  content: { width: "100%", maxWidth: 700, alignSelf: "center", padding: 24, gap: 14 }, sectionTitle: { color: colors.ink, fontFamily: fonts.heading, fontSize: 24, lineHeight: 32, flexShrink: 1 }, body: { color: colors.body, fontSize: 15, lineHeight: 25 }, label: { color: colors.ink, fontSize: 15, fontWeight: "600", lineHeight: 23 }, helper: { color: colors.quiet, fontSize: 14, lineHeight: 23 },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: 16, paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: colors.border }, toggleCopy: { flex: 1, gap: 6 }, section: { gap: 10, marginTop: 12, paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: colors.border }, languageChoices: { flexDirection: "row", gap: 8, flexWrap: "wrap", marginTop: 2 }, languageOption: { minHeight: 46, justifyContent: "center", borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 13 }, languageSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, languageLabel: { color: colors.body, fontSize: 13 }, languageLabelSelected: { color: colors.white, fontWeight: "600" },
  headingRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 20, gap: 12 }, count: { color: colors.quiet, fontSize: 14 }, search: { flexDirection: "row", alignItems: "center", gap: 8, borderBottomWidth: 1, borderBottomColor: colors.border }, searchInput: { fontFamily: fonts.body, flex: 1, minHeight: 48, color: colors.ink, fontSize: 14 },
  memoryRow: { paddingVertical: 16, gap: 10, borderBottomWidth: 1, borderBottomColor: colors.border }, kind: { color: colors.accent, fontSize: 12, fontWeight: "600" }, memoryText: { color: colors.ink, fontSize: 16, lineHeight: 25 }, editInput: { fontFamily: fonts.body, borderWidth: 1, borderColor: colors.primary, borderRadius: radii.control, padding: 12, minHeight: 94, fontSize: 16, lineHeight: 24, color: colors.ink, textAlignVertical: "top" }, actions: { flexDirection: "row", alignItems: "center", gap: 12, flexWrap: "wrap" }, saveButton: { backgroundColor: colors.primary, minHeight: 44, borderRadius: 10, paddingHorizontal: 14, justifyContent: "center" }, saveLabel: { color: colors.white, fontSize: 13, fontWeight: "600" }, textButton: { minHeight: 44, flexDirection: "row", gap: 8, alignItems: "center", paddingHorizontal: 4 }, textButtonLabel: { color: colors.primary, fontSize: 14, fontWeight: "600" }, removeLabel: { color: colors.quiet, fontSize: 14 },
  accountButton: { minHeight: 48, flexDirection: "row", justifyContent: "center", gap: 8, alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radii.control, marginTop: 6 }, deleteLabel: { color: colors.danger, fontSize: 14 }, error: { color: colors.danger, fontSize: 14, lineHeight: 22 }, notice: { color: colors.success, fontSize: 14, lineHeight: 22 },
  empty: { gap: 10, paddingVertical: 24 }, emptyTitle: { color: colors.ink, fontSize: 17, fontWeight: "500" }, loading: { gap: 12, paddingVertical: 24 }, skeleton: { width: "90%", height: 16, borderRadius: 6, backgroundColor: colors.surface }, version: { color: colors.quiet, fontSize: 12, textAlign: "center", paddingVertical: 12 },
});
