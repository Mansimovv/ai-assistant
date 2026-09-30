// Client for the assistant backend. The browser talks to the backend directly;
// provider API keys stay on the backend and never reach this code.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Risk = "low" | "medium" | "high";

export type ApiInfo = { name: string; version: string };

export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type Conversation = { id: string; messages: Message[] };

export type Device = {
  id: string;
  name: string;
  type: string;
  status: "online" | "offline";
  last_seen: string | null;
  capabilities: string[];
};

export type ActionRecord = {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error: string | null;
  duration_ms: number;
};

export type PendingAction = {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  risk: Risk;
};

export type ChatReply = {
  conversation_id: string;
  message: string;
  actions: ActionRecord[];
  pending: PendingAction[];
};

export type ActivityEntry = ActionRecord & { id: number; created_at: string };

export type VoiceSession = { client_secret: string; expires_at: number | null; model: string };

export type VoiceToolResult = {
  result: { ok: boolean; data?: unknown; error?: string | null };
  pending: PendingAction[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(`Backend əlçatan deyil: ${API_URL}`);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Sorğu alınmadı (${response.status})`;
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getInfo = () => request<ApiInfo>("/");
export const getConversation = () => request<Conversation>("/api/v1/conversations/current");
export const getDevices = () => request<Device[]>("/api/v1/devices");
export const getActivity = () => request<ActivityEntry[]>("/api/v1/activity");

export const sendChat = (message: string, conversationId: string | null) =>
  request<ChatReply>("/api/v1/chat", json({ message, conversation_id: conversationId }));

export const confirmAction = (actionId: string) =>
  request<ChatReply>(`/api/v1/actions/${actionId}/confirm`, { method: "POST" });

export const cancelAction = (actionId: string) =>
  request<void>(`/api/v1/actions/${actionId}/cancel`, { method: "POST" });

export const createVoiceSession = () => request<VoiceSession>("/api/v1/voice/session", { method: "POST" });

export const runVoiceTool = (name: string, args: Record<string, unknown>) =>
  request<VoiceToolResult>("/api/v1/voice/tool", json({ name, arguments: args }));

export const recordVoiceTurn = (role: "user" | "assistant", text: string) =>
  request<void>("/api/v1/voice/turn", json({ role, text }));
