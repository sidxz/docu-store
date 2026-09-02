"use client";

import { createContext, useContext, type ReactNode } from "react";

export interface AppConfig {
  apiUrl: string;
  appUrl: string;
  duarUrl: string;
  /** Duar SELF_SERVE_ENABLED mirror — shows sign-up / invite links (public instances only). */
  selfServeEnabled: boolean;
  /** Backend LITERATURE_ENABLED mirror — offers the Literature Search surface at all. */
  literatureEnabled: boolean;
  googleClientId: string;
  githubClientId: string;
  entraIdClientId: string;
  umamiUrl: string;
  umamiWebsiteId: string;
}

const defaultConfig: AppConfig = {
  apiUrl: "http://localhost:8000",
  appUrl: "http://localhost:15000",
  duarUrl: "http://localhost:9003",
  selfServeEnabled: false,
  literatureEnabled: false,
  googleClientId: "",
  githubClientId: "",
  entraIdClientId: "",
  umamiUrl: "",
  umamiWebsiteId: "",
};

const AppConfigContext = createContext<AppConfig>(defaultConfig);

export function AppConfigProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: ReactNode;
}) {
  return (
    <AppConfigContext.Provider value={config}>
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig(): AppConfig {
  return useContext(AppConfigContext);
}

/**
 * Fetch runtime config from the server endpoint.
 * Falls back to NEXT_PUBLIC_* env vars for backwards compatibility
 * (dev without Docker), then to defaults.
 */
export async function fetchAppConfig(): Promise<AppConfig> {
  try {
    const res = await fetch("/api/config");
    if (res.ok) return await res.json();
  } catch {
    // Server not reachable (SSR, tests) — fall through to env vars
  }

  // Fallback: NEXT_PUBLIC_* env vars (build-time, for dev without Docker)
  return {
    apiUrl: process.env.NEXT_PUBLIC_API_URL ?? defaultConfig.apiUrl,
    appUrl: process.env.NEXT_PUBLIC_APP_URL ?? defaultConfig.appUrl,
    duarUrl:
      process.env.NEXT_PUBLIC_DUAR_URL ?? defaultConfig.duarUrl,
    selfServeEnabled: process.env.NEXT_PUBLIC_SELF_SERVE_ENABLED === "true",
    literatureEnabled: process.env.NEXT_PUBLIC_LITERATURE_ENABLED === "true",
    googleClientId:
      process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? defaultConfig.googleClientId,
    githubClientId:
      process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID ?? defaultConfig.githubClientId,
    entraIdClientId:
      process.env.NEXT_PUBLIC_ENTRA_ID_CLIENT_ID ??
      defaultConfig.entraIdClientId,
    umamiUrl: process.env.NEXT_PUBLIC_UMAMI_URL ?? defaultConfig.umamiUrl,
    umamiWebsiteId:
      process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID ?? defaultConfig.umamiWebsiteId,
  };
}
