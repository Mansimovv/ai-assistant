"use client";

import { useEffect, useRef, useState } from "react";

// "Hey Jarvis" as Chrome's Azerbaijani recognizer tends to write it: Jarvis, Carvis,
// Cərvis, Cervis, Ceyrvis, Jarviz... plus whatever was said right after it.
const WAKE = /(?:^|\s)(?:hey|hay|ey|hei|hi|həy)?[\s,]*[jcçd][aəe]y?r?v[iıey]?[sz][\s,.!?]*/i;

// Two claps: each is a sudden loud click that dies away quickly (speech and music
// rise and stay loud), and the second follows the first within this window.
const CLAP_GAP_MIN_MS = 120;
const CLAP_GAP_MAX_MS = 900;

// Runs on the audio thread, so it keeps working when the tab is in the background.
const CLAP_WORKLET = `
class ClapDetector extends AudioWorkletProcessor {
  constructor() {
    super();
    this.background = 0.01;
    this.candidate = null; // { peak, age, tail }
    this.refractory = 0;
  }
  process(inputs) {
    const samples = inputs[0] && inputs[0][0];
    if (!samples) return true;
    let peak = 0;
    for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
    const blockMs = (samples.length / sampleRate) * 1000;

    if (this.candidate) {
      this.candidate.age += blockMs;
      if (this.candidate.age > 40) this.candidate.tail = Math.max(this.candidate.tail, peak);
      if (this.candidate.age >= 120) {
        // A clap has gone quiet again by now; a word or a bang that lingers has not.
        if (this.candidate.tail < this.candidate.peak * 0.35) this.port.postMessage("clap");
        this.candidate = null;
        this.refractory = 80;
      }
    } else if (this.refractory > 0) {
      this.refractory -= blockMs;
    } else if (peak > 0.3 && peak > this.background * 8) {
      this.candidate = { peak, age: 0, tail: 0 };
    }
    this.background = this.background * 0.995 + peak * 0.005;
    return true;
  }
}
registerProcessor("clap-detector", ClapDetector);
`;

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult:
    | ((event: {
        resultIndex: number;
        results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
};

type RecognitionConstructor = new () => Recognition;

function recognitionClass(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

type Options = {
  // `command` is what followed "Hey Jarvis" ("" after a double clap).
  onWake: (command: string) => void;
  // What the recognizer is hearing, so the user can see why it did or did not wake.
  onHeard: (text: string) => void;
  onError: (message: string) => void;
};

/**
 * While `active`, wakes on "Hey Jarvis" (the browser's speech recognition, Chrome)
 * or on two claps (a detector on the raw microphone). "Hey Jarvis, VS Code-u aç"
 * works in one breath.
 */
export function useWakeWord(active: boolean, { onWake, onHeard, onError }: Options) {
  const [supported] = useState(() => recognitionClass() !== null);
  const callbacks = useRef({ onWake, onHeard, onError });
  useEffect(() => {
    callbacks.current = { onWake, onHeard, onError };
  });

  // "Hey Jarvis"
  useEffect(() => {
    const Recognition = recognitionClass();
    if (!active || !Recognition) return;

    let stopped = false;
    const recognition = new Recognition();
    recognition.lang = "az-AZ";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;
        callbacks.current.onHeard(text);
        if (!result.isFinal) continue;
        const match = WAKE.exec(text);
        if (match) {
          stopped = true;
          recognition.stop();
          callbacks.current.onWake(text.slice(match.index + match[0].length).trim());
          return;
        }
      }
    };
    // Chrome ends a session after a silence or a minute; keep listening.
    recognition.onend = () => {
      if (!stopped) recognition.start();
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        stopped = true;
        callbacks.current.onError("Mikrofona icazə yoxdur — brauzerdə mikrofonu icazələ");
      }
    };

    recognition.start();
    return () => {
      stopped = true;
      recognition.onend = null;
      recognition.stop();
    };
  }, [active]);

  // Two claps
  useEffect(() => {
    if (!active) return;

    let cancelled = false;
    let context: AudioContext | null = null;
    let stream: MediaStream | null = null;
    let lastClap = 0;

    (async () => {
      // Raw microphone: noise suppression and auto gain would flatten the claps.
      const microphone = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      if (cancelled) {
        microphone.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = microphone;
      context = new AudioContext();
      const workletUrl = URL.createObjectURL(new Blob([CLAP_WORKLET], { type: "application/javascript" }));
      await context.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);
      if (cancelled) return;

      const detector = new AudioWorkletNode(context, "clap-detector");
      detector.port.onmessage = () => {
        const now = performance.now();
        const gap = now - lastClap;
        lastClap = now;
        if (gap >= CLAP_GAP_MIN_MS && gap <= CLAP_GAP_MAX_MS) {
          lastClap = 0;
          callbacks.current.onHeard("👏👏");
          callbacks.current.onWake("");
        }
      };
      context.createMediaStreamSource(stream).connect(detector);
    })().catch(() => undefined);

    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
      void context?.close().catch(() => undefined);
    };
  }, [active]);

  return supported;
}
