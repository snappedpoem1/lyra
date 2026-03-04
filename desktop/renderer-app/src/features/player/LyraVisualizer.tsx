import { useEffect, useRef } from "react";
import { usePlayerStore } from "@/stores/playerStore";

export function LyraVisualizer() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frame = usePlayerStore((state) => state.frame);
  const track = usePlayerStore((state) => state.track);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    const width = canvas.width;
    const height = canvas.height;
    const centerY = height * 0.52;
    const energy = frame.energy;
    const tension = frame.tension;
    const movement = frame.movement;

    context.clearRect(0, 0, width, height);
    const base = context.createLinearGradient(0, 0, 0, height);
    base.addColorStop(0, "rgba(7, 7, 7, 0.15)");
    base.addColorStop(0.45, "rgba(22, 14, 10, 0.92)");
    base.addColorStop(1, "rgba(4, 4, 4, 0.98)");
    context.fillStyle = base;
    context.fillRect(0, 0, width, height);

    const bloom = context.createRadialGradient(width * 0.5, centerY * 0.76, 12, width * 0.5, centerY * 0.76, width * 0.6);
    bloom.addColorStop(0, `rgba(255, 198, 127, ${0.14 + energy * 0.45})`);
    bloom.addColorStop(0.45, `rgba(219, 112, 42, ${0.08 + tension * 0.24})`);
    bloom.addColorStop(1, "rgba(0, 0, 0, 0)");
    context.fillStyle = bloom;
    context.fillRect(0, 0, width, height);

    context.save();
    context.globalCompositeOperation = "screen";
    frame.spectrum.forEach((value, index) => {
      const x = (index / frame.spectrum.length) * width;
      const barWidth = width / frame.spectrum.length - 1.5;
      const barHeight = 18 + value * height * (0.24 + energy * 0.34);
      const y = height - barHeight;
      const barGlow = context.createLinearGradient(0, y, 0, height);
      barGlow.addColorStop(0, `rgba(255, 220, 170, ${0.32 + value * 0.3})`);
      barGlow.addColorStop(1, `rgba(255, 128, 44, ${0.04 + value * 0.16})`);
      context.fillStyle = barGlow;
      context.fillRect(x, y, barWidth, barHeight);
    });
    context.restore();

    for (let layer = 0; layer < 3; layer += 1) {
      const alpha = 0.28 - layer * 0.08;
      const offset = layer * 9;
      context.strokeStyle = `rgba(255, 214, 158, ${alpha})`;
      context.lineWidth = 1.5 + layer * 0.8;
      context.beginPath();
      frame.waveform.forEach((value, index) => {
        const x = (index / (frame.waveform.length - 1)) * width;
        const y = centerY + (value - 0.5) * height * (0.48 - layer * 0.1) - offset;
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      });
      context.stroke();
    }

    context.strokeStyle = "rgba(255, 228, 188, 0.96)";
    context.lineWidth = 2.2;
    context.beginPath();
    frame.waveform.forEach((value, index) => {
      const x = (index / (frame.waveform.length - 1)) * width;
      const y = centerY + (value - 0.5) * height * 0.34;
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();

    const particleCount = 18;
    for (let index = 0; index < particleCount; index += 1) {
      const waveValue = frame.waveform[index % frame.waveform.length] ?? 0.5;
      const sx = ((index * 37) % width) + (movement * 10);
      const sy = centerY - 30 - (index % 5) * 18 - waveValue * 40;
      const radius = 1.5 + ((index + 1) % 4) * 0.9 + energy * 3.5;
      context.beginPath();
      context.fillStyle = `rgba(255, 225, 188, ${0.08 + ((index % 3) * 0.03) + energy * 0.16})`;
      context.arc(sx, sy, radius, 0, Math.PI * 2);
      context.fill();
    }

    const titleGlow = context.createLinearGradient(0, 0, width, 0);
    titleGlow.addColorStop(0, "rgba(255,255,255,0)");
    titleGlow.addColorStop(0.4, "rgba(255,228,188,0.22)");
    titleGlow.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = titleGlow;
    context.fillRect(width * 0.12, 12, width * 0.76, 2);

    context.fillStyle = "rgba(247, 222, 192, 0.7)";
    context.font = "12px Bahnschrift";
    context.fillText(track?.title ?? "Lyra signal waiting", 16, 20);
  }, [frame, track]);

  return <canvas ref={canvasRef} className="visualizer-canvas" width={420} height={260} />;
}
