import { useRef } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useModalAccessibility } from "./useModalAccessibility";
import { colors, radii } from "../theme";

export function ConfirmDialog({ visible, title, description, confirmLabel = "Delete", busy = false, onConfirm, onClose }: {
  visible: boolean; title: string; description: string; confirmLabel?: string;
  busy?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  const root = useRef<View>(null);
  useModalAccessibility(visible, root, onClose, busy);
  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={() => { if (!busy) onClose(); }}>
      <View style={styles.backdrop}>
        <View ref={root} accessibilityViewIsModal aria-modal={true} role="dialog" aria-labelledby="confirm-title" style={styles.dialog}>
          <ScrollView style={{ flexShrink: 1 }} contentContainerStyle={{ gap: 16 }}>
          <Text nativeID="confirm-title" accessibilityRole="header" style={styles.title}>{title}</Text>
          <Text style={styles.body}>{description}</Text>
          </ScrollView>
          <View style={styles.actions}>
            <Pressable accessibilityRole="button" disabled={busy} onPress={onClose} style={styles.cancel}>
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel={confirmLabel} aria-busy={busy} accessibilityState={{ busy, disabled: busy }} disabled={busy} onPress={onConfirm} style={styles.confirm}>
              {busy ? <ActivityIndicator color={colors.white} /> : <Text style={styles.confirmText}>{confirmLabel}</Text>}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}
const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(35,18,25,0.38)", justifyContent: "center", padding: 24 },
  dialog: { maxHeight: "90%", width: "100%", maxWidth: 400, alignSelf: "center", backgroundColor: colors.white, borderRadius: radii.panel, padding: 24, gap: 16 },
  title: { fontSize: 21, fontWeight: "600", color: colors.ink, lineHeight: 29 },
  body: { fontSize: 15, lineHeight: 23, color: colors.body },
  actions: { flexDirection: "row", gap: 12, marginTop: 8 },
  cancel: { flex: 1, minHeight: 48, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radii.control },
  cancelText: { color: colors.body, fontWeight: "600", fontSize: 15 },
  confirm: { flex: 1, minHeight: 48, alignItems: "center", justifyContent: "center", backgroundColor: colors.danger, borderRadius: radii.control },
  confirmText: { color: colors.white, fontWeight: "600", fontSize: 15 },
});
