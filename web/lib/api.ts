// Client for the Personal AI backend. The browser talks to the backend directly;
// API keys (OpenAI etc.) stay on the backend and never reach this code.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Device = {
  id: string;
  name: string;
  type: string;
  status: "online" | "offline";
  last_seen: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(`Cannot reach the backend at ${API_URL}`);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function getDevices(): Promise<Device[]> {
  return request<Device[]>("/api/v1/devices");
}

export async function sendChat(message: string): Promise<string> {
  const data = await request<{ message: string }>("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return data.message;
}
