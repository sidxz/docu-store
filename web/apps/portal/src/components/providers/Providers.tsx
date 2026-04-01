"use client";

import { AuthzProvider } from "@sentinel-auth/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { PrimeReactProvider } from "primereact/api";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { SentinelAuthz } from "@sentinel-auth/js";

import { getAuthzClient } from "@/lib/authz-client";
import { apiClient, setApiBaseUrl } from "@docu-store/api-client";
import { authMiddleware } from "@/lib/api-auth-middleware";
import { getQueryClient } from "@/lib/query-client";
import {
  AppConfigProvider,
  fetchAppConfig,
  type AppConfig,
} from "@/lib/app-config";
import { _setApiUrl } from "@/lib/constants";

import { ThemeProvider } from "./ThemeProvider";

// ripple: true enables PrimeReact's touch-feedback ripple animation on buttons
const primeReactConfig = {
  ripple: true,
};

/**
 * Root client-side provider tree.
 *
 * On mount, fetches runtime config from /api/config (enables universal
 * Docker images without build-time NEXT_PUBLIC_* vars), then initializes
 * the auth client and API client with the runtime URLs.
 *
 * Order matters:
 *  1. AppConfigProvider   — Runtime config context (outermost)
 *  2. AuthzProvider       — Sentinel auth context
 *  3. QueryClientProvider — TanStack Query
 *  4. PrimeReactProvider  — PrimeReact context (ripple, locale, etc.)
 *  5. ThemeProvider       — Injects the PrimeReact theme CSS link
 */
export function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();
  const clientRef = useRef<SentinelAuthz | null>(null);
  const configRef = useRef<AppConfig | null>(null);
  const middlewareApplied = useRef(false);
  const [mounted, setMounted] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchAppConfig()
      .then((config) => {
        if (cancelled) return;

        // Reconfigure singletons with runtime URLs
        setApiBaseUrl(config.apiUrl);
        _setApiUrl(config.apiUrl);

        clientRef.current = getAuthzClient(config);
        configRef.current = config;

        apiClient.use(authMiddleware);
        middlewareApplied.current = true;
        setMounted(true);
      })
      .catch((err) => {
        if (cancelled) return;
        setConfigError(
          err instanceof Error ? err.message : "Failed to load app configuration",
        );
      });

    return () => {
      cancelled = true;
      if (middlewareApplied.current) {
        apiClient.eject(authMiddleware);
        middlewareApplied.current = false;
      }
    };
  }, []);

  if (configError) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
        <div style={{ textAlign: "center", maxWidth: 420 }}>
          <h2 style={{ marginBottom: 8 }}>Configuration Error</h2>
          <p style={{ color: "#666", marginBottom: 16 }}>{configError}</p>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: "8px 20px", cursor: "pointer", borderRadius: 6, border: "1px solid #ccc", background: "#fff" }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!mounted || !configRef.current) return null;

  return (
    <AppConfigProvider config={configRef.current}>
      <AuthzProvider client={clientRef.current!}>
        <QueryClientProvider client={queryClient}>
          <PrimeReactProvider value={primeReactConfig}>
            <ThemeProvider>{children}</ThemeProvider>
          </PrimeReactProvider>
        </QueryClientProvider>
      </AuthzProvider>
    </AppConfigProvider>
  );
}
