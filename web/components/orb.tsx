"use client";

import { useEffect, useRef } from "react";

type Props = {
  // Loudness 0..1, read every frame: the user's microphone and the assistant's voice.
  inputLevel: () => number;
  outputLevel: () => number;
  live: boolean;
  thinking: boolean;
};

type RGB = [number, number, number];

const IDLE: RGB = [120, 150, 210];
const USER: RGB = [255, 48, 72]; // red while you speak
const ASSISTANT: RGB = [40, 235, 140]; // green while it speaks
const THINKING: RGB = [170, 140, 255];
const SPEAKING_THRESHOLD = 0.06;
const LAYERS = 6;
const POINTS = 160;

const mix = (a: number, b: number, t: number) => a + (b - a) * t;

export function Orb({ inputLevel, outputLevel, live, thinking }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  // Read inside the animation loop without restarting it on every render.
  const props = useRef({ inputLevel, outputLevel, live, thinking });
  useEffect(() => {
    props.current = { inputLevel, outputLevel, live, thinking };
  });

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    let frame = 0;
    let input = 0;
    let output = 0;
    let color: RGB = [...IDLE];

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      element.width = element.clientWidth * ratio;
      element.height = element.clientHeight * ratio;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);

    const draw = (now: number) => {
      const t = now / 1000;
      const { inputLevel, outputLevel, live, thinking } = props.current;
      input = mix(input, inputLevel(), 0.25);
      output = mix(output, outputLevel(), 0.25);

      // The assistant's voice wins: the microphone also hears the speakers a little.
      const target =
        output > SPEAKING_THRESHOLD ? ASSISTANT : input > SPEAKING_THRESHOLD ? USER : thinking ? THINKING : IDLE;
      color = color.map((channel, i) => mix(channel, target[i], 0.08)) as RGB;
      const energy = Math.max(input, output, thinking ? 0.18 + 0.08 * Math.sin(t * 4) : 0);
      const breathing = 0.03 * Math.sin(t * 1.3);

      const { width, height } = element;
      const cx = width / 2;
      const cy = height / 2;
      const base = Math.min(width, height) * (live ? 0.26 : 0.22) * (1 + breathing + energy * 0.25);
      const [r, g, b] = color.map(Math.round);

      context.clearRect(0, 0, width, height);
      context.globalCompositeOperation = "lighter";

      // Outer halo.
      const halo = context.createRadialGradient(cx, cy, base * 0.4, cx, cy, base * 2.2);
      halo.addColorStop(0, `rgba(${r},${g},${b},${0.18 + energy * 0.25})`);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      context.fillStyle = halo;
      context.fillRect(0, 0, width, height);

      // Layered, slowly twisting blobs: each layer warps with its own frequencies.
      for (let layer = 0; layer < LAYERS; layer++) {
        const phase = layer * 1.7;
        const speed = 0.4 + layer * 0.15;
        const wobble = base * (0.04 + energy * 0.35) * (1 - layer / (LAYERS * 1.5));
        context.beginPath();
        for (let i = 0; i <= POINTS; i++) {
          const angle = (i / POINTS) * Math.PI * 2;
          const offset =
            Math.sin(angle * 3 + t * speed + phase) * 0.5 +
            Math.sin(angle * 5 - t * speed * 1.3 + phase * 2) * 0.3 +
            Math.sin(angle * 9 + t * speed * 2.1 - phase) * 0.2 * (0.3 + energy);
          const radius = base * (1 - layer * 0.08) + wobble * offset;
          const x = cx + Math.cos(angle + t * 0.1 * (layer % 2 ? 1 : -1)) * radius;
          const y = cy + Math.sin(angle + t * 0.1 * (layer % 2 ? 1 : -1)) * radius;
          if (i === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        }
        context.closePath();
        const fill = context.createRadialGradient(cx, cy, 0, cx, cy, base * 1.2);
        fill.addColorStop(0, `rgba(${r},${g},${b},${0.1 + energy * 0.08})`);
        fill.addColorStop(1, `rgba(${r},${g},${b},0.02)`);
        context.fillStyle = fill;
        context.fill();
        context.lineWidth = Math.max(1, base * 0.006);
        context.strokeStyle = `rgba(${Math.min(255, r + 60)},${Math.min(255, g + 60)},${Math.min(255, b + 60)},${0.25 + energy * 0.5})`;
        context.stroke();
      }

      // Bright core.
      const core = context.createRadialGradient(cx, cy, 0, cx, cy, base * 0.55);
      core.addColorStop(0, `rgba(255,255,255,${0.25 + energy * 0.5})`);
      core.addColorStop(0.4, `rgba(${r},${g},${b},${0.3 + energy * 0.4})`);
      core.addColorStop(1, "rgba(0,0,0,0)");
      context.fillStyle = core;
      context.beginPath();
      context.arc(cx, cy, base * 0.55, 0, Math.PI * 2);
      context.fill();

      context.globalCompositeOperation = "source-over";
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvas} className="h-full w-full" aria-hidden />;
}
