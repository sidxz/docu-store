"use client";

import { useEffect, useState } from "react";
import type { RDKitModule } from "@rdkit/rdkit";

/**
 * Corrected RDKit loader signature. The upstream @rdkit/rdkit types
 * declare locateFile as `() => string`, but Emscripten actually passes
 * the filename: `(file: string) => string`.
 */
type RDKitInit = (options?: {
  locateFile?: (file: string) => string;
}) => Promise<RDKitModule>;

let rdkitPromise: Promise<RDKitModule> | null = null;
let rdkitInstance: RDKitModule | null = null;

function loadRDKit(): Promise<RDKitModule> {
  if (rdkitInstance) return Promise.resolve(rdkitInstance);
  if (rdkitPromise) return rdkitPromise;

  rdkitPromise = (async () => {
    const initRDKitModule = (await import("@rdkit/rdkit")).default as RDKitInit;

    // locateFile tells the Emscripten loader where to find RDKit_minimal.wasm.
    // The WASM file is copied to the Next.js public/ directory at install time.
    const mod = await initRDKitModule({
      locateFile: (file) => `/${file}`,
    });
    rdkitInstance = mod;
    return mod;
  })();

  return rdkitPromise;
}

/**
 * Hook that loads the RDKit WASM module as a singleton.
 * Returns `{ rdkit, loading, error }`.
 * The WASM is loaded once and shared across all components.
 */
export function useRDKit() {
  const [rdkit, setRDKit] = useState<RDKitModule | null>(rdkitInstance);
  const [loading, setLoading] = useState(!rdkitInstance);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (rdkitInstance) {
      setRDKit(rdkitInstance);
      setLoading(false);
      return;
    }

    let cancelled = false;
    loadRDKit()
      .then((mod) => {
        if (!cancelled) {
          setRDKit(mod);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { rdkit, loading, error };
}
