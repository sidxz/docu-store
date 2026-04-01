import { create } from "zustand";
import { persist } from "zustand/middleware";
import { trackEvent } from "@/lib/analytics";

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
        set((state) => {
          const newTheme = state.theme === "light" ? "dark" : "light";
          trackEvent("theme_toggled", { new_theme: newTheme });
          return { theme: newTheme };
        }),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: STORAGE_KEY,
    },
  ),
);
