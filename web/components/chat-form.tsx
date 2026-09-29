"use client";

import { useState, type FormEvent } from "react";

import type { ActivityEntry } from "@/components/activity-feed";
import { sendChat } from "@/lib/api";

type Props = {
  onActivity: (kind: ActivityEntry["kind"], text: string) => void;
};

export function ChatForm({ onActivity }: Props) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text || sending) return;

    setSending(true);
    onActivity("user", text);
    try {
      onActivity("assistant", await sendChat(text));
      setMessage("");
    } catch (error) {
      onActivity("error", error instanceof Error ? error.message : "Request failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="Ask Personal AI…"
        aria-label="Message"
        className="flex-1 rounded border border-gray-300 px-3 py-2"
      />
      <button
        type="submit"
        disabled={sending || !message.trim()}
        className="rounded bg-gray-900 px-4 py-2 text-white disabled:opacity-50"
      >
        {sending ? "Sending…" : "Send"}
      </button>
    </form>
  );
}
