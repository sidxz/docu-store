"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const isSettingMolecule = useRef(false);
  const lastEmittedSmiles = useRef<string>("");
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const setMoleculeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const changeHandler = useRef<(() => void) | null>(null);

  const [KetcherEditor, setKetcherEditor] =
    useState<ComponentType<EditorProps> | null>(null);
  const [ServiceProviderClass, setServiceProviderClass] = useState<
    (new () => unknown) | null
  >(null);

  // Stable refs to avoid stale closures in changeEvent handler
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const valueRef = useRef(value);
  valueRef.current = value;

  // Memoize the service provider instance to prevent Ketcher re-initialization
  const serviceProviderInstance = useMemo(
    () => (ServiceProviderClass ? new ServiceProviderClass() : null),
    [ServiceProviderClass],
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      import("ketcher-react"),
      import("ketcher-standalone"),
    ]).then(([reactMod, standaloneMod]) => {
      if (cancelled) return;
      setKetcherEditor(() => reactMod.Editor);
      setServiceProviderClass(
        () => standaloneMod.StandaloneStructServiceProvider,
      );
    });
    import("ketcher-react/dist/index.css");
    return () => {
      cancelled = true;
    };
  }, []);

  // Subscribe to Ketcher changeEvent for real-time Ketcher→text sync
  const handleInit = useCallback(async (ketcher: Ketcher) => {
    // Clean up previous subscription if Ketcher re-initializes
    if (ketcherRef.current && changeHandler.current) {
      ketcherRef.current.changeEvent.remove(changeHandler.current);
    }

    ketcherRef.current = ketcher;

    // Load initial value if present
    const initialValue = valueRef.current;
    if (initialValue) {
      isSettingMolecule.current = true;
      try {
        await ketcher.setMolecule(initialValue);
        lastEmittedSmiles.current = initialValue;
      } catch {
        // Invalid SMILES — leave editor empty
      }
      setTimeout(() => {
        isSettingMolecule.current = false;
      }, 300);
    }

    // Create the change handler
    const handler = () => {
      if (isSettingMolecule.current) return;
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(async () => {
        const k = ketcherRef.current;
        if (!k || isSettingMolecule.current) return;
        try {
          const smiles = await k.getSmiles();
          const trimmed = smiles?.trim() ?? "";
          if (trimmed !== lastEmittedSmiles.current) {
            lastEmittedSmiles.current = trimmed;
            onChangeRef.current?.(trimmed);
          }
        } catch {
          // Empty canvas or invalid structure — emit empty string
          if (lastEmittedSmiles.current !== "") {
            lastEmittedSmiles.current = "";
            onChangeRef.current?.("");
          }
        }
      }, 500);
    };

    changeHandler.current = handler;
    ketcher.changeEvent.add(handler);
  }, []);

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
      const k = ketcherRef.current;
      if (!k) return;
      isSettingMolecule.current = true;
      try {
        await k.setMolecule(trimmed || "");
        lastEmittedSmiles.current = trimmed;
      } catch {
        // Invalid SMILES — Ketcher can't parse it (yet)
      }
      setTimeout(() => {
        isSettingMolecule.current = false;
      }, 300);
    }, 600);
  }, [value]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (setMoleculeTimer.current) clearTimeout(setMoleculeTimer.current);
      if (ketcherRef.current && changeHandler.current) {
        ketcherRef.current.changeEvent.remove(changeHandler.current);
      }
    };
  }, []);

  if (!KetcherEditor || !serviceProviderInstance) {
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
        structServiceProvider={serviceProviderInstance}
        onInit={handleInit}
        errorHandler={() => {
          // Ketcher internal errors are non-actionable; suppress.
        }}
      />
    </div>
  );
}
