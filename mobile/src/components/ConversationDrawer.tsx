import { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SaarthiMark, Icon } from "./Icons";
import { ConfirmDialog } from "./ConfirmDialog";
import { colors, fonts, radii } from "../theme";
import type { Conversation } from "../types";

export function ConversationDrawer({ conversations, activeId, email, onSelect, onCreate, onSettings, onSignOut, onClose, onDelete, loading, error, onRefresh }: {
  conversations: Conversation[]; activeId: string | null; email: string;
  onSelect: (id: string) => void; onCreate: (isPrivate?: boolean) => void;
  onSettings: () => void; onSignOut: () => void; onClose?: () => void;
  onDelete: (id: string) => Promise<void>; loading: boolean; error: string; onRefresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const filtered = useMemo(() => conversations.filter(c => c.title.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim())), [query, conversations]);
  const groups = filtered.reduce<Record<string, Conversation[]>>((acc, c) => {
    const date = new Date(c.updated_at);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const label = date >= today ? "Today" : date >= new Date(today.getTime() - 7 * 86400000) ? "This week" : "Earlier";
    (acc[label] ??= []).push(c); return acc;
  }, {});
  return (
    <View style={styles.root}>
      <View style={styles.brand}>
        <SaarthiMark size={42} />
        <View style={{ flex: 1 }}><Text style={styles.brandName}>Saarthi</Text><Text style={styles.brandSub}>Wisdom for everyday life</Text></View>
        {onClose ? <Pressable accessibilityRole="button" accessibilityLabel="Close conversations" onPress={onClose} style={styles.iconButton}><Icon name="close" size={20} /></Pressable> : null}
      </View>
      <Pressable accessibilityRole="button" onPress={() => onCreate(false)} style={({ pressed }) => [styles.createButton, pressed && styles.pressed]}>
        <Icon name="plus" size={19} color={colors.white} /><Text style={styles.createLabel}>New conversation</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => onCreate(true)} style={styles.privateButton}>
        <Icon name="lock" size={17} color={colors.primary} /><Text style={styles.privateLabel}>Chat without memory</Text>
      </Pressable>
      <View style={styles.search}><Icon name="search" size={18} color={colors.quiet} />
        <TextInput accessibilityLabel="Search conversations" value={query} onChangeText={setQuery} placeholder="Search conversations" placeholderTextColor={colors.quiet} style={styles.searchInput} />
        {query ? <Pressable accessibilityRole="button" accessibilityLabel="Clear search" onPress={() => setQuery("")} style={styles.iconButton}><Icon name="close" size={17} /></Pressable> : null}
      </View>
      <ScrollView style={styles.list} contentContainerStyle={styles.listContent} keyboardShouldPersistTaps="handled">
        {loading ? <ActivityIndicator color={colors.primary} accessibilityLabel="Loading conversations" /> : null}
        {error ? <View style={styles.error}><Text accessibilityRole="alert" style={styles.errorText}>{error}</Text><Pressable accessibilityRole="button" onPress={onRefresh} style={styles.retry}><Text style={styles.privateLabel}>Try again</Text></Pressable></View> : null}
        {!loading && !error && !filtered.length ? <Text style={styles.empty}>{query ? "No conversations match this search." : "Your conversations will appear here after you send a message."}</Text> : null}
        {Object.entries(groups).map(([label, items]) => <View key={label}>
          <Text style={styles.sectionTitle}>{label}</Text>
          {items.map(item => <View key={item.id} style={[styles.row, activeId === item.id && styles.rowActive]}>
            <Pressable accessibilityRole="button" aria-current={activeId === item.id ? "page" : undefined} accessibilityState={{ selected: activeId === item.id }} accessibilityLabel={`${item.private ? "Without memory, " : ""}${item.title}`} onPress={() => onSelect(item.id)} style={styles.rowMain}>
              {item.private ? <Icon name="lock" size={15} color={colors.quiet} /> : null}
              <Text numberOfLines={2} style={[styles.rowTitle, activeId === item.id && styles.rowTitleActive]}>{item.title}</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel={`Delete ${item.title}`} onPress={() => setDeleting(item)} style={styles.iconButton}><Icon name="trash" size={17} color={colors.quiet} /></Pressable>
          </View>)}
        </View>)}
      </ScrollView>
      <View style={styles.footer}>
        <Text numberOfLines={1} style={styles.email}>{email}</Text>
        <Pressable accessibilityRole="button" onPress={onSettings} style={styles.settingsButton}><Icon name="settings" size={20} color={colors.body} /><Text style={styles.settingsLabel}>Memory & settings</Text></Pressable>
        <Pressable accessibilityRole="button" onPress={onSignOut} style={styles.settingsButton}><Icon name="logout" size={20} color={colors.body} /><Text style={styles.settingsLabel}>Sign out</Text></Pressable>
      </View>
      <ConfirmDialog visible={!!deleting} title="Delete this conversation?" description="Its messages and memories learned from this chat will be permanently removed." busy={busy} onClose={() => setDeleting(null)} onConfirm={() => void (async () => {
        if (!deleting) return; setBusy(true);
        try { await onDelete(deleting.id); setDeleting(null); } catch {} finally { setBusy(false); }
      })()} />
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: 16, paddingTop: 16 },
  brand: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 24 },
  brandName: { color: colors.primary, fontFamily: fonts.heading, fontSize: 25 },
  brandSub: { color: colors.quiet, fontSize: 12, marginTop: 3 },
  createButton: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, minHeight: 50, borderRadius: radii.control, backgroundColor: colors.primary },
  createLabel: { color: colors.white, fontWeight: "600", fontSize: 15 },
  privateButton: { flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", minHeight: 48, marginTop: 4 },
  privateLabel: { color: colors.primary, fontWeight: "600", fontSize: 14 },
  search: { flexDirection: "row", alignItems: "center", gap: 8, borderBottomWidth: 1, borderBottomColor: colors.border, marginTop: 12, marginBottom: 16 },
  searchInput: { fontFamily: fonts.body, flex: 1, minHeight: 48, fontSize: 14, color: colors.ink },
  sectionTitle: { color: colors.quiet, fontSize: 12, fontWeight: "600", marginTop: 12, marginBottom: 8, paddingHorizontal: 8 },
  list: { flex: 1 }, listContent: { paddingBottom: 16 },
  empty: { color: colors.quiet, fontSize: 14, lineHeight: 22, padding: 8 },
  row: { flexDirection: "row", alignItems: "center", borderRadius: 10, minHeight: 48, paddingLeft: 10 },
  rowActive: { backgroundColor: colors.white },
  rowMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: 7, minHeight: 48 },
  rowTitle: { color: colors.body, fontSize: 14, lineHeight: 21, flexShrink: 1, paddingVertical: 10 },
  rowTitleActive: { color: colors.primary, fontWeight: "600" },
  iconButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  footer: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 16, paddingBottom: 12 },
  email: { color: colors.quiet, fontSize: 13, marginBottom: 6, paddingHorizontal: 8 },
  settingsButton: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48, paddingHorizontal: 8 },
  settingsLabel: { color: colors.body, fontSize: 14, fontWeight: "500" },
  pressed: { opacity: .8 }, error: { padding: 8 }, errorText: { color: colors.danger, fontSize: 14, lineHeight: 21 }, retry: { minHeight: 48, justifyContent: "center" },
});
