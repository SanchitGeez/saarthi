import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";
import { colors, radii } from "../theme";

export function PrimaryButton({
  label,
  onPress,
  disabled = false,
  busy = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || busy, busy }}
      aria-busy={busy}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [styles.button, (disabled || busy) && styles.disabled, pressed && styles.pressed]}
    >
      {busy ? <ActivityIndicator color={colors.white} /> : <Text style={styles.label}>{label}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 52,
    paddingHorizontal: 22,
    borderRadius: radii.control,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  label: { color: colors.white, fontSize: 16, fontWeight: "700" },
  disabled: { opacity: 0.58 },
  pressed: { opacity: 0.84 },
});
