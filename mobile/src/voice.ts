import { Directory, File, Paths } from "expo-file-system";
import { randomUUID } from "expo-crypto";
import { Platform } from "react-native";
import { ApiError } from "./api";

export function playbackUri(buffer: ArrayBuffer): string {
  if (!buffer.byteLength) throw new ApiError("No audio was received. Try listening again.", 0);
  if (Platform.OS === "web") return URL.createObjectURL(new Blob([buffer], { type: "audio/mpeg" }));
  const directory = new Directory(Paths.cache, "saarthi-playback");
  // Expo Go's experience cache may have been cleared while the app was open.
  directory.create({ intermediates: true, idempotent: true });
  const file = new File(directory, `reply-${randomUUID()}.mp3`);
  try { file.write(new Uint8Array(buffer)); return file.uri; }
  catch (error) { removeVoiceFile(file.uri); throw error; }
}

export function removeVoiceFile(uri: string | null) {
  if (!uri) return;
  try {
    if (Platform.OS === "web") { if (uri.startsWith("blob:")) URL.revokeObjectURL(uri); }
    else { const file = new File(uri); if (file.exists) file.delete(); }
  } catch { if (__DEV__) console.info("[voice] Temporary file cleanup failed."); }
}

export function voiceError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (__DEV__) console.info("[voice] Native audio operation failed:", error instanceof Error ? error.message : "unknown error");
  return fallback;
}
