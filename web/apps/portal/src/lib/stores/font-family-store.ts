import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "ds-font"; // must match the inline anti-flash script in layout.tsx
export type FontFamily = "plex" | "inter";

interface FontFamilyState {
  font: FontFamily;
  setFont: (font: FontFamily) => void;
  toggle: () => void;
}

export const useFontFamilyStore = create<FontFamilyState>()(
  persist(
    (set, get) => ({
      font: "plex",
      setFont: (font) => set({ font }),
      toggle: () => set({ font: get().font === "plex" ? "inter" : "plex" }),
    }),
    { name: STORAGE_KEY },
  ),
);
