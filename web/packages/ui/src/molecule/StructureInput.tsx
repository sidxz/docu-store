"use client";

import dynamic from "next/dynamic";

const LazyStructureEditor = dynamic(
  () =>
    import("./StructureEditor").then((m) => ({
      default: m.StructureEditor,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-96 items-center justify-center rounded-lg border border-border-default bg-surface-elevated">
        <span className="text-sm text-text-subtle">Loading editor...</span>
      </div>
    ),
  },
);

export interface StructureInputProps {
  /** Current SMILES value */
  value: string;
  /** Called when the SMILES value changes (from text input or editor) */
  onChange: (smiles: string) => void;
  /** Placeholder for text input */
  placeholder?: string;
}

/**
 * Compound structure input showing a SMILES text field and Ketcher editor
 * simultaneously. Both stay in sync bidirectionally:
 *
 * - Drawing in Ketcher → updates the text input (via changeEvent)
 * - Typing/pasting SMILES → updates Ketcher (via setMolecule)
 */
export function StructureInput({
  value,
  onChange,
  placeholder = "Enter or paste SMILES, e.g. CC(=O)Oc1ccccc1C(=O)O",
}: StructureInputProps) {
  return (
    <div className="space-y-3">
      {/* SMILES text input — always visible */}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-border-default bg-surface-elevated px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-subtle focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none"
      />

      {/* Ketcher editor — always mounted */}
      <LazyStructureEditor
        value={value || undefined}
        onChange={onChange}
        height={450}
      />
    </div>
  );
}
