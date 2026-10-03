export type User = {
  id: string;
  email: string;
  memory_enabled: boolean;
  language: "auto" | "en" | "hi" | "hinglish";
};
export type Conversation = { id: string; title: string; private: boolean; updated_at: string };
export type Verse = {
  reference: string; title: string; sanskrit: string; english: string; hindi: string;
  source_url: string; translation_note: string; note?: string;
};
export type Message = {
  id: string;
  turn_id?: string;
  role: "user" | "assistant";
  text: string;
  status?: "processing" | "completed" | "failed";
  error?: string | null;
  error_code?: number | null;
  verses?: Verse[];
  created_at?: string;
};
export type Memory = {
  id: string; kind: string; content: string; proposed_content: string | null;
  source_excerpt: string; status: "pending" | "pending_update" | "confirmed" | "rejected";
};
