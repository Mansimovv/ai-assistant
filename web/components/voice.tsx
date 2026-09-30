"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { createVoiceSession, recordVoiceTurn, runVoiceTool, type PendingAction } from "@/lib/api";

// The browser streams audio straight to OpenAI (that is what keeps it fast), using a
// short-lived credential minted by our backend. Tool calls still go through the backend.
const REALTIME_URL = "https://api.openai.com/v1/realtime/calls";
// Cost guard: an open microphone costs money, so a silent session closes itself.
const IDLE_TIMEOUT_MS = 120_000;

type State = "off" | "connecting" | "live";

type Props = {
  onTranscript: (role: "user" | "assistant", text: string) => void;
  onPending: (pending: PendingAction[]) => void;
  onActed: () => void;
  onError: (message: string) => void;
};

export function VoiceButton({ onTranscript, onPending, onActed, onError }: Props) {
  const [state, setState] = useState<State>("off");
  const [speaking, setSpeaking] = useState(false);
  const connection = useRef<RTCPeerConnection | null>(null);
  const channel = useRef<RTCDataChannel | null>(null);
  const microphone = useRef<MediaStream | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    channel.current?.close();
    connection.current?.close();
    microphone.current?.getTracks().forEach((track) => track.stop());
    channel.current = null;
    connection.current = null;
    microphone.current = null;
    setSpeaking(false);
    setState("off");
  }, []);

  useEffect(() => stop, [stop]);

  function resetIdleTimer() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(stop, IDLE_TIMEOUT_MS);
  }

  async function handleEvent(raw: string) {
    resetIdleTimer();
    const event = JSON.parse(raw) as {
      type: string;
      transcript?: string;
      name?: string;
      call_id?: string;
      arguments?: string;
      error?: { message?: string };
    };

    switch (event.type) {
      case "conversation.item.input_audio_transcription.completed":
        if (event.transcript?.trim()) {
          onTranscript("user", event.transcript);
          void recordVoiceTurn("user", event.transcript).catch(() => undefined);
        }
        break;

      case "response.output_audio_transcript.done":
        setSpeaking(false);
        if (event.transcript?.trim()) {
          onTranscript("assistant", event.transcript);
          void recordVoiceTurn("assistant", event.transcript).catch(() => undefined);
        }
        break;

      case "response.output_audio.delta":
        setSpeaking(true);
        break;

      case "response.function_call_arguments.done":
        await executeTool(event.name ?? "", event.call_id ?? "", event.arguments ?? "{}");
        break;

      case "error":
        onError(event.error?.message ?? "Səs sessiyasında xəta");
        break;
    }
  }

  async function executeTool(name: string, callId: string, rawArguments: string) {
    let result: unknown;
    let pending: PendingAction[] = [];
    try {
      const response = await runVoiceTool(name, JSON.parse(rawArguments || "{}") as Record<string, unknown>);
      result = response.result;
      pending = response.pending;
    } catch (error) {
      result = { ok: false, error: error instanceof Error ? error.message : "Əməliyyat alınmadı" };
    }

    // Give the model the real result, then let it speak.
    channel.current?.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: callId, output: JSON.stringify(result) },
      }),
    );
    channel.current?.send(JSON.stringify({ type: "response.create" }));

    if (pending.length > 0) onPending(pending);
    onActed();
  }

  async function start() {
    setState("connecting");
    try {
      const session = await createVoiceSession();

      const peer = new RTCPeerConnection();
      connection.current = peer;

      player.current ??= new Audio();
      player.current.autoplay = true;
      peer.ontrack = (event) => {
        if (player.current) {
          player.current.srcObject = event.streams[0];
          void player.current.play().catch(() => undefined);
        }
      };

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      microphone.current = stream;
      stream.getTracks().forEach((track) => peer.addTrack(track, stream));

      const events = peer.createDataChannel("oai-events");
      channel.current = events;
      events.onmessage = (event) => void handleEvent(event.data as string);

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const answer = await fetch(REALTIME_URL, {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: `Bearer ${session.client_secret}`, "Content-Type": "application/sdp" },
      });
      if (!answer.ok) throw new Error(`Səs bağlantısı alınmadı (${answer.status})`);
      await peer.setRemoteDescription({ type: "answer", sdp: await answer.text() });

      resetIdleTimer();
      setState("live");
    } catch (error) {
      stop();
      onError(error instanceof Error ? error.message : "Mikrofon açıla bilmədi");
    }
  }

  if (state === "off") {
    return (
      <button
        onClick={() => void start()}
        className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
        title="Səslə danış"
      >
        🎙 Səs
      </button>
    );
  }

  return (
    <button
      onClick={stop}
      className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
      title="Səsi bitir"
    >
      {state === "connecting" ? "Qoşulur…" : speaking ? "◼ Danışır…" : "◼ Dinləyir"}
    </button>
  );
}
