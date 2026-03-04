"use client";

import { useEffect, type ReactNode } from "react";

import { useThemeStore } from "@/lib/stores/theme-store";

// PrimeReact theme CSS files are copied from node_modules at install time
// via scripts/copy-primereact-themes.mjs. Lara Blue is used (not Teal —
// see upstream bug: primefaces/primereact-sass-theme#75).
const THEME_CSS_MAP = {
  light: "/primereact-themes/lara-light-blue/theme.css",
  dark: "/primereact-themes/lara-dark-blue/theme.css",
} as const;

// Stable <link> element ID so we swap href in-place rather than appending
// a new stylesheet on each theme switch (avoids flash of unstyled content).
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
