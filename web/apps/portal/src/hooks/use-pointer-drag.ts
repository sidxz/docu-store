"use client";

import { useCallback, useRef, useState } from "react";

/** Drag-to-move for dialogs (parity with PrimeReact Dialog `draggable`). */
export function usePointerDrag() {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const origin = useRef({ px: 0, py: 0, ox: 0, oy: 0 });

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      origin.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y };
      const onMove = (ev: PointerEvent) =>
        setOffset({
          x: origin.current.ox + ev.clientX - origin.current.px,
          y: origin.current.oy + ev.clientY - origin.current.py,
        });
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [offset],
  );

  const reset = useCallback(() => setOffset({ x: 0, y: 0 }), []);

  return {
    offset,
    onPointerDown,
    reset,
    style: { transform: `translate(${offset.x}px, ${offset.y}px)` } as React.CSSProperties,
  };
}
