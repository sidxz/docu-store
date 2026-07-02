"use client";

import { useEffect, type ReactNode } from "react";

import { useThemeStore } from "@/lib/stores/theme-store";

/** Applies the persisted theme as a data-theme attribute (tokens flip via CSS). */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return <>{children}</>;
}
