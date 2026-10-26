"use client";

import { useState } from "react";

/** Parse the shared limit input: "" = unlimited (null), else a non-negative int.
 * Capped at `max` (default MAX_SAFE_INTEGER — beyond that JS silently loses precision). */
function parseLimitInput(raw: string, max = Number.MAX_SAFE_INTEGER): number | null | undefined {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 && n <= max ? n : undefined;
}

export function LimitInput({
  onSave,
  isPending,
  placeholder,
  max,
}: {
  onSave: (limit: number | null) => void;
  isPending: boolean;
  placeholder: string;
  /** Largest value Set accepts; anything above it is treated as invalid. */
  max?: number;
}) {
  const [value, setValue] = useState("");
  const [badInput, setBadInput] = useState(false);
  // badInput: the field shows text (e.g. "12e") but exposes value="" — without
  // this guard that would parse as "" = unlimited and silently drop the quota.
  const parsed = badInput ? undefined : parseLimitInput(value, max);
  return (
    <span className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        max={max}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setBadInput(e.target.validity.badInput);
        }}
        placeholder={placeholder}
        className="w-32 rounded-md border border-border-default bg-surface-elevated px-2 py-1 font-mono text-xs text-text-primary"
      />
      <button
        onClick={() => {
          if (parsed !== undefined) {
            onSave(parsed);
            setValue("");
            setBadInput(false);
          }
        }}
        disabled={isPending || parsed === undefined}
        className="rounded-md border border-border-default px-2 py-1 text-xs text-text-primary hover:bg-surface-sunken disabled:opacity-50"
      >
        Set
      </button>
    </span>
  );
}
