"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { PendingActionCard } from "@/components/pending-action";
import { VoiceButton } from "@/components/voice";
import {
  cancelAction,
  confirmAction,
  getConversation,
  sendChat,
  type Message,
  type PendingAction,
} from "@/lib/api";

type Props = { onActed: () => void };

export function Chat({ onActed }: Props) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // Load the shared thread, so any device continues the same conversation.
  useEffect(() => {
    getConversation()
      .then((conversation) => {
        setConversationId(conversation.id);
        setMessages(conversation.messages);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  function addLocalMessage(role: Message["role"], content: string) {
    setMessages((current) => [
      ...current,
      { id: -Date.now() - current.length, role, content, created_at: new Date().toISOString() },
    ]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setBusy(true);
    setError(null);
    addLocalMessage("user", text);
    setInput("");
    try {
      const reply = await sendChat(text, conversationId);
      setConversationId(reply.conversation_id);
      if (reply.message) addLocalMessage("assistant", reply.message);
      setPending(reply.pending);
      if (reply.actions.length > 0) onActed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xəta baş verdi");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm(action: PendingAction) {
    setBusy(true);
    setError(null);
    try {
      const reply = await confirmAction(action.id);
      if (reply.message) addLocalMessage("assistant", reply.message);
      setPending((current) => current.filter((item) => item.id !== action.id));
      onActed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xəta baş verdi");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(action: PendingAction) {
    setPending((current) => current.filter((item) => item.id !== action.id));
    await cancelAction(action.id).catch(() => undefined);
    addLocalMessage("assistant", "Ləğv etdim.");
  }

  return (
    <div className="flex h-[70vh] flex-col rounded-lg border border-gray-200 bg-white">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !error && (
          <p className="text-sm text-gray-500">
            Salam. Nə etməli olduğumu yaz — məsələn “Mac-da VS Code-u aç” və ya “Docker işləyir?”
          </p>
        )}
        {messages.map((message) => (
          <div key={message.id} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <p
              className={
                message.role === "user"
                  ? "max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-900 px-3 py-2 text-sm text-white"
                  : "max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-3 py-2 text-sm text-gray-900"
              }
            >
              {message.content}
            </p>
          </div>
        ))}
        {pending.map((action) => (
          <PendingActionCard
            key={action.id}
            action={action}
            busy={busy}
            onConfirm={() => handleConfirm(action)}
            onCancel={() => handleCancel(action)}
          />
        ))}
        {busy && <p className="text-xs text-gray-400">Düşünürəm…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div ref={bottom} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-gray-200 p-3">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Mesaj yaz…"
          aria-label="Mesaj"
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <VoiceButton
          onTranscript={addLocalMessage}
          onPending={(incoming) => setPending((current) => [...current, ...incoming])}
          onActed={onActed}
          onError={setError}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          Göndər
        </button>
      </form>
    </div>
  );
}
