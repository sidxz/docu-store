import { create } from "zustand";
import { persist } from "zustand/middleware";

// localStorage key — must match the key read by the inline anti-flash script
// in app/layout.tsx, which runs before React hydrates.
const STORAGE_KEY = "ds-theme";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "light",
      toggleTheme: () =>
        set((state) => ({ theme: state.theme === "light" ? "dark" : "light" })),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: STORAGE_KEY,
    },
  ),
);
