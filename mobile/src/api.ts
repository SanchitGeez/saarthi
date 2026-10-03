import * as SecureStore from "expo-secure-store";
import { File as ExpoFile } from "expo-file-system";
import { fetch as expoFetch } from "expo/fetch";
import { Platform } from "react-native";
import type { Conversation, Memory, Message, User } from "./types";

export const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://10.0.2.2:8000/api";
let accessToken: string | null = null;
let unauthorized: (() => void) | null = null;
export const setAccessToken = (value: string | null) => { accessToken = value; };
export const onUnauthorized = (handler: (() => void) | null) => { unauthorized = handler; };
const SESSION_KEY = "saarthi-session";
export const readSession = async () => Platform.OS === "web"
  ? window.sessionStorage.getItem(SESSION_KEY) : SecureStore.getItemAsync(SESSION_KEY);
export const saveSession = async (token: string) => {
  if (Platform.OS === "web") window.sessionStorage.setItem(SESSION_KEY, token);
  else await SecureStore.setItemAsync(SESSION_KEY, token);
};
export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message); this.name = "ApiError"; }
}
async function request(path: string, init: RequestInit = {}, timeout = 20000): Promise<Response> {
  const started = Date.now();
  const method = init.method ?? "GET";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  try {
    const response = await expoFetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal });
    if (__DEV__) console.info(`[api] ${method} ${path} → ${response.status} (${Date.now() - started} ms)`);
    if (!response.ok) {
      let message = "Something went wrong. Please try again.";
      try {
        const payload = await response.json();
        if (typeof payload.detail === "string") message = payload.detail;
        else if (response.status === 422) {
          message = "Check the details and try again.";
          if (Array.isArray(payload.detail)) {
            if (__DEV__) console.info("[api] Validation", payload.detail.map((item: { loc?: unknown; msg?: string; type?: string }) => ({ location: item.loc, message: item.msg, type: item.type })));
            if (path === "/voice/speak") message = payload.detail.some((item: { type?: string }) => item.type === "string_too_long")
              ? "This reply is too long to play as one recording."
              : "Couldn't prepare this reply for playback. Reload the chat and try again.";
          }
        }
      } catch {}
      if (response.status === 401 && accessToken) unauthorized?.();
      throw new ApiError(message, response.status);
    }
    return response;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    // Recoverable failures belong in the inline UI, not a blocking LogBox overlay.
    if (__DEV__) console.info(`[api] ${method} ${path} → ${controller.signal.aborted ? "timeout" : "request failed"} (${Date.now() - started} ms)`);
    throw new ApiError(controller.signal.aborted
      ? "The connection took too long. Please try again."
      : "Couldn't reach Saarthi. Check your connection and try again.");
  } finally { clearTimeout(timer); }
}
async function call<T>(path: string, init: RequestInit = {}, timeout?: number): Promise<T> {
  const response = await request(path, init, timeout);
  return response.status === 204 ? undefined as T : response.json();
}
export const requestCode = (email: string) => call<{ ok: boolean; message: string; dev_code?: string }>("/auth/request-code", { method: "POST", body: JSON.stringify({ email }) });
export const verifyCode = (email: string, code: string) => call<{ access_token: string; user: User }>("/auth/verify-code", { method: "POST", body: JSON.stringify({ email, code }) });
export const getMe = () => call<User>("/auth/me");
export const getConversations = () => call<Conversation[]>("/conversations");
export const createConversation = (isPrivate = false) => call<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ private: isPrivate }) });
export const getMessages = (id: string) => call<Message[]>(`/conversations/${id}/messages`);
export const sendTurn = (id: string, text: string, clientId: string) => call<Message & { conversation_title: string }>(`/conversations/${id}/turns`, { method: "POST", body: JSON.stringify({ text, client_id: clientId }) }, 105000);
export const discardTurn = (id: string, turnId: string) => call<void>(`/conversations/${id}/turns/${turnId}`, { method: "DELETE" });
export const deleteConversation = (id: string) => call<void>(`/conversations/${id}`, { method: "DELETE" });
export const getMemories = () => call<Memory[]>("/memories");
export const updateMemory = (id: string, patch: { content: string }) => call<{ ok: boolean; content: string }>(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ ...patch, action: "confirm" }) });
export const deleteMemory = (id: string) => call<void>(`/memories/${id}`, { method: "DELETE" });
export const updatePreferences = (patch: { memory_enabled?: boolean; language?: string }) => call<{ memory_enabled: boolean; language: User["language"] }>("/me/preferences", { method: "PATCH", body: JSON.stringify(patch) });
export const deleteAccount = () => call<void>("/auth/me", { method: "DELETE" });
export const getVoiceStatus = () => call<{ available: boolean }>("/voice/status");
export async function transcribeVoice(uri: string): Promise<string> {
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    if (!blob.size) throw new ApiError("The recording was empty. Record a little longer and try again.");
    if (blob.size > 12 * 1024 * 1024) throw new ApiError("That recording is too large. Try a shorter note.");
    form.append("file", blob, "voice-note.webm");
  } else {
    // SDK 57's Expo fetch accepts File/Blob parts, not the old RN URI object.
    const file = new ExpoFile(uri.startsWith("/") ? `file://${uri}` : uri);
    if (!file.exists) throw new ApiError("The recording is no longer available. Please record it again.");
    if (!file.size) throw new ApiError("The recording was empty. Record a little longer and try again.");
    if (file.size > 12 * 1024 * 1024) throw new ApiError("That recording is too large. Try a shorter note.");
    if (__DEV__) console.info(`[voice] Recording ready: ${file.size} bytes (${file.type || "audio/mp4"})`);
    form.append("file", file);
  }
  return (await call<{ text: string }>("/voice/transcribe", { method: "POST", body: form }, 90000)).text;
}
export const speakReply = async (text: string) => (await request("/voice/speak", {
  method: "POST", headers: { Accept: "audio/mpeg" }, body: JSON.stringify({ text }),
}, 90000)).arrayBuffer();
export async function signOut() {
  setAccessToken(null);
  if (Platform.OS === "web") window.sessionStorage.removeItem(SESSION_KEY);
  else await SecureStore.deleteItemAsync(SESSION_KEY);
}
