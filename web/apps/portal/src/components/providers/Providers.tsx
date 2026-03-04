"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { PrimeReactProvider } from "primereact/api";
import type { ReactNode } from "react";

import { getQueryClient } from "@/lib/query-client";

import { ThemeProvider } from "./ThemeProvider";

// ripple: true enables PrimeReact's touch-feedback ripple animation on buttons
const primeReactConfig = {
  ripple: true,
};

/**
 * Root client-side provider tree.
 *
 * Order matters:
 *  1. QueryClientProvider — TanStack Query must wrap everything that uses useQuery/useMutation
 *  2. PrimeReactProvider  — PrimeReact context (ripple, locale, etc.)
 *  3. ThemeProvider       — Injects the PrimeReact theme CSS link and sets data-theme on <html>
 */
export function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <PrimeReactProvider value={primeReactConfig}>
        <ThemeProvider>{children}</ThemeProvider>
      </PrimeReactProvider>
    </QueryClientProvider>
  );
}
