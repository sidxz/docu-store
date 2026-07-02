import { create } from "zustand";
import { persist } from "zustand/middleware";
import { trackEvent } from "@/lib/analytics";

// localStorage key — must match the key read by the inline anti-flash script
// in app/layout.tsx, which runs before React hydrates.
const STORAGE_KEY = "ds-font-scale";

// Percent of the browser's default font-size (100 = browser default). Relative
// (not absolute px) so a user who raised their browser font-size for
// accessibility keeps that baseline; this scales on top of it.
export const FONT_SCALE_MIN = 85;
export const FONT_SCALE_MAX = 130;
export const FONT_SCALE_STEP = 5;
export const FONT_SCALE_DEFAULT = 100;

interface FontScaleState {
  scale: number;
  setScale: (scale: number) => void;
  reset: () => void;
}

export const useFontScaleStore = create<FontScaleState>()(
  persist(
    (set) => ({
      scale: FONT_SCALE_DEFAULT,
      setScale: (scale) => {
        const clamped = Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, scale));
        trackEvent("font_scale_changed", { scale: clamped });
        set({ scale: clamped });
      },
      reset: () => set({ scale: FONT_SCALE_DEFAULT }),
    }),
    { name: STORAGE_KEY },
  ),
);
