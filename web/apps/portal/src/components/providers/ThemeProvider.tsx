"use client";

import { useEffect, type ReactNode } from "react";

import { useThemeStore } from "@/lib/stores/theme-store";

const THEME_CSS_MAP = {
  light: "/primereact-themes/lara-light-teal/theme.css",
  dark: "/primereact-themes/lara-dark-teal/theme.css",
} as const;

const LINK_ID = "primereact-theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    // Set data-theme attribute for CSS token switching
    document.documentElement.setAttribute("data-theme", theme);

    // Load PrimeReact theme CSS dynamically
    let link = document.getElementById(LINK_ID) as HTMLLinkElement | null;
    if (!link) {
      link = document.createElement("link");
      link.id = LINK_ID;
      link.rel = "stylesheet";
      document.head.appendChild(link);
    }
    link.href = THEME_CSS_MAP[theme];
  }, [theme]);

  return <>{children}</>;
}
