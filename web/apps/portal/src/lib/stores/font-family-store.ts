import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "ds-font"; // must match the inline anti-flash script in layout.tsx
export type FontFamily = "plex" | "inter" | "grotesk";

interface FontFamilyState {
  font: FontFamily;
  setFont: (font: FontFamily) => void;
}

export const useFontFamilyStore = create<FontFamilyState>()(
  persist(
    (set) => ({
      font: "inter",
      setFont: (font) => set({ font }),
    }),
    { name: STORAGE_KEY },
  ),
);
