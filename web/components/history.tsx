"use client";

import { useEffect, useRef, useState } from "react";

import { getConversationById, listConversations, type ConversationSummary, type Message } from "@/lib/api";

type Props = {
  // The live thread, updated as you talk or type.
  current: Message[];
  currentId: string | null;
  assistantName: string;
};

type View = { kind: "current" } | { kind: "list" } | { kind: "past"; id: string; messages: Message[] };

const timeFormat = new Intl.DateTimeFormat("az", { hour: "2-digit", minute: "2-digit" });
const dateFormat = new Intl.DateTimeFormat("az", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function History({ current, currentId, assistantName }: Props) {
  const [view, setView] = useState<View>({ kind: "current" });
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (view.kind === "list") {
      listConversations()
        .then(setConversations)
        .catch(() => undefined);
    }
  }, [view.kind]);

  useEffect(() => {
    if (view.kind === "current") bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [current, view.kind]);

  async function open(id: string) {
    if (id === currentId) return setView({ kind: "current" });
    const conversation = await getConversationById(id).catch(() => null);
    if (conversation) setView({ kind: "past", id, messages: conversation.messages });
  }

  const messages = view.kind === "current" ? current : view.kind === "past" ? view.messages : [];

  return (
    <aside className="flex h-full flex-col border-r border-white/10 bg-black/40 backdrop-blur">
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        {view.kind === "past" ? (
          <button onClick={() => setView({ kind: "list" })} className="text-sm text-white/60 hover:text-white">
            ← Söhbətlər
          </button>
        ) : (
          <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-white/50">Tarixçə</h2>
        )}
        <div className="flex gap-1 text-xs">
          <button
            onClick={() => setView({ kind: "current" })}
            className={`rounded px-2 py-1 ${view.kind === "current" ? "bg-white/15 text-white" : "text-white/50 hover:text-white"}`}
          >
            İndi
          </button>
          <button
            onClick={() => setView({ kind: "list" })}
            className={`rounded px-2 py-1 ${view.kind !== "current" ? "bg-white/15 text-white" : "text-white/50 hover:text-white"}`}
          >
            Hamısı
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {view.kind === "list" ? (
          <ul className="space-y-1">
            {conversations.length === 0 && <p className="px-1 text-sm text-white/40">Hələ söhbət yoxdur.</p>}
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  onClick={() => void open(conversation.id)}
                  className="w-full rounded-lg px-3 py-2 text-left hover:bg-white/10"
                >
                  <p className="truncate text-sm text-white/90">{conversation.preview}</p>
                  <p className="text-xs text-white/40">
                    {dateFormat.format(new Date(conversation.updated_at))}
                    {conversation.id === currentId && " · indiki"}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="space-y-3">
            {messages.length === 0 && (
              <p className="px-1 text-sm text-white/40">Danış və ya yaz — söhbət burada görünəcək.</p>
            )}
            {messages.map((message) => (
              <div key={message.id} className={message.role === "user" ? "pl-6" : "pr-6"}>
                <p
                  className={`mb-1 text-[10px] uppercase tracking-widest ${message.role === "user" ? "text-right text-rose-400/80" : "text-emerald-400/80"}`}
                >
                  {message.role === "user" ? "Sən" : assistantName} · {timeFormat.format(new Date(message.created_at))}
                </p>
                <p
                  className={`whitespace-pre-wrap rounded-xl px-3 py-2 text-sm leading-relaxed ${message.role === "user" ? "bg-rose-500/10 text-rose-50" : "bg-emerald-500/10 text-emerald-50"}`}
                >
                  {message.content}
                </p>
              </div>
            ))}
            <div ref={bottom} />
          </div>
        )}
      </div>
    </aside>
  );
}
