import { useEffect, useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { requestCode, verifyCode } from "../api";
import { PrimaryButton } from "../components/PrimaryButton";
import { SaarthiMark } from "../components/Icons";
import { colors, fonts, radii } from "../theme";
import type { User } from "../types";

export function SignInScreen({ onSignIn }: { onSignIn: (token: string, user: User) => Promise<void> }) {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState(""); const [code, setCode] = useState("");
  const [sent, setSent] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [cooldown, setCooldown] = useState(0);
  const [localCode, setLocalCode] = useState(false);
  const flight = useRef(false);
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  useEffect(() => { if (!cooldown) return; const timer = setTimeout(() => setCooldown(c => c - 1), 1000); return () => clearTimeout(timer); }, [cooldown]);
  async function sendCode() {
    if (!validEmail || flight.current || cooldown > 0) return;
    flight.current = true; setBusy(true); setError("");
    try { const result = await requestCode(email.trim()); setCode(result.dev_code ?? ""); setLocalCode(!!result.dev_code); setSent(true); setCooldown(45); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't send a sign-in code."); }
    finally { flight.current = false; setBusy(false); }
  }
  async function finishSignIn() {
    if (!/^\d{6}$/.test(code) || flight.current) return;
    flight.current = true; setBusy(true); setError("");
    try { const result = await verifyCode(email.trim(), code); await onSignIn(result.access_token, result.user); }
    catch (err) { setError(err instanceof Error ? err.message : "That code didn't work. Try again."); }
    finally { flight.current = false; setBusy(false); }
  }
  return <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "ios" ? "padding" : Platform.OS === "android" ? "height" : undefined} keyboardVerticalOffset={insets.top}>
    <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
      <View style={styles.content}>
        <View style={styles.brand}><SaarthiMark size={40} /><Text style={styles.brandName}>Saarthi</Text></View>
        <View style={styles.copy}><Text style={styles.namaste}>नमस्ते</Text><Text accessibilityRole="header" style={styles.title}>Ancient wisdom.{"\n"}A space for you.</Text><Text style={styles.description}>A listening ear for what life brings. Find perspective in the Bhagavad Gita, and a little clarity in your next step.</Text></View>
        <View style={styles.form}>
          <Text accessibilityRole="header" style={styles.formTitle}>{sent ? "Check your inbox" : "Come as you are."}</Text>
          <Text style={styles.helper}>{sent ? `A six-digit code for ${email.trim()}. It’s valid for 10 minutes.` : "Sign in with your email. No password to remember."}</Text>
          {!sent ? <><Text style={styles.label}>Email address</Text><TextInput accessibilityLabel="Email address" autoCapitalize="none" autoComplete="email" keyboardType="email-address" textContentType="emailAddress" editable={!busy} value={email} onChangeText={setEmail} placeholder="you@example.com" placeholderTextColor={colors.quiet} style={styles.input} returnKeyType="done" onSubmitEditing={() => void sendCode()} /></> : <><Text style={styles.label}>Sign-in code</Text><TextInput accessibilityLabel="Six-digit sign-in code" autoFocus autoComplete="one-time-code" textContentType="oneTimeCode" keyboardType="number-pad" maxLength={6} editable={!busy} value={code} onChangeText={v => setCode(v.replace(/\D/g, ""))} placeholder="000000" placeholderTextColor={colors.quiet} style={[styles.input, styles.codeInput]} onSubmitEditing={() => void finishSignIn()} />{localCode ? <Text style={styles.localNote}>Local development: your code is filled in automatically.</Text> : null}</>}
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <PrimaryButton label={sent ? "Continue to Saarthi" : "Send sign-in code"} onPress={sent ? finishSignIn : sendCode} busy={busy} disabled={sent ? code.length !== 6 : !validEmail} />
          {sent ? <View style={styles.links}><Pressable accessibilityRole="button" disabled={busy} onPress={() => { setSent(false); setCode(""); setError(""); setCooldown(0); }} style={styles.link}><Text style={styles.linkText}>Change email</Text></Pressable><Pressable accessibilityRole="button" accessibilityState={{ disabled: cooldown > 0 || busy }} disabled={cooldown > 0 || busy} onPress={() => void sendCode()} style={styles.link}><Text style={[styles.linkText, cooldown > 0 && { color: colors.quiet }]}>{cooldown ? `Resend in ${cooldown}s` : "Resend code"}</Text></Pressable></View> : null}
        </View>
        <Text style={styles.disclaimer}>A private AI companion for reflection, inspired by the Gita. Useful details can be remembered; you can edit, delete, or switch memory off. Guidance, not therapy.</Text>
      </View>
    </ScrollView>
  </KeyboardAvoidingView>;
}
const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background }, scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 28, paddingVertical: 30 }, content: { width: "100%", maxWidth: 440, alignSelf: "center", gap: 32 },
  brand: { flexDirection: "row", alignItems: "center", gap: 10 }, brandName: { color: colors.primary, fontSize: 27, fontFamily: fonts.heading }, copy: { gap: 16 }, namaste: { color: colors.accent, fontSize: 19, lineHeight: 28 }, title: { color: colors.ink, fontFamily: fonts.heading, fontSize: 38, lineHeight: 46 }, description: { color: colors.body, fontSize: 16, lineHeight: 26 },
  form: { gap: 12 }, formTitle: { color: colors.ink, fontSize: 20, fontWeight: "600" }, label: { color: colors.body, fontWeight: "600", fontSize: 13, marginTop: 6 }, input: { fontFamily: fonts.body, borderWidth: 1, borderColor: colors.border, borderRadius: radii.control, minHeight: 54, paddingHorizontal: 16, color: colors.ink, fontSize: 16 }, codeInput: { letterSpacing: 10, fontSize: 22 }, helper: { color: colors.quiet, fontSize: 14, lineHeight: 23 }, error: { color: colors.danger, fontSize: 14, lineHeight: 22 }, localNote: { color: colors.accent, fontSize: 12, lineHeight: 20 },
  links: { flexDirection: "row", justifyContent: "space-between" }, link: { minHeight: 44, justifyContent: "center", paddingHorizontal: 4 }, linkText: { color: colors.primary, fontSize: 13, fontWeight: "600" }, disclaimer: { color: colors.quiet, fontSize: 12, lineHeight: 20, textAlign: "center" },
});
