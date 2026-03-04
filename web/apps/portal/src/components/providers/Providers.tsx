"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { PrimeReactProvider } from "primereact/api";
import type { ReactNode } from "react";

import { getQueryClient } from "@/lib/query-client";

const primeReactConfig = {
  ripple: true,
};

export function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <PrimeReactProvider value={primeReactConfig}>
        {children}
      </PrimeReactProvider>
    </QueryClientProvider>
  );
}
