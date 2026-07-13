"use client";

import { useEffect, useRef } from "react";

interface ShapeGridProps {
  cellSize?: number;
  glowRadius?: number;
}

// Cool half of the docustore.io spectrum: cyan → blue → app accent.
// First tuple element is the stop position as a fraction of viewport width.
const STOPS: Array<[number, number, number, number]> = [
  [0.05, 0x37, 0xd7, 0xfa],
  [0.55, 0x4b, 0x72, 0xfe],
  [1.0, 0x3b, 0x82, 0xf6],
];

function spectrumAt(t: number): [number, number, number] {
  if (t <= STOPS[0][0]) return [STOPS[0][1], STOPS[0][2], STOPS[0][3]];
  for (let i = 0; i < STOPS.length - 1; i++) {
    const a = STOPS[i];
    const b = STOPS[i + 1];
    if (t <= b[0]) {
      const f = (t - a[0]) / (b[0] - a[0]);
      return [
        Math.round(a[1] + (b[1] - a[1]) * f),
        Math.round(a[2] + (b[2] - a[2]) * f),
        Math.round(a[3] + (b[3] - a[3]) * f),
      ];
    }
  }
  const last = STOPS[STOPS.length - 1];
  return [last[1], last[2], last[3]];
}

export function ShapeGrid({ cellSize = 48, glowRadius = 200 }: ShapeGridProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const mouse = { x: -9999, y: -9999 };
    let frame = 0;
    let t = 0;

    const resize = () => {
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const h = cellSize * 0.866;

    const drawFrame = () => {
      const w = window.innerWidth;
      const ht = window.innerHeight;

      ctx.clearRect(0, 0, w, ht);
      ctx.lineWidth = 0.6;

      const rows = Math.ceil(ht / h) + 2;
      const cols = Math.ceil(w / cellSize) + 2;

      for (let row = -1; row < rows; row++) {
        for (let col = -1; col < cols; col++) {
          const x = col * cellSize;
          const y = row * h;

          // Up-pointing triangle
          drawTriangle(
            ctx,
            x, y + h,
            x + cellSize / 2, y,
            x + cellSize, y + h,
            mouse,
            glowRadius,
            t, col, row,
            w,
          );

          // Down-pointing triangle
          drawTriangle(
            ctx,
            x + cellSize / 2, y,
            x + cellSize, y + h,
            x + cellSize * 1.5, y,
            mouse,
            glowRadius,
            t, col + 0.5, row + 0.5,
            w,
          );
        }
      }
    };

    const render = () => {
      t += 0.004;
      drawFrame();
      frame = requestAnimationFrame(render);
    };

    const onMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    const onMouseLeave = () => {
      mouse.x = -9999;
      mouse.y = -9999;
    };
    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        mouse.x = e.touches[0].clientX;
        mouse.y = e.touches[0].clientY;
      }
    };
    const onTouchEnd = () => {
      mouse.x = -9999;
      mouse.y = -9999;
    };

    resize();

    // Reduced motion: draw the resting lattice once — no loop, no spotlight.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      drawFrame();
      const onStaticResize = () => {
        resize();
        drawFrame();
      };
      window.addEventListener("resize", onStaticResize);
      return () => window.removeEventListener("resize", onStaticResize);
    }

    render();

    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseleave", onMouseLeave);
    window.addEventListener("touchmove", onTouchMove);
    window.addEventListener("touchend", onTouchEnd);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseleave", onMouseLeave);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [cellSize, glowRadius]);

  return <canvas ref={canvasRef} className="pointer-events-none fixed inset-0" />;
}

function drawTriangle(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number,
  x2: number, y2: number,
  x3: number, y3: number,
  mouse: { x: number; y: number },
  glowRadius: number,
  t: number,
  col: number, row: number,
  viewportWidth: number,
) {
  const cx = (x1 + x2 + x3) / 3;
  const cy = (y1 + y2 + y3) / 3;

  const dist = Math.hypot(cx - mouse.x, cy - mouse.y);

  // Ambient sine shimmer — resting lattice
  const wave = Math.sin(t + col * 0.4 + row * 0.6) * 0.02;
  const base = 0.07 + wave;

  // Mouse proximity (quadratic falloff)
  const hover = dist < glowRadius ? (1 - dist / glowRadius) ** 2 : 0;

  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.lineTo(x3, y3);
  ctx.closePath();

  if (hover > 0.01) {
    // Spotlight reveals the spectrum color for this x-position
    const [r, g, b] = spectrumAt(cx / viewportWidth);
    if (hover > 0.03) {
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${hover * 0.16})`;
      ctx.fill();
    }
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${Math.min(1, base + hover * 0.85)})`;
  } else {
    // slate-500 — blue-leaning gray so the resting lattice reads cool
    ctx.strokeStyle = `rgba(100, 116, 139, ${base})`;
  }
  ctx.stroke();
}
