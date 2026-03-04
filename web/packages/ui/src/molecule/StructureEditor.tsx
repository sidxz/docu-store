"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType } from "react";
import type { Ketcher } from "ketcher-core";
import type { EditorProps } from "ketcher-react";

export interface StructureEditorProps {
  /** Current SMILES value — kept in sync bidirectionally */
  value?: string;
  /** Called when the user modifies the structure in Ketcher */
  onChange?: (smiles: string) => void;
  /** Height of the editor */
  height?: number | string;
}

export function StructureEditor({
  value,
  onChange,
  height = 400,
}: StructureEditorProps) {
  const ketcherRef = useRef<Ketcher | null>(null);
  const initialValueSet = useRef(false);
  const isSettingMolecule = useRef(false);
  const lastEmittedSmiles = useRef<string>("");
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const setMoleculeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [KetcherEditor, setKetcherEditor] =
    useState<ComponentType<EditorProps> | null>(null);
  const [ServiceProvider, setServiceProvider] = useState<
    (new () => unknown) | null
  >(null);

  // Stable ref for onChange to avoid re-subscribing changeEvent
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

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
    return () => {
      cancelled = true;
    };
  }, []);

  // Subscribe to Ketcher changeEvent for real-time Ketcher→text sync
  const handleInit = useCallback(
    async (ketcher: Ketcher) => {
      ketcherRef.current = ketcher;

      // Load initial value
      if (value && !initialValueSet.current) {
        initialValueSet.current = true;
        isSettingMolecule.current = true;
        try {
          await ketcher.setMolecule(value);
          lastEmittedSmiles.current = value;
        } catch {
          // Invalid SMILES — leave editor empty
        }
        // Small delay before clearing the guard so the resulting changeEvent is ignored
        setTimeout(() => {
          isSettingMolecule.current = false;
        }, 200);
      }

      // Subscribe to structure changes
      const handler = () => {
        if (isSettingMolecule.current) return;
        if (debounceTimer.current) clearTimeout(debounceTimer.current);
        debounceTimer.current = setTimeout(async () => {
          if (!ketcherRef.current || isSettingMolecule.current) return;
          try {
            const smiles = await ketcherRef.current.getSmiles();
            const trimmed = smiles?.trim() ?? "";
            if (trimmed !== lastEmittedSmiles.current) {
              lastEmittedSmiles.current = trimmed;
              onChangeRef.current?.(trimmed);
            }
          } catch {
            // Empty canvas or invalid structure
          }
        }, 500);
      };

      ketcher.changeEvent.add(handler);
    },
    // Only depend on initial value — we use refs for the rest
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [value],
  );

  // Text→Ketcher sync: when value prop changes externally, push into Ketcher
  useEffect(() => {
    const ketcher = ketcherRef.current;
    if (!ketcher) return;
    if (value === undefined) return;

    const trimmed = value.trim();
    // Skip if this value was just emitted by Ketcher itself
    if (trimmed === lastEmittedSmiles.current) return;

    if (setMoleculeTimer.current) clearTimeout(setMoleculeTimer.current);
    setMoleculeTimer.current = setTimeout(async () => {
      if (!ketcherRef.current) return;
      isSettingMolecule.current = true;
      try {
        await ketcherRef.current.setMolecule(trimmed || "");
        lastEmittedSmiles.current = trimmed;
      } catch {
        // Invalid SMILES — Ketcher can't parse it (yet)
      }
      setTimeout(() => {
        isSettingMolecule.current = false;
      }, 200);
    }, 600);
  }, [value]);

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (setMoleculeTimer.current) clearTimeout(setMoleculeTimer.current);
    };
  }, []);

  if (!KetcherEditor || !ServiceProvider) {
    return (
      <div
        style={{ height }}
        className="relative flex items-center justify-center overflow-hidden rounded-lg border border-border-default"
      >
        <div className="animate-pulse text-sm text-text-subtle">
          Loading editor...
        </div>
      </div>
    );
  }

  return (
    <div
      style={{ height }}
      className="relative overflow-hidden rounded-lg border border-border-default"
    >
      <KetcherEditor
        staticResourcesUrl=""
        structServiceProvider={new ServiceProvider()}
        onInit={handleInit}
        errorHandler={() => {
          // Ketcher internal errors are non-actionable; suppress.
        }}
      />
    </div>
  );
}
