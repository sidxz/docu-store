"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { authFetchJson, authFetch } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useSidebarStore } from "@/lib/stores/sidebar-store";
import { useScopeStore } from "@/lib/stores/scope-store";

interface ServerPreferences {
  theme: string;
  sidebar_collapsed: boolean;
  dev_mode: boolean;
  default_scope: string;
}

/**
 * Syncs Zustand localStorage stores with server-side user preferences.
 *
 * Strategy: optimistic local-first with background server sync.
 * - On mount: fetch server prefs, hydrate Zustand stores (once)
 * - On store change: debounced PATCH to server (1s idle)
 *
 * Zustand stores keep localStorage persistence for instant render.
 * This hook overlays cross-browser persistence on top.
 */
export function usePreferencesSync() {
  const { data: serverPrefs, isSuccess } = useQuery({
    queryKey: queryKeys.user.preferences(),
    queryFn: () => authFetchJson<ServerPreferences>("/user/preferences"),
    staleTime: Infinity,
    retry: 1,
  });

  // State (not ref) so subscription effect re-runs after hydration completes
  const [hydrated, setHydrated] = useState(false);
  // Guard: true while we're pushing server values into stores (skip echoing back)
  const syncing = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<Partial<ServerPreferences>>({});

  const flush = useCallback(() => {
    const changes = { ...pendingRef.current };
    pendingRef.current = {};
    if (Object.keys(changes).length === 0) return;
    authFetch("/user/preferences", {
      method: "PATCH",
      body: JSON.stringify(changes),
      headers: { "Content-Type": "application/json" },
    }).catch((err) => {
      if (process.env.NODE_ENV === "development") {
        console.warn("Preferences sync failed:", err);
      }
    });
  }, []);

  const scheduleFlush = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(flush, 1000);
  }, [flush]);

  // Step 1: Hydrate stores from server (once)
  useEffect(() => {
    if (isSuccess && serverPrefs && !hydrated) {
      syncing.current = true;
      const theme = serverPrefs.theme === "light" || serverPrefs.theme === "dark"
        ? serverPrefs.theme : "light";
      const scope = serverPrefs.default_scope === "workspace" || serverPrefs.default_scope === "private"
        ? serverPrefs.default_scope : "workspace";
      useThemeStore.getState().setTheme(theme);
      useDevModeStore.getState().setEnabled(serverPrefs.dev_mode);
      useSidebarStore.getState().setCollapsed(serverPrefs.sidebar_collapsed);
      useScopeStore.getState().setDefaultScope(scope);
      syncing.current = false;
      setHydrated(true);
    }
  }, [isSuccess, serverPrefs, hydrated]);

  // Step 2: Subscribe to store changes, sync to server.
  // Dependency on `hydrated` (state) ensures this re-runs once hydration completes.
  useEffect(() => {
    if (!hydrated) return;

    const unsubs = [
      useThemeStore.subscribe((s) => {
        if (syncing.current) return;
        pendingRef.current.theme = s.theme;
        scheduleFlush();
      }),
      useDevModeStore.subscribe((s) => {
        if (syncing.current) return;
        pendingRef.current.dev_mode = s.enabled;
        scheduleFlush();
      }),
      useSidebarStore.subscribe((s) => {
        if (syncing.current) return;
        pendingRef.current.sidebar_collapsed = s.collapsed;
        scheduleFlush();
      }),
      useScopeStore.subscribe((s) => {
        if (syncing.current) return;
        pendingRef.current.default_scope = s.defaultScope;
        scheduleFlush();
      }),
    ];

    return () => {
      unsubs.forEach((fn) => fn());
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        flush();
      }
    };
  }, [hydrated, scheduleFlush, flush]);
}
