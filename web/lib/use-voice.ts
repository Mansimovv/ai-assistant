"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { createVoiceSession, recordVoiceTurn, runVoiceTool, speakSentence, type PendingAction } from "@/lib/api";

// The browser streams audio straight to OpenAI (that is what keeps it fast), using a
// short-lived credential minted by our backend. Tool calls still go through the backend.
const REALTIME_URL = "https://api.openai.com/v1/realtime/calls";
// Cost guard: an open microphone costs money, so a silent session closes itself.
const IDLE_TIMEOUT_MS = 300_000;
// After "go to sleep", let the goodbye finish playing before hanging up.
const SLEEP_FALLBACK_MS = 6_000;
// One wake, one exchange: once it has answered and nothing is running, the session
// stays open this long for a follow-up, then closes. Audio is billed while it is open.
const FOLLOW_UP_MS = 8_000;
// With the native voice, text is spoken sentence by sentence as it streams in.
// Cut at the first sentence end after at least 12 characters, so "Bəli." joins the next one.
const SENTENCE = /^([\s\S]{12,}?[.!?…:;\n])\s+/;

export type VoiceState = "off" | "connecting" | "live";

type Options = {
  onTranscript: (role: "user" | "assistant", text: string) => void;
  onPending: (pending: PendingAction[]) => void;
  onActed: () => void;
  onError: (message: string) => void;
};

// Loudness of whatever feeds the analyser, 0..1, read once per animation frame by the orb.
function analyserFor(context: AudioContext, stream: MediaStream): AnalyserNode {
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  context.createMediaStreamSource(stream).connect(analyser);
  return analyser;
}

function meter(analyser: AnalyserNode): () => number {
  const samples = new Uint8Array(analyser.fftSize);
  return () => {
    analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (const sample of samples) sum += ((sample - 128) / 128) ** 2;
    return Math.min(1, Math.sqrt(sum / samples.length) * 5);
  };
}

export function useVoice({ onTranscript, onPending, onActed, onError }: Options) {
  const [state, setState] = useState<VoiceState>("off");
  const connection = useRef<RTCPeerConnection | null>(null);
  const channel = useRef<RTCDataChannel | null>(null);
  const microphone = useRef<MediaStream | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sleeping = useRef(false);
  const inputMeter = useRef<() => number>(() => 0);
  const outputMeter = useRef<() => number>(() => 0);
  // Native voice playback: sentences play in order; a new generation drops the old ones.
  const native = useRef(false);
  const speakers = useRef<AnalyserNode | null>(null);
  const textBuffer = useRef("");
  const queue = useRef<Promise<void>>(Promise.resolve());
  const queued = useRef(0);
  const generation = useRef(0);
  const playing = useRef<AudioBufferSourceNode | null>(null);
  const responding = useRef(false);
  const audioPlaying = useRef(false);
  const toolsRunning = useRef(0);
  const followUpTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    if (followUpTimer.current) clearTimeout(followUpTimer.current);
    audioPlaying.current = false;
    toolsRunning.current = 0;
    responding.current = false;
    sleeping.current = false;
    channel.current?.close();
    connection.current?.close();
    microphone.current?.getTracks().forEach((track) => track.stop());
    void audio.current?.close().catch(() => undefined);
    channel.current = null;
    connection.current = null;
    microphone.current = null;
    audio.current = null;
    inputMeter.current = () => 0;
    outputMeter.current = () => 0;
    generation.current += 1;
    playing.current = null;
    speakers.current = null;
    textBuffer.current = "";
    queued.current = 0;
    setState("off");
  }, []);

  useEffect(() => stop, [stop]);

  function speak(text: string) {
    const context = audio.current;
    const output = speakers.current;
    if (!context || !output || !text.trim()) return;
    const turn = generation.current;
    // Fetch now, so the next sentence is ready while this one plays.
    const sound = speakSentence(text).then((data) => context.decodeAudioData(data));
    queued.current += 1;
    queue.current = queue.current
      .then(async () => {
        const buffer = await sound.catch(() => null);
        if (!buffer || turn !== generation.current) return;
        await new Promise<void>((done) => {
          const source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(output);
          source.onended = () => done();
          playing.current = source;
          source.start();
        });
      })
      .finally(() => {
        queued.current -= 1;
        if (queued.current === 0 && sleeping.current) stop();
        else if (queued.current === 0) waitForFollowUp();
      });
  }

  // Speak every complete sentence in the buffer; `flush` speaks the rest too.
  function speakBuffered(flush: boolean) {
    let match;
    while ((match = SENTENCE.exec(textBuffer.current))) {
      speak(match[1]);
      textBuffer.current = textBuffer.current.slice(match[0].length);
    }
    if (flush) {
      speak(textBuffer.current);
      textBuffer.current = "";
    }
  }

  // The user started talking: stop speaking at once, like a person would.
  function interrupt() {
    generation.current += 1;
    textBuffer.current = "";
    playing.current?.stop();
    playing.current = null;
    if (responding.current) channel.current?.send(JSON.stringify({ type: "response.cancel" }));
  }

  // Answered, silent, nothing running: give the user a moment, then go back to sleep.
  function waitForFollowUp() {
    const speaking = native.current ? queued.current > 0 : audioPlaying.current;
    if (responding.current || toolsRunning.current > 0 || speaking) return;
    cancelFollowUp();
    followUpTimer.current = setTimeout(stop, FOLLOW_UP_MS);
  }

  function cancelFollowUp() {
    if (followUpTimer.current) clearTimeout(followUpTimer.current);
    followUpTimer.current = null;
  }

  function resetIdleTimer() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(stop, IDLE_TIMEOUT_MS);
  }

  async function handleEvent(raw: string) {
    const event = JSON.parse(raw) as {
      type: string;
      transcript?: string;
      delta?: string;
      text?: string;
      name?: string;
      call_id?: string;
      arguments?: string;
      error?: { message?: string };
    };

    switch (event.type) {
      case "input_audio_buffer.speech_started":
        resetIdleTimer();
        cancelFollowUp();
        if (native.current) interrupt();
        break;

      case "response.created":
        responding.current = true;
        cancelFollowUp();
        break;

      case "response.done":
        responding.current = false;
        waitForFollowUp();
        break;

      case "output_audio_buffer.started":
        audioPlaying.current = true;
        cancelFollowUp();
        break;

      case "response.output_text.delta":
        textBuffer.current += event.delta ?? "";
        speakBuffered(false);
        break;

      case "response.output_text.done":
        resetIdleTimer();
        speakBuffered(true);
        if (event.text?.trim()) {
          onTranscript("assistant", event.text);
          void recordVoiceTurn("assistant", event.text).catch(() => undefined);
        }
        break;

      case "conversation.item.input_audio_transcription.completed":
        if (event.transcript?.trim()) {
          onTranscript("user", event.transcript);
          void recordVoiceTurn("user", event.transcript).catch(() => undefined);
        }
        break;

      case "response.output_audio_transcript.done":
        resetIdleTimer();
        if (event.transcript?.trim()) {
          onTranscript("assistant", event.transcript);
          void recordVoiceTurn("assistant", event.transcript).catch(() => undefined);
        }
        break;

      case "response.function_call_arguments.done":
        resetIdleTimer();
        if (event.name === "go_to_sleep") {
          goToSleep(event.call_id ?? "");
        } else {
          await executeTool(event.name ?? "", event.call_id ?? "", event.arguments ?? "{}");
        }
        break;

      case "output_audio_buffer.stopped":
        audioPlaying.current = false;
        if (sleeping.current) stop();
        else waitForFollowUp();
        break;

      case "error":
        onError(event.error?.message ?? "Səs sessiyasında xəta");
        break;
    }
  }

  function goToSleep(callId: string) {
    sleeping.current = true;
    if (native.current && queued.current === 0) {
      setTimeout(stop, 500);
    }
    channel.current?.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: callId, output: JSON.stringify({ ok: true }) },
      }),
    );
    setTimeout(() => {
      if (sleeping.current) stop();
    }, SLEEP_FALLBACK_MS);
  }

  async function executeTool(name: string, callId: string, rawArguments: string) {
    let result: unknown;
    let pending: PendingAction[] = [];
    cancelFollowUp();
    toolsRunning.current += 1;
    try {
      const response = await runVoiceTool(name, JSON.parse(rawArguments || "{}") as Record<string, unknown>);
      result = response.result;
      pending = response.pending;
    } catch (error) {
      result = { ok: false, error: error instanceof Error ? error.message : "Əməliyyat alınmadı" };
    } finally {
      toolsRunning.current -= 1;
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

  // `command` is what was said right after "Hey Jarvis"; without one, it just answers.
  async function start(command?: string) {
    setState("connecting");
    try {
      const session = await createVoiceSession();
      const context = new AudioContext();
      audio.current = context;
      native.current = session.speech === "native";
      if (native.current) {
        const output = context.createAnalyser();
        output.fftSize = 512;
        output.connect(context.destination);
        speakers.current = output;
        outputMeter.current = meter(output);
      }

      const peer = new RTCPeerConnection();
      connection.current = peer;

      player.current ??= new Audio();
      player.current.autoplay = true;
      peer.ontrack = (event) => {
        const [remote] = event.streams;
        if (player.current) {
          player.current.srcObject = remote;
          void player.current.play().catch(() => undefined);
        }
        if (!native.current) outputMeter.current = meter(analyserFor(context, remote));
      };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      microphone.current = stream;
      stream.getTracks().forEach((track) => peer.addTrack(track, stream));
      inputMeter.current = meter(analyserFor(context, stream));

      const events = peer.createDataChannel("oai-events");
      channel.current = events;
      events.onmessage = (event) => void handleEvent(event.data as string);
      events.onopen = () => {
        if (command) {
          onTranscript("user", command);
          void recordVoiceTurn("user", command).catch(() => undefined);
          events.send(
            JSON.stringify({
              type: "conversation.item.create",
              item: { type: "message", role: "user", content: [{ type: "input_text", text: command }] },
            }),
          );
          events.send(JSON.stringify({ type: "response.create" }));
        } else {
          events.send(
            JSON.stringify({
              type: "response.create",
              response: { instructions: "You were just woken up. Answer in two or three words, addressing the owner by name, like 'Bəli, <name>?'." },
            }),
          );
        }
      };

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

  return {
    state,
    start,
    stop,
    inputLevel: () => inputMeter.current(),
    outputLevel: () => outputMeter.current(),
  };
}
