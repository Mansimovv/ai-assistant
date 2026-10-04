"use client";

import { useEffect, useState, useSyncExternalStore, type FormEvent } from "react";

import { Activity } from "@/components/activity";
import { DeviceList } from "@/components/device-list";
import { History } from "@/components/history";
import { Orb } from "@/components/orb";
import { PendingActionCard } from "@/components/pending-action";
import {
  cancelAction,
  confirmAction,
  getConversation,
  getInfo,
  sendChat,
  type Message,
  type PendingAction,
} from "@/lib/api";
import { useVoice } from "@/lib/use-voice";
import { useWakeWord } from "@/lib/use-wake-word";

const WAKE_PREFERENCE = "jarvis.wake";
const WAKE_EVENT = "jarvis-wake-change";

// "Hey Jarvis" and the double clap are on unless switched off; remembered per browser.
function readWakePreference(): boolean {
  try {
    return localStorage.getItem(WAKE_PREFERENCE) !== "off";
  } catch {
    return true;
  }
}

function subscribeWakePreference(onChange: () => void) {
  window.addEventListener(WAKE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(WAKE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export default function Home() {
  // The name comes from the backend, so renaming the assistant is one setting.
  const [name, setName] = useState("Jarvis");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activityKey, setActivityKey] = useState(0);
  // "Hey Jarvis" listening. Browsers only let a page play audio after the user has
  // interacted with it, so after a reload it arms on the first click or key press.
  const wakeOn = useSyncExternalStore(subscribeWakePreference, readWakePreference, () => false);
  const [heard, setHeard] = useState("");

  const acted = () => setActivityKey((key) => key + 1);

  function addLocalMessage(role: Message["role"], content: string) {
    setMessages((current) => [
      ...current,
      { id: -Date.now() - current.length, role, content, created_at: new Date().toISOString() },
    ]);
  }

  const voice = useVoice({
    onTranscript: addLocalMessage,
    onPending: (incoming) => setPending((current) => [...current, ...incoming]),
    onActed: acted,
    onError: setError,
  });

  const wakeSupported = useWakeWord(wakeOn && voice.state === "off", {
    onWake: (command) => {
      setHeard("");
      void voice.start(command || undefined);
    },
    onHeard: setHeard,
    onError: setError,
  });

  // The last thing heard fades after a few seconds.
  useEffect(() => {
    if (!heard) return;
    const timer = setTimeout(() => setHeard(""), 4000);
    return () => clearTimeout(timer);
  }, [heard]);

  function toggleWake() {
    try {
      localStorage.setItem(WAKE_PREFERENCE, wakeOn ? "off" : "on");
    } catch {
      // storage unavailable: nothing to remember it in
    }
    window.dispatchEvent(new Event(WAKE_EVENT));
  }

  // Load the shared thread, so any device continues the same conversation.
  useEffect(() => {
    getInfo()
      .then((info) => setName(info.name))
      .catch(() => undefined);
    getConversation()
      .then((conversation) => {
        setConversationId(conversation.id);
        setMessages(conversation.messages);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

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
      setPending((current) => [...current, ...reply.pending]);
      if (reply.actions.length > 0) acted();
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
      acted();
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

  const live = voice.state === "live";
  const waiting = wakeOn && voice.state === "off";
  const status =
    voice.state === "connecting"
      ? "Qoşulur…"
      : busy
        ? "Düşünürəm…"
        : live
          ? "Dinləyirəm — susanda özüm yatacağam"
          : waiting
            ? "“Hey Jarvis” de və ya iki dəfə əl çal"
            : "Danışmaq üçün mikrofona bas";

  return (
    <main className="grid h-dvh grid-cols-1 overflow-hidden bg-[#05070b] text-white md:grid-cols-[320px_1fr] xl:grid-cols-[320px_1fr_260px]">
      <div className="hidden h-dvh md:block">
        <History current={messages} currentId={conversationId} assistantName={name} />
      </div>

      <section className="relative flex h-dvh flex-col">
        <header className="flex items-center justify-between px-6 pt-5">
          <h1 lang="en" className="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">{name}</h1>
          <div className="flex items-center gap-4">
            {wakeSupported && (
              <button
                onClick={toggleWake}
                title="“Hey Jarvis” deyəndə oyansın"
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  wakeOn ? "border-emerald-400/60 text-emerald-300" : "border-white/15 text-white/50 hover:text-white"
                }`}
              >
                Hey Jarvis {wakeOn ? "· açıq" : "· bağlı"}
              </button>
            )}
            <span className={`text-xs ${live ? "text-emerald-400" : "text-white/40"}`}>
              {live ? "● canlı" : waiting ? "◌ gözləyir" : "○ səs bağlı"}
            </span>
          </div>
        </header>

        <div className="relative min-h-0 flex-1">
          <Orb inputLevel={voice.inputLevel} outputLevel={voice.outputLevel} live={live} thinking={busy} />
        </div>

        <div className="mx-auto w-full max-w-2xl space-y-3 px-4 pb-6">
          <p className="text-center text-xs tracking-widest text-white/50">{status}</p>
          {waiting && heard && <p className="text-center text-xs text-white/30">eşitdim: “{heard}”</p>}
          {error && <p className="text-center text-sm text-rose-400">{error}</p>}
          {pending.map((action) => (
            <PendingActionCard
              key={action.id}
              action={action}
              busy={busy}
              onConfirm={() => handleConfirm(action)}
              onCancel={() => handleCancel(action)}
            />
          ))}

          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 p-1.5 pl-5 backdrop-blur"
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Yaz və ya danış…"
              aria-label="Mesaj"
              className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => (voice.state === "off" ? void voice.start() : voice.stop())}
              title={voice.state === "off" ? "Səslə danış" : "Səsi bitir"}
              className={`h-11 w-11 shrink-0 rounded-full text-lg transition ${
                voice.state === "off"
                  ? "bg-white/10 hover:bg-white/20"
                  : "bg-rose-500/80 shadow-[0_0_24px_rgba(244,63,94,0.6)] hover:bg-rose-500"
              }`}
            >
              {voice.state === "off" ? "🎙" : "■"}
            </button>
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="h-11 shrink-0 rounded-full bg-white px-5 text-sm font-medium text-black disabled:opacity-30"
            >
              Göndər
            </button>
          </form>
        </div>
      </section>

      <aside className="hidden h-dvh space-y-8 overflow-y-auto border-l border-white/10 bg-black/40 p-5 xl:block">
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-white/50">Cihazlar</h2>
          <DeviceList />
        </section>
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-white/50">Son fəaliyyət</h2>
          <Activity reloadKey={activityKey} />
        </section>
      </aside>
    </main>
  );
}
