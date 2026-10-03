import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StatusBar, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { ApiError, getMe, onUnauthorized, readSession, saveSession, setAccessToken, signOut } from "./src/api";
import { CallHome } from "./src/screens/CallHome";
import { SignInScreen } from "./src/screens/SignInScreen";
import { SaarthiMark } from "./src/components/Icons";
import { colors, fonts } from "./src/theme";
import type { User } from "./src/types";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState("");
  const live = useRef(true);
  async function start() {
    setStarting(true); setError("");
    try {
      const token = await readSession();
      if (token) {
        setAccessToken(token);
        try { const profile = await getMe(); if (live.current) setUser(profile); }
        catch (err) {
          if (err instanceof ApiError && err.status === 401) await signOut();
          else throw err;
        }
      }
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : "Couldn't open Saarthi. Please try again."); }
    finally { if (live.current) setStarting(false); }
  }
  useEffect(() => {
    live.current = true;
    onUnauthorized(() => { void leave(); });
    void start();
    return () => { live.current = false; onUnauthorized(null); };
  }, []);
  async function signedIn(token: string, profile: User) {
    await saveSession(token); setAccessToken(token); setUser(profile);
  }
  async function leave() {
    try { await signOut(); }
    finally { if (live.current) { setUser(null); setError(""); } }
  }
  return <SafeAreaProvider><SafeAreaView style={{ flex: 1, backgroundColor: user ? "#100c09" : colors.background }}>
    <StatusBar barStyle={user ? "light-content" : "dark-content"} backgroundColor={user ? "#100c09" : colors.background} />
    {starting || error ? <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 28, gap: 20 }}>
      <SaarthiMark size={64} /><Text style={{ color: colors.primary, fontFamily: fonts.heading, fontSize: 30 }}>Saarthi</Text>
      {starting ? <ActivityIndicator color={colors.primary} accessibilityLabel="Opening Saarthi" /> : <>
        <Text accessibilityRole="alert" style={{ color: colors.body, fontSize: 16, textAlign: "center", lineHeight: 25 }}>{error}</Text>
        <Pressable accessibilityRole="button" onPress={() => void start()} style={{ minHeight: 48, justifyContent: "center", backgroundColor: colors.primary, borderRadius: 12, paddingHorizontal: 24 }}><Text style={{ color: colors.white, fontWeight: "600" }}>Try again</Text></Pressable>
      </>}
    </View> : user ? <CallHome key={user.id} user={user} onSignOut={() => void leave()} onUserChange={setUser} /> : <SignInScreen onSignIn={signedIn} />}
  </SafeAreaView></SafeAreaProvider>;
}
