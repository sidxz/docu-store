"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType } from "react";
import type { Ketcher } from "ketcher-core";
import type { EditorProps } from "ketcher-react";

export interface StructureEditorProps {
  /** Initial SMILES to load into the editor */
  value?: string;
  /** Called when the user modifies the structure (debounced) */
  onChange?: (smiles: string) => void;
  /** Height of the editor */
  height?: number | string;
}

/**
 * Molecular structure drawing editor powered by Ketcher (standalone mode).
 *
 * This component requires browser globals (canvas, DOM, workers) and MUST be
 * dynamically imported with `ssr: false`:
 *
 * ```tsx
 * import dynamic from "next/dynamic";
 * const StructureEditor = dynamic(
 *   () => import("@docu-store/ui/src/molecule/StructureEditor").then(m => m.StructureEditor),
 *   { ssr: false }
 * );
 * ```
 */
export function StructureEditor({
  value,
  onChange,
  height = 400,
}: StructureEditorProps) {
  const ketcherRef = useRef<Ketcher | null>(null);
  const initialValueSet = useRef(false);
  const [KetcherEditor, setKetcherEditor] = useState<ComponentType<EditorProps> | null>(null);
  const [ServiceProvider, setServiceProvider] = useState<(new () => unknown) | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      import("ketcher-react"),
      import("ketcher-standalone"),
    ]).then(([reactMod, standaloneMod]) => {
      if (cancelled) return;
      setKetcherEditor(() => reactMod.Editor);
      setServiceProvider(() => standaloneMod.StandaloneStructServiceProvider);
    });
    import("ketcher-react/dist/index.css");
    return () => { cancelled = true; };
  }, []);

  const handleInit = useCallback(
    async (ketcher: Ketcher) => {
      ketcherRef.current = ketcher;

      if (value && !initialValueSet.current) {
        initialValueSet.current = true;
        try {
          await ketcher.setMolecule(value);
        } catch {
          // Invalid SMILES — leave editor empty
        }
      }
    },
    [value],
  );

  if (!KetcherEditor || !ServiceProvider) {
    return (
      <div style={{ height }} className="relative rounded-lg border border-gray-200 overflow-hidden flex items-center justify-center">
        <div className="animate-pulse text-sm text-gray-400">Loading editor...</div>
      </div>
    );
  }

  return (
    <div style={{ height }} className="relative rounded-lg border border-gray-200 overflow-hidden">
      <KetcherEditor
        staticResourcesUrl=""
        structServiceProvider={new ServiceProvider()}
        onInit={handleInit}
        errorHandler={() => {
          // Ketcher internal errors are non-actionable; suppress.
        }}
      />
      {onChange && (
        <button
          type="button"
          className="absolute bottom-3 right-3 z-10 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-blue-700 transition-colors"
          onClick={async () => {
            if (!ketcherRef.current) return;
            try {
              const smiles = await ketcherRef.current.getSmiles();
              if (smiles) onChange(smiles);
            } catch {
              // Empty canvas or invalid structure
            }
          }}
        >
          Use Structure
        </button>
      )}
    </div>
  );
}
